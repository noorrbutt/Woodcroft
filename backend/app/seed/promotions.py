"""Seed coupons, automatic discounts, a live flash sale and gift cards."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.enums import DiscountKind, DiscountTarget, GiftCardStatus
from app.models.promotion import (
    Bundle,
    BundleItem,
    Coupon,
    DiscountRule,
    FlashSale,
    FlashSaleItem,
    GiftCard,
    GiftCardTransaction,
)


def seed_promotions(s) -> None:
    now = datetime.now(UTC)
    _coupons(s, now)
    _automatic_rules(s, now)
    _flash_sale(s, now)
    _bundles(s)
    _gift_cards(s, now)
    s.db.flush()
    s.log(
        f"{len(s.coupons)} coupons, 2 automatic rules, 1 live flash sale, "
        f"2 bundles, 8 gift cards"
    )


def _coupons(s, now: datetime) -> None:
    # Deliberately spans every state the admin list has to render: live,
    # scheduled, exhausted and expired.
    rows = [
        ("WELCOME10", "10% off your first order", DiscountKind.PERCENTAGE,
         1000, None, 500_000, True, now - timedelta(days=200), now + timedelta(days=200), 500, 138),
        ("WOOD15", "15% off everything", DiscountKind.PERCENTAGE,
         1500, None, 1_000_000, False, now - timedelta(days=30), now + timedelta(days=60), 300, 47),
        ("FREESHIP", "Free delivery, any order", DiscountKind.FREE_SHIPPING,
         None, None, 0, False, now - timedelta(days=90), now + timedelta(days=90), None, 212),
        ("FLAT2000", "Rs 2,000 off orders over Rs 15,000", DiscountKind.FIXED_AMOUNT,
         None, 200_000, 1_500_000, False, now - timedelta(days=60), now + timedelta(days=30), 200, 64),
        ("EID25", "Eid campaign, starts next week", DiscountKind.PERCENTAGE,
         2500, None, 2_000_000, False, now + timedelta(days=7), now + timedelta(days=21), 400, 0),
        ("SOLDOUT50", "Exhausted promotion", DiscountKind.PERCENTAGE,
         5000, None, 0, False, now - timedelta(days=120), now + timedelta(days=10), 50, 50),
        ("EXPIRED20", "Last year's campaign", DiscountKind.PERCENTAGE,
         2000, None, 0, False, now - timedelta(days=400), now - timedelta(days=300), 500, 301),
    ]

    for (code, desc, kind, bp, paisa, minimum, first_only,
         start, end, limit, used) in rows:
        coupon, _ = s.get_or_create(
            Coupon,
            {
                "description": desc,
                "kind": kind,
                "value_bp": bp,
                "value_paisa": paisa,
                "min_order_paisa": minimum,
                "first_order_only": first_only,
                "starts_at": start,
                "ends_at": end,
                "usage_limit": limit,
                "used_count": used,
                "usage_limit_per_user": 1 if first_only else None,
                "max_discount_paisa": (
                    500_000 if kind is DiscountKind.PERCENTAGE else None
                ),
                "target": (
                    DiscountTarget.SHIPPING
                    if kind is DiscountKind.FREE_SHIPPING
                    else DiscountTarget.ORDER
                ),
            },
            code=code,
        )
        s.coupons.append(coupon)


def _automatic_rules(s, now: datetime) -> None:
    s.get_or_create(
        DiscountRule,
        {
            "description": "10% off everything in Decor & Small Goods",
            "kind": DiscountKind.PERCENTAGE,
            "target": DiscountTarget.CATEGORY,
            "value_bp": 1000,
            "config": {"category_slugs": ["decor"]},
            "priority": 50,
            "starts_at": now - timedelta(days=10),
            "ends_at": now + timedelta(days=20),
        },
        name="Decor Week",
    )
    s.get_or_create(
        DiscountRule,
        {
            "description": "Buy two chopping boards, get a third free",
            "kind": DiscountKind.BUY_X_GET_Y,
            "target": DiscountTarget.CATEGORY,
            "config": {"buy": 2, "get": 1, "category_slugs": ["chopping-boards"]},
            "priority": 40,
            "starts_at": now - timedelta(days=5),
        },
        name="Chopping Board 3 for 2",
    )


def _flash_sale(s, now: datetime) -> None:
    sale, created = s.get_or_create(
        FlashSale,
        {
            "name": "Dining Flash Sale",
            "description": "Two days only on selected dining pieces.",
            "discount_bp": 2500,
            # Already running, so the storefront countdown has something to
            # count down to the moment the app starts.
            "starts_at": now - timedelta(hours=6),
            "ends_at": now + timedelta(hours=42),
            "is_active": True,
            "max_units": 100,
            "units_sold": s.rng.randint(18, 62),
        },
        slug="dining-flash",
    )
    if created:
        dining = [
            p for p in s.products
            if p.category and p.category.path.startswith("dining")
        ][:8]
        for product in dining:
            s.db.add(FlashSaleItem(flash_sale_id=sale.id, product_id=product.id))


def _bundles(s) -> None:
    def by_slug_fragment(fragment: str, limit: int = 1):
        return [p for p in s.products if fragment in p.slug][:limit]

    definitions = [
        ("Dining Set", "dining-set", "Table and four chairs, priced together.",
         1500, [("dining-table", 1), ("dining-chair", 4)]),
        ("Kitchen Starter", "kitchen-starter", "Board, serving board and utensils.",
         1200, [("chopping-board", 1), ("serving-board", 1), ("utensil", 1)]),
    ]
    for name, slug, description, discount_bp, members in definitions:
        bundle, created = s.get_or_create(
            Bundle,
            {"name": name, "description": description, "discount_bp": discount_bp},
            slug=slug,
        )
        if not created:
            continue
        for fragment, quantity in members:
            for product in by_slug_fragment(fragment):
                s.db.add(BundleItem(
                    bundle_id=bundle.id, product_id=product.id, quantity=quantity
                ))


def _gift_cards(s, now: datetime) -> None:
    # These demo cards are addressed to seeded customers, who do not exist in
    # production (real cards are issued when a customer buys one). Skip them
    # there rather than crash on an empty customer list.
    if not s.users:
        return
    for i in range(8):
        code = f"WCGIFT{1000 + i}"
        if s.db.scalar(select(GiftCard).where(GiftCard.code == code)):
            continue

        amount = s.rng.choice([500_000, 1_000_000, 2_500_000, 5_000_000])
        spent = s.rng.choice([0, 0, amount // 3, amount // 2, amount])
        recipient = s.rng.choice(s.users)

        card = GiftCard(
            code=code,
            initial_balance_paisa=amount,
            balance_paisa=amount - spent,
            status=(
                GiftCardStatus.REDEEMED if spent >= amount else GiftCardStatus.ACTIVE
            ),
            recipient_email=recipient.email,
            recipient_name=recipient.full_name,
            message="Happy birthday. Pick something you will keep.",
            expires_at=now + timedelta(days=365),
        )
        s.db.add(card)
        s.db.flush()

        # The ledger has to explain the balance, exactly like stock movements.
        s.db.add(GiftCardTransaction(
            gift_card_id=card.id, delta_paisa=amount,
            balance_after_paisa=amount, note="Issued",
        ))
        if spent:
            s.db.add(GiftCardTransaction(
                gift_card_id=card.id, delta_paisa=-spent,
                balance_after_paisa=amount - spent,
                note="Redeemed against an order",
            ))
