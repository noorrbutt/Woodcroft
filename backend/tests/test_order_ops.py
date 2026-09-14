"""Order and return lifecycle rules.

The transition tables are pure and tested directly. The loyalty credit and the
whole-order reversal touch the database, so they run against the rolled-back
session with a minimal order built by raw SQL.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text

from app.core.errors import ConflictError
from app.models.enums import LoyaltyTransactionKind, OrderStatus, ReturnStatus
from app.models.order import Order
from app.models.promotion import LoyaltyAccount, LoyaltyTransaction
from app.services.order_ops import (
    assert_order_transition,
    assert_return_transition,
    credit_loyalty_on_delivery,
    tier_for,
)


class TestOrderTransitions:
    def test_forward_moves_are_allowed(self) -> None:
        assert_order_transition(OrderStatus.PENDING, OrderStatus.CONFIRMED)
        assert_order_transition(OrderStatus.SHIPPED, OrderStatus.DELIVERED)
        assert_order_transition(OrderStatus.DELIVERED, OrderStatus.REFUNDED)

    def test_delivered_cannot_be_cancelled(self) -> None:
        with pytest.raises(ConflictError):
            assert_order_transition(OrderStatus.DELIVERED, OrderStatus.CANCELLED)

    def test_cancelling_twice_is_rejected(self) -> None:
        with pytest.raises(ConflictError):
            assert_order_transition(OrderStatus.CANCELLED, OrderStatus.CANCELLED)

    def test_refunded_is_terminal(self) -> None:
        with pytest.raises(ConflictError):
            assert_order_transition(OrderStatus.REFUNDED, OrderStatus.SHIPPED)


class TestReturnTransitions:
    def test_received_then_refunded_is_allowed(self) -> None:
        assert_return_transition(ReturnStatus.RECEIVED, ReturnStatus.REFUNDED)

    def test_refunding_twice_is_rejected(self) -> None:
        with pytest.raises(ConflictError):
            assert_return_transition(ReturnStatus.REFUNDED, ReturnStatus.REFUNDED)


class TestTiers:
    def test_thresholds(self) -> None:
        assert tier_for(0) == "bronze"
        assert tier_for(301) == "silver"
        assert tier_for(1001) == "gold"


@pytest.fixture
def delivered_order(db):
    """A user with a loyalty account and one delivered order worth 200 points."""
    user_id = db.execute(
        text(
            'INSERT INTO "user" (email, full_name, password_hash, role) '
            "VALUES ('ops@test.pk', 'Ops Tester', 'x', 'customer') RETURNING id"
        )
    ).scalar_one()
    db.execute(
        text(
            "INSERT INTO loyalty_account (user_id, points_balance, "
            "lifetime_points_earned, tier) VALUES (:u, 0, 0, 'bronze')"
        ),
        {"u": user_id},
    )
    order_id = db.execute(
        text(
            'INSERT INTO "order" (order_number, user_id, status, subtotal_paisa, '
            "  total_paisa, shipping_name, shipping_phone, shipping_line1, "
            "  shipping_city, shipping_province, loyalty_points_earned) "
            "VALUES ('WC-2026-000950', :u, 'delivered', 1000000, 1000000, "
            "  'Ops Tester', '03001234567', 'House 9', 'Karachi', 'sindh', 200) "
            "RETURNING id"
        ),
        {"u": user_id},
    ).scalar_one()
    db.flush()
    return {"user_id": user_id, "order_id": order_id}


class TestLoyaltyCredit:
    def test_credited_once_on_delivery(self, db, delivered_order) -> None:
        order = db.get(Order, delivered_order["order_id"])

        credit_loyalty_on_delivery(db, order)
        credit_loyalty_on_delivery(db, order)  # a second delivery bounce

        account = db.scalar(
            select(LoyaltyAccount).where(
                LoyaltyAccount.user_id == delivered_order["user_id"]
            )
        )
        assert account.points_balance == 200
        assert account.lifetime_points_earned == 200
        earned = db.scalar(
            select(text("count(*)"))
            .select_from(LoyaltyTransaction)
            .where(
                LoyaltyTransaction.order_id == order.id,
                LoyaltyTransaction.kind == LoyaltyTransactionKind.EARNED,
            )
        )
        assert earned == 1
