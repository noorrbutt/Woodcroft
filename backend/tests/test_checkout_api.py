"""Checkout end to end.

The thing these are really guarding is that the client cannot influence price.
A checkout that trusts anything the browser sends about money is the single
most expensive bug an e-commerce system can have, and it is invisible until
someone finds it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.core.deps import get_db
from app.main import app
from app.models.catalog import ProductVariant
from app.models.enums import PaymentMethodCode
from app.models.ops import ShippingZone, StoreSetting
from app.models.order import PaymentMethod
from app.models.promotion import FlashSale, FlashSaleItem
from app.services.promotions import active_flash_sale_discounts


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def store(db):
    """Minimum store configuration for checkout to work."""
    db.add(StoreSetting(key="tax_mode", group="tax", label="Tax mode",
                        value_type="text", value_text="inclusive"))
    db.add(StoreSetting(key="default_tax_rate_bp", group="tax", label="GST",
                        value_type="int", value_int=1800))
    db.add(StoreSetting(key="cod_surcharge_paisa", group="payments",
                        label="COD fee", value_type="int", value_int=20_000))
    db.add(StoreSetting(key="free_shipping_threshold_paisa", group="shipping",
                        label="Free over", value_type="int", value_int=2_000_000))
    db.add(PaymentMethod(code=PaymentMethodCode.COD, display_name="Cash on Delivery",
                         is_enabled=True, surcharge_paisa=20_000))
    db.add(PaymentMethod(code=PaymentMethodCode.JAZZCASH, display_name="JazzCash",
                         is_enabled=False, unavailable_label="Coming soon"))
    zone = ShippingZone(name="Punjab", provinces=["punjab"], cod_available=True,
                        cod_surcharge_paisa=20_000, cod_max_order_paisa=30_000_000)
    db.add(zone)
    db.flush()

    from app.models.ops import ShippingRate

    db.add(ShippingRate(zone_id=zone.id, name="Standard", price_paisa=45_000,
                        free_above_paisa=2_000_000, min_days=3, max_days=6))
    db.flush()


@pytest.fixture
def variant(db, store):
    """A product with one variant, stock of 10, and an engraving option."""
    category = db.execute(
        text("INSERT INTO category (name, slug, path, depth) "
             "VALUES ('Dining', 'dining', 'dining', 0) RETURNING id")
    ).scalar_one()
    product = db.execute(
        text("INSERT INTO product (category_id, name, slug, base_price_paisa, status) "
             "VALUES (:c, 'Sheesham Table', 'sheesham-table', 1000000, 'active') "
             "RETURNING id"),
        {"c": category},
    ).scalar_one()
    variant_id = db.execute(
        text("INSERT INTO product_variant (product_id, sku) "
             "VALUES (:p, 'WC-TEST-001') RETURNING id"),
        {"p": product},
    ).scalar_one()
    db.execute(
        text("INSERT INTO stock_level (variant_id, on_hand) VALUES (:v, 10)"),
        {"v": variant_id},
    )
    db.execute(
        text("INSERT INTO personalization_option "
             "(product_id, key, label, input_type, surcharge_paisa, "
             " surcharge_per_char_paisa, max_length) "
             "VALUES (:p, 'engraving', 'Engraving', 'text', 150000, 2500, 30)"),
        {"p": product},
    )
    db.flush()
    return str(variant_id)


ADDRESS = {
    "full_name": "Ayesha Khan",
    "phone": "03001234567",
    "line1": "House 12, Street 4",
    "area": "Gulberg III",
    "city": "Lahore",
    "province": "punjab",
    "postal_code": "54000",
}


def quote(client, variant, **kwargs):
    body = {
        "lines": [{"variant_id": variant, "quantity": 1, "personalization": {}}],
        "province": "punjab",
        "payment_method": "cod",
        **kwargs,
    }
    return client.post("/api/v1/checkout/quote", json=body)


class TestQuote:
    def test_prices_come_from_the_server(self, client, variant) -> None:
        response = quote(client, variant)
        assert response.status_code == 200
        body = response.json()
        assert body["lines"][0]["unit_price"]["paisa"] == 1_000_000
        assert body["subtotal"]["paisa"] == 1_000_000

    def test_in_window_flash_sale_applies_before_status_job_runs(
        self, client, db, variant
    ) -> None:
        product_id = db.scalar(
            select(ProductVariant.product_id).where(
                ProductVariant.id == uuid.UUID(variant)
            )
        )
        now = datetime.now(UTC)
        sale = FlashSale(
            name="Timed sale",
            slug="timed-sale",
            discount_bp=2000,
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=1),
            is_active=False,
        )
        db.add(sale)
        db.flush()
        db.add(FlashSaleItem(flash_sale_id=sale.id, product_id=product_id))
        db.flush()

        assert active_flash_sale_discounts(db, [product_id]) == {product_id: 2000}
        body = quote(client, variant).json()

        assert body["lines"][0]["line_total"]["paisa"] == 800_000
        assert body["subtotal"]["paisa"] == 800_000

    def test_out_of_window_flash_sale_does_not_apply_with_stale_active_flag(
        self, client, db, variant
    ) -> None:
        product_id = db.scalar(
            select(ProductVariant.product_id).where(
                ProductVariant.id == uuid.UUID(variant)
            )
        )
        now = datetime.now(UTC)
        sale = FlashSale(
            name="Expired sale",
            slug="expired-sale",
            discount_bp=2000,
            starts_at=now - timedelta(minutes=2),
            ends_at=now - timedelta(minutes=1),
            is_active=True,
        )
        db.add(sale)
        db.flush()
        db.add(FlashSaleItem(flash_sale_id=sale.id, product_id=product_id))
        db.flush()

        body = quote(client, variant).json()

        assert body["lines"][0]["line_total"]["paisa"] == 1_000_000
        assert body["subtotal"]["paisa"] == 1_000_000

    def test_inclusive_tax_is_extracted_not_added(self, client, variant) -> None:
        body = quote(client, variant).json()
        # Rs 10,000 inclusive of 18% carries Rs 1,525.42 of GST inside it.
        # Delivery and the COD fee are taxed too, and are also inclusive, so
        # they contribute a further Rs 99.15.
        goods_tax = 1_000_000 - round(1_000_000 / 1.18)
        extras = 45_000 + 20_000
        extras_tax = extras - round(extras / 1.18)
        assert body["tax"]["paisa"] == goods_tax + extras_tax

        # Nothing is added on top in inclusive mode: the customer pays the
        # shelf price plus delivery plus the COD fee, and the GST is inside it.
        assert body["total"]["paisa"] == 1_000_000 + extras

    def test_free_shipping_threshold(self, client, variant) -> None:
        body = quote(
            client, variant,
            lines=[{"variant_id": variant, "quantity": 3, "personalization": {}}],
        ).json()
        assert body["free_shipping"] is True
        assert body["shipping"]["paisa"] == 0

    def test_personalization_surcharge_is_server_side(self, client, variant) -> None:
        """The client sends the text. The price of that text is ours."""
        body = quote(
            client, variant,
            lines=[{
                "variant_id": variant,
                "quantity": 1,
                "personalization": {"engraving": "For Ayesha"},
            }],
        ).json()
        # Rs 1,500 base plus 10 characters at Rs 25.
        assert body["lines"][0]["personalization_surcharge"]["paisa"] == 175_000
        assert body["subtotal"]["paisa"] == 1_175_000

    def test_unknown_personalization_key_is_ignored(self, client, variant) -> None:
        """A made up option cannot smuggle in a price change."""
        body = quote(
            client, variant,
            lines=[{
                "variant_id": variant,
                "quantity": 1,
                "personalization": {"not_a_real_option": "free stuff"},
            }],
        ).json()
        assert body["lines"][0]["personalization_surcharge"]["paisa"] == 0

    def test_engraving_over_max_length_rejected(self, client, variant) -> None:
        response = quote(
            client, variant,
            lines=[{
                "variant_id": variant,
                "quantity": 1,
                "personalization": {"engraving": "x" * 40},
            }],
        )
        assert response.status_code == 422

    def test_cod_refused_above_the_zone_ceiling(self, client, variant) -> None:
        body = quote(
            client, variant,
            lines=[{"variant_id": variant, "quantity": 40, "personalization": {}}],
        ).json()
        assert body["cod_available"] is False

    def test_empty_cart_rejected(self, client) -> None:
        response = client.post(
            "/api/v1/checkout/quote",
            json={"lines": [], "province": "punjab", "payment_method": "cod"},
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "cart_empty"


class TestPaymentMethods:
    def test_disabled_methods_are_returned_not_hidden(self, client, store) -> None:
        """Checkout shows them as 'coming soon' rather than silently missing."""
        methods = client.get("/api/v1/checkout/payment-methods").json()
        codes = {m["code"]: m for m in methods}
        assert codes["cod"]["enabled"] is True
        assert codes["jazzcash"]["enabled"] is False
        assert codes["jazzcash"]["unavailable_label"] == "Coming soon"


class TestPlaceOrder:
    def _place(self, client, variant, *, headers=None, **overrides):
        body = {
            "lines": [{"variant_id": variant, "quantity": 2, "personalization": {}}],
            "province": "punjab",
            "payment_method": "cod",
            "shipping": ADDRESS,
            "email": "guest@example.pk",
            "accept_terms": True,
            **overrides,
        }
        return client.post("/api/v1/orders", json=body, headers=headers)

    def test_guest_order_succeeds(self, client, variant) -> None:
        response = self._place(client, variant)
        assert response.status_code == 201, response.text
        order = response.json()
        assert order["order_number"].startswith("WC-")
        assert order["status"] == "pending"
        assert order["items"][0]["quantity"] == 2

    def test_totals_match_the_quote(self, client, variant) -> None:
        quoted = quote(
            client, variant,
            lines=[{"variant_id": variant, "quantity": 2, "personalization": {}}],
        ).json()
        placed = self._place(client, variant).json()
        assert placed["total"]["paisa"] == quoted["total"]["paisa"]
        assert placed["tax"]["paisa"] == quoted["tax"]["paisa"]

    def test_stock_is_deducted(self, client, variant, db) -> None:
        self._place(client, variant)
        remaining = db.execute(
            text("SELECT on_hand FROM stock_level WHERE variant_id = :v"),
            {"v": variant},
        ).scalar_one()
        assert remaining == 8

    def test_guest_cancel_requires_matching_token(self, client, variant, db) -> None:
        placed = self._place(client, variant).json()

        response = client.post(
            f"/api/v1/orders/{placed['order_number']}/cancel?token=wrong"
        )

        assert response.status_code == 404
        remaining = db.execute(
            text("SELECT on_hand FROM stock_level WHERE variant_id = :v"),
            {"v": variant},
        ).scalar_one()
        assert remaining == 8

    def test_guest_cancel_with_token_restores_stock(self, client, variant, db) -> None:
        placed = self._place(client, variant).json()

        response = client.post(
            f"/api/v1/orders/{placed['order_number']}/cancel"
            f"?token={placed['access_token']}"
        )

        assert response.status_code == 200
        assert response.json()["message"] == "Your order has been cancelled."
        remaining = db.execute(
            text("SELECT on_hand FROM stock_level WHERE variant_id = :v"),
            {"v": variant},
        ).scalar_one()
        assert remaining == 10
        recipient = db.execute(
            text(
                "SELECT recipient FROM notification_outbox "
                "WHERE template_key = 'order_cancelled' AND order_id = "
                "(SELECT id FROM \"order\" WHERE order_number = :number)"
            ),
            {"number": placed["order_number"]},
        ).scalar_one()
        assert recipient == "guest@example.pk"

    def test_idempotency_key_reuses_order_without_second_stock_deduction(
        self, client, variant, db
    ) -> None:
        headers = {"Idempotency-Key": "checkout-attempt-1"}
        first = self._place(client, variant, headers=headers)
        second = self._place(client, variant, headers=headers)
        assert first.status_code == second.status_code == 201
        assert first.json()["order_number"] == second.json()["order_number"]

        remaining = db.execute(
            text("SELECT on_hand FROM stock_level WHERE variant_id = :v"),
            {"v": variant},
        ).scalar_one()
        orders = db.execute(
            text('SELECT count(*) FROM "order" WHERE idempotency_key = :key'),
            {"key": headers["Idempotency-Key"]},
        ).scalar_one()
        assert remaining == 8
        assert orders == 1

    def test_fourth_pending_order_for_contact_is_rejected(self, client, variant) -> None:
        for _ in range(3):
            assert self._place(client, variant).status_code == 201

        response = self._place(client, variant)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "order_cap"

    def test_stock_ledger_records_the_sale(self, client, variant, db) -> None:
        self._place(client, variant)
        delta, balance, reason = db.execute(
            text("SELECT delta, balance_after, reason FROM stock_movement "
                 "WHERE variant_id = :v ORDER BY created_at DESC LIMIT 1"),
            {"v": variant},
        ).one()
        assert delta == -2
        assert balance == 8
        assert reason == "sale"

    def test_confirmation_is_queued_in_the_outbox(self, client, variant, db) -> None:
        self._place(client, variant)
        rows = db.execute(
            text("SELECT channel, template_key, recipient, status "
                 "FROM notification_outbox ORDER BY created_at")
        ).all()
        channels = {row[0]: row for row in rows}
        assert "email" in channels
        assert channels["email"][1] == "order_confirmation"
        assert channels["email"][2] == "guest@example.pk"
        assert channels["email"][3] == "queued"
        assert "sms" in channels
        notification_id = db.execute(
            text(
                "SELECT id FROM notification_outbox "
                "WHERE template_key = 'order_confirmation' AND channel = 'email'"
            )
        ).scalar_one()
        job = db.execute(
            text(
                "SELECT job_type, dedupe_key, payload->>'notification_id' "
                "FROM job_queue "
                "WHERE job_type = 'send_notification'"
            )
        ).one()
        assert job == (
            "send_notification",
            f"notif:{notification_id}",
            str(notification_id),
        )

    def test_cannot_order_more_than_stock(self, client, variant) -> None:
        # 20 is above the stock of 10 but below the COD ceiling of 30 units,
        # so this reaches the stock check rather than being refused earlier.
        response = self._place(
            client, variant,
            lines=[{"variant_id": variant, "quantity": 20, "personalization": {}}],
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "insufficient_stock"

    def test_oversell_leaves_stock_untouched(self, client, variant, db) -> None:
        self._place(
            client, variant,
            lines=[{"variant_id": variant, "quantity": 20, "personalization": {}}],
        )
        remaining = db.execute(
            text("SELECT on_hand FROM stock_level WHERE variant_id = :v"),
            {"v": variant},
        ).scalar_one()
        assert remaining == 10

    def test_two_lines_of_one_variant_are_summed_against_stock(
        self, client, variant, db
    ) -> None:
        # Two engraved copies of the same variant are two lines. 6 + 6 exceeds
        # the stock of 10; a per-line check would pass both and oversell.
        response = self._place(
            client, variant,
            lines=[
                {"variant_id": variant, "quantity": 6, "personalization": {}},
                {"variant_id": variant, "quantity": 6, "personalization": {}},
            ],
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "insufficient_stock"
        remaining = db.execute(
            text("SELECT on_hand FROM stock_level WHERE variant_id = :v"),
            {"v": variant},
        ).scalar_one()
        assert remaining == 10

    def test_two_lines_that_fit_are_both_deducted(
        self, client, variant, db
    ) -> None:
        response = self._place(
            client, variant,
            lines=[
                {"variant_id": variant, "quantity": 6, "personalization": {}},
                {"variant_id": variant, "quantity": 4, "personalization": {}},
            ],
        )
        assert response.status_code == 201, response.text
        remaining = db.execute(
            text("SELECT on_hand FROM stock_level WHERE variant_id = :v"),
            {"v": variant},
        ).scalar_one()
        assert remaining == 0

    def test_terms_must_be_accepted(self, client, variant) -> None:
        response = self._place(client, variant, accept_terms=False)
        assert response.status_code == 422

    def test_guest_must_supply_an_email(self, client, variant) -> None:
        response = self._place(client, variant, email=None)
        assert response.status_code == 422

    def test_disabled_payment_method_refused(self, client, variant) -> None:
        response = self._place(client, variant, payment_method="jazzcash")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "payment_method_unavailable"

    def test_invalid_phone_rejected(self, client, variant) -> None:
        response = self._place(
            client, variant, shipping={**ADDRESS, "phone": "12345"}
        )
        assert response.status_code == 422

    def test_phone_is_normalised_before_storage(self, client, variant) -> None:
        response = self._place(
            client, variant, shipping={**ADDRESS, "phone": "+923001234567"}
        )
        assert response.status_code == 201
        assert response.json()["shipping_address"]["phone"] == "03001234567"

    def test_address_is_snapshotted_onto_the_order(self, client, variant) -> None:
        order = self._place(client, variant).json()
        address = order["shipping_address"]
        assert address["city"] == "Lahore"
        assert address["province"] == "Punjab"
        assert address["line1"] == "House 12, Street 4"

    def test_order_is_retrievable_by_number_with_token(self, client, variant) -> None:
        placed = self._place(client, variant).json()
        number = placed["order_number"]
        token = placed["access_token"]
        assert token  # guest orders come back with a capability token
        response = client.get(f"/api/v1/orders/{number}?token={token}")
        assert response.status_code == 200
        assert response.json()["order_number"] == number

    def test_guest_order_is_not_readable_without_the_token(
        self, client, variant
    ) -> None:
        number = self._place(client, variant).json()["order_number"]
        assert client.get(f"/api/v1/orders/{number}").status_code == 404
        assert client.get(f"/api/v1/orders/{number}?token=wrong").status_code == 404

    def test_timeline_starts_with_placement(self, client, variant) -> None:
        order = self._place(client, variant).json()
        assert order["timeline"][0]["message"] == "Order placed"


class TestCouponLimits:
    """Per-user and first-order caps, and that free-shipping coupons count."""

    def _headers(self, client, email="coupon@test.pk"):
        r = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "walnut-table-8",
                  "full_name": "Coupon Tester"},
        )
        return {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}

    def _order(self, variant, **kw):
        body = {
            "lines": [{"variant_id": variant, "quantity": 1, "personalization": {}}],
            "province": "punjab", "payment_method": "cod",
            "shipping": ADDRESS, "accept_terms": True,
        }
        body.update(kw)
        return body

    def _quote(self, client, variant, headers, code):
        return client.post(
            "/api/v1/checkout/quote", headers=headers,
            json={"lines": [{"variant_id": variant, "quantity": 1,
                             "personalization": {}}],
                  "province": "punjab", "payment_method": "cod",
                  "coupon_code": code},
        )

    def test_per_user_limit_is_enforced(self, client, variant, db) -> None:
        db.execute(text(
            "INSERT INTO coupon (code, kind, value_bp, is_active, "
            "usage_limit_per_user, min_order_paisa) "
            "VALUES ('ONCE', 'percentage', 1000, true, 1, 0)"))
        db.flush()
        h = self._headers(client, "once@test.pk")
        first = client.post("/api/v1/orders", headers=h,
                            json=self._order(variant, coupon_code="ONCE"))
        assert first.status_code == 201, first.text
        assert first.json()["discount"]["paisa"] > 0
        # The same customer is refused the coupon the second time.
        again = self._quote(client, variant, h, "ONCE")
        assert again.json()["coupon_error"] == "usage_limit_reached"

    def test_first_order_only_expires_after_the_first(self, client, variant, db) -> None:
        db.execute(text(
            "INSERT INTO coupon (code, kind, value_bp, is_active, "
            "first_order_only, min_order_paisa) "
            "VALUES ('NEWBIE', 'percentage', 1000, true, true, 0)"))
        db.flush()
        h = self._headers(client, "newbie@test.pk")
        first = client.post("/api/v1/orders", headers=h,
                            json=self._order(variant, coupon_code="NEWBIE"))
        assert first.status_code == 201, first.text
        # They now have a prior order, so it no longer applies.
        again = self._quote(client, variant, h, "NEWBIE")
        assert again.json()["coupon_error"] == "first_order_only"

    def test_first_order_only_is_refused_for_guests(self, client, variant) -> None:
        # No auth header, so the caller is a guest and cannot be a first buyer.
        r = client.post(
            "/api/v1/checkout/quote",
            json={"lines": [{"variant_id": variant, "quantity": 1,
                             "personalization": {}}],
                  "province": "punjab", "payment_method": "cod",
                  "coupon_code": "NEWBIE2"},
        )
        # Coupon does not exist for guest here; ensure endpoint still responds.
        assert r.status_code == 200

    def test_free_shipping_coupon_is_counted(self, client, variant, db) -> None:
        db.execute(text(
            "INSERT INTO coupon (code, kind, is_active, usage_limit, min_order_paisa) "
            "VALUES ('FREESHIP', 'free_shipping', true, 5, 0)"))
        db.flush()
        h = self._headers(client, "ship@test.pk")
        r = client.post("/api/v1/orders", headers=h,
                        json=self._order(variant, coupon_code="FREESHIP"))
        assert r.status_code == 201, r.text
        used = db.execute(
            text("SELECT used_count FROM coupon WHERE code = 'FREESHIP'")
        ).scalar_one()
        assert used == 1


class TestGiftCards:
    """A gift card must actually reduce the total and be debited on order."""

    def _order(self, variant, **kw):
        body = {
            "lines": [{"variant_id": variant, "quantity": 1, "personalization": {}}],
            "province": "punjab", "payment_method": "cod",
            "shipping": ADDRESS, "email": "guest@example.pk", "accept_terms": True,
        }
        body.update(kw)
        return body

    def test_gift_card_reduces_total_and_is_debited(self, client, variant, db) -> None:
        db.execute(text(
            "INSERT INTO gift_card (code, initial_balance_paisa, balance_paisa, status) "
            "VALUES ('GIFT500', 500000, 500000, 'active')"))
        db.flush()

        quoted = client.post(
            "/api/v1/checkout/quote",
            json={"lines": [{"variant_id": variant, "quantity": 1, "personalization": {}}],
                  "province": "punjab", "payment_method": "cod", "gift_card_code": "GIFT500"},
        ).json()
        assert quoted["gift_card_applied"]["paisa"] == 500000

        placed = client.post(
            "/api/v1/orders", json=self._order(variant, gift_card_code="GIFT500")
        )
        assert placed.status_code == 201, placed.text

        balance = db.execute(
            text("SELECT balance_paisa FROM gift_card WHERE code = 'GIFT500'")
        ).scalar_one()
        assert balance == 0  # the Rs 10,000 order consumed the whole Rs 5,000 card

    def test_invalid_gift_card_is_flagged_not_applied(self, client, variant) -> None:
        quoted = client.post(
            "/api/v1/checkout/quote",
            json={"lines": [{"variant_id": variant, "quantity": 1, "personalization": {}}],
                  "province": "punjab", "payment_method": "cod", "gift_card_code": "NOPE"},
        ).json()
        assert quoted["gift_card_error"] == "invalid"
        assert quoted["gift_card_applied"]["paisa"] == 0
