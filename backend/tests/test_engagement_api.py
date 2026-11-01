"""Customer reviews, Q&A and returns, end to end.

These paths did not exist until customers had no way to review, ask or return.
The happy paths here run against a delivered order created in the fixture, so
the verified-purchase badge and the return window are exercised for real.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.deps import get_db
from app.core.security import hash_password
from app.main import app


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def scenario(db):
    """A customer with a delivered order, so reviews and returns are possible."""
    user_id = db.execute(
        text(
            'INSERT INTO "user" (email, full_name, password_hash, role, email_verified_at) '
            "VALUES ('buyer@test.pk', 'Test Buyer', :pw, 'customer', now()) RETURNING id"
        ),
        {"pw": hash_password("buyer-pass-1")},
    ).scalar_one()

    category = db.execute(
        text("INSERT INTO category (name, slug, path, depth) "
             "VALUES ('Dining', 'dining', 'dining', 0) RETURNING id")
    ).scalar_one()
    product_id = db.execute(
        text("INSERT INTO product (category_id, name, slug, base_price_paisa, status) "
             "VALUES (:c, 'Sheesham Table', 'sheesham-table', 1000000, 'active') RETURNING id"),
        {"c": category},
    ).scalar_one()
    variant_id = db.execute(
        text("INSERT INTO product_variant (product_id, sku) "
             "VALUES (:p, 'WC-T-1') RETURNING id"),
        {"p": product_id},
    ).scalar_one()
    db.execute(
        text("INSERT INTO stock_level (variant_id, on_hand) VALUES (:v, 10)"),
        {"v": variant_id},
    )

    # A delivered order, delivered yesterday so it is inside the return window.
    order_id = db.execute(
        text(
            'INSERT INTO "order" (order_number, user_id, status, subtotal_paisa, '
            '  total_paisa, tax_paisa, shipping_name, shipping_phone, shipping_line1, '
            '  shipping_city, shipping_province, placed_at, delivered_at) '
            "VALUES ('WC-2026-000900', :u, 'delivered', 2000000, 2065000, 315000, "
            "  'Test Buyer', '03001234567', 'House 1', 'Lahore', 'punjab', "
            "  :placed, :delivered) RETURNING id"
        ),
        {"u": user_id, "placed": datetime.now(UTC) - timedelta(days=5),
         "delivered": datetime.now(UTC) - timedelta(days=1)},
    ).scalar_one()
    order_item_id = db.execute(
        text("INSERT INTO order_item (order_id, product_id, variant_id, product_name, "
             "  sku, quantity, unit_price_paisa, tax_paisa, line_total_paisa) "
             "VALUES (:o, :p, :v, 'Sheesham Table', 'WC-T-1', 2, 1000000, 315000, 2000000) "
             "RETURNING id"),
        {"o": order_id, "p": product_id, "v": variant_id},
    ).scalar_one()
    db.flush()

    return {
        "user_id": user_id, "product_slug": "sheesham-table",
        "order_number": "WC-2026-000900", "order_item_id": str(order_item_id),
    }


def login(client) -> dict:
    r = client.post("/api/v1/auth/login",
                    json={"email": "buyer@test.pk", "password": "buyer-pass-1"})
    return {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}


class TestReviews:
    def test_customer_can_review_a_delivered_purchase(self, client, scenario) -> None:
        h = login(client)
        check = client.get(f"/api/v1/products/{scenario['product_slug']}/can-review", headers=h)
        assert check.json() == {"can_review": True, "verified": True, "reason": None}

        r = client.post(
            f"/api/v1/products/{scenario['product_slug']}/reviews",
            headers=h, json={"rating": 5, "title": "Great", "body": "Really solid, very happy."},
        )
        assert r.status_code == 201

    def test_unverified_customer_cannot_review(self, client, scenario, db) -> None:
        db.execute(
            text('UPDATE "user" SET email_verified_at = NULL WHERE id = :u'),
            {"u": scenario["user_id"]},
        )
        h = login(client)
        r = client.post(
            f"/api/v1/products/{scenario['product_slug']}/reviews",
            headers=h,
            json={"rating": 5, "body": "Please verify before reviewing."},
        )
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "email_not_verified"

    def test_new_review_is_held_for_moderation(self, client, scenario, db) -> None:
        h = login(client)
        client.post(f"/api/v1/products/{scenario['product_slug']}/reviews",
                    headers=h, json={"rating": 5, "body": "Held until approved please."})
        status = db.execute(
            text("SELECT status FROM review WHERE user_id = :u"),
            {"u": scenario["user_id"]},
        ).scalar_one()
        assert status == "pending"

    def test_pending_review_is_not_publicly_listed(self, client, scenario) -> None:
        h = login(client)
        client.post(f"/api/v1/products/{scenario['product_slug']}/reviews",
                    headers=h, json={"rating": 5, "body": "Not visible until approved."})
        listed = client.get(f"/api/v1/products/{scenario['product_slug']}/reviews")
        assert listed.json() == []

    def test_verified_badge_requires_a_delivered_order(self, client, scenario, db) -> None:
        # A different customer who never bought it gets an unverified review.
        db.execute(
            text('INSERT INTO "user" (email, full_name, password_hash, role, '
                 "email_verified_at) VALUES ('nobuy@test.pk', 'No Buy', :pw, "
                 "'customer', now())"),
            {"pw": hash_password("nobuy-pass-1")},
        )
        db.flush()
        r = client.post("/api/v1/auth/login",
                        json={"email": "nobuy@test.pk", "password": "nobuy-pass-1"})
        h = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}
        check = client.get(f"/api/v1/products/{scenario['product_slug']}/can-review", headers=h)
        assert check.json()["verified"] is False

    def test_cannot_review_twice(self, client, scenario) -> None:
        h = login(client)
        first = client.post(f"/api/v1/products/{scenario['product_slug']}/reviews",
                            headers=h, json={"rating": 5, "body": "My one and only review."})
        assert first.status_code == 201
        second = client.post(f"/api/v1/products/{scenario['product_slug']}/reviews",
                             headers=h, json={"rating": 1, "body": "Trying to review again."})
        assert second.status_code == 409

    def test_review_requires_auth(self, client, scenario) -> None:
        r = client.post(f"/api/v1/products/{scenario['product_slug']}/reviews",
                        json={"rating": 5, "body": "Anonymous review attempt here."})
        assert r.status_code == 401

    def test_short_body_rejected(self, client, scenario) -> None:
        h = login(client)
        r = client.post(f"/api/v1/products/{scenario['product_slug']}/reviews",
                        headers=h, json={"rating": 5, "body": "short"})
        assert r.status_code == 422


class TestQuestions:
    def test_ask_a_question(self, client, scenario) -> None:
        h = login(client)
        r = client.post(f"/api/v1/products/{scenario['product_slug']}/questions",
                        headers=h, json={"body": "Does it come flat packed?"})
        assert r.status_code == 201

    def test_question_held_until_published(self, client, scenario) -> None:
        h = login(client)
        client.post(f"/api/v1/products/{scenario['product_slug']}/questions",
                    headers=h, json={"body": "Is delivery free to Quetta?"})
        assert client.get(f"/api/v1/products/{scenario['product_slug']}/questions").json() == []

    def test_guest_cannot_ask(self, client, scenario) -> None:
        r = client.post(f"/api/v1/products/{scenario['product_slug']}/questions",
                        json={"body": "Can a guest ask a question like this?"})
        assert r.status_code == 401


class TestReturns:
    def test_returnable_lists_the_delivered_items(self, client, scenario) -> None:
        h = login(client)
        r = client.get(f"/api/v1/orders/{scenario['order_number']}/returnable", headers=h)
        body = r.json()
        assert body["eligible"] is True
        assert len(body["items"]) == 1
        assert body["items"][0]["returnable"] == 2

    def test_request_a_return(self, client, scenario) -> None:
        h = login(client)
        r = client.post(
            f"/api/v1/orders/{scenario['order_number']}/returns",
            headers=h,
            json={"reason": "size_issue", "customer_note": "Bigger than expected.",
                  "items": [{"order_item_id": scenario["order_item_id"], "quantity": 1}]},
        )
        assert r.status_code == 201
        assert "WC-RET-" in r.json()["message"]

    def test_return_shows_in_my_returns(self, client, scenario) -> None:
        h = login(client)
        client.post(f"/api/v1/orders/{scenario['order_number']}/returns", headers=h,
                    json={"reason": "changed_mind",
                          "items": [{"order_item_id": scenario["order_item_id"], "quantity": 1}]})
        mine = client.get("/api/v1/returns", headers=h).json()
        assert len(mine) == 1
        assert mine[0]["order_number"] == scenario["order_number"]

    def test_cannot_return_more_than_bought(self, client, scenario) -> None:
        h = login(client)
        r = client.post(f"/api/v1/orders/{scenario['order_number']}/returns", headers=h,
                        json={"reason": "other",
                              "items": [{"order_item_id": scenario["order_item_id"], "quantity": 5}]})
        assert r.status_code == 422

    def test_cannot_return_another_persons_order(self, client, scenario, db) -> None:
        db.execute(
            text('INSERT INTO "user" (email, full_name, password_hash, role, '
                 "email_verified_at) VALUES ('other@test.pk', 'Other', :pw, "
                 "'customer', now())"),
            {"pw": hash_password("other-pass-1")},
        )
        db.flush()
        r = client.post("/api/v1/auth/login",
                        json={"email": "other@test.pk", "password": "other-pass-1"})
        h = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}
        # The order is scoped to its owner, so to someone else it is simply absent.
        got = client.get(f"/api/v1/orders/{scenario['order_number']}/returnable", headers=h)
        assert got.status_code == 404

    def test_window_closed_blocks_return(self, client, scenario, db) -> None:
        # Push the delivery date back beyond the 14-day window.
        db.execute(
            text('UPDATE "order" SET delivered_at = :d WHERE order_number = :n'),
            {"d": datetime.now(UTC) - timedelta(days=40), "n": scenario["order_number"]},
        )
        db.flush()
        h = login(client)
        info = client.get(f"/api/v1/orders/{scenario['order_number']}/returnable", headers=h)
        assert info.json()["eligible"] is False
        assert info.json()["reason"] == "window_closed"

        blocked = client.post(
            f"/api/v1/orders/{scenario['order_number']}/returns", headers=h,
            json={"reason": "changed_mind",
                  "items": [{"order_item_id": scenario["order_item_id"], "quantity": 1}]},
        )
        assert blocked.status_code == 409
