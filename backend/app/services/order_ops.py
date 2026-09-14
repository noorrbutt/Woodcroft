"""Order and return lifecycle: which transitions are legal, and the side effects
that must happen exactly once when an order changes state.

Everything here is in one module because the same work has to fire from more than
one place and must not fire twice:

* Reversing an order (stock, loyalty, coupon, sales count, payment) happens both
  when a customer cancels their own order and when staff cancel it, so it lives
  in one helper called from both.
* Refunds and restocks must be idempotent. A double-clicked admin button, or a
  status set twice, previously paid out twice and restocked twice. The transition
  tables make an illegal or repeated move raise instead of silently redoing the
  work, and the refund path also checks the ledger before paying out.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models.catalog import Product
from app.models.enums import (
    LoyaltyTransactionKind,
    MovementReason,
    OrderStatus,
    PaymentStatus,
    ReturnStatus,
)
from app.models.inventory import StockLevel, StockMovement
from app.models.order import Order, Payment, PaymentTransaction, Refund
from app.models.promotion import (
    Coupon,
    CouponRedemption,
    LoyaltyAccount,
    LoyaltyTransaction,
)


def _now() -> datetime:
    return datetime.now(UTC)


# ── Order status machine ──────────────────────────────────────────────────────
S = OrderStatus
ALLOWED_ORDER_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    S.PENDING: {S.CONFIRMED, S.PROCESSING, S.SHIPPED, S.CANCELLED},
    S.CONFIRMED: {S.PROCESSING, S.SHIPPED, S.OUT_FOR_DELIVERY, S.CANCELLED},
    S.PROCESSING: {S.SHIPPED, S.OUT_FOR_DELIVERY, S.CANCELLED},
    S.SHIPPED: {S.OUT_FOR_DELIVERY, S.DELIVERED},
    S.OUT_FOR_DELIVERY: {S.DELIVERED, S.SHIPPED},
    S.DELIVERED: {S.REFUNDED},
    S.CANCELLED: set(),
    S.REFUNDED: set(),
}

#: Once an order is in one of these, it is out for delivery or delivered and can
#: no longer be cancelled; it can only be refunded through the returns flow.
FULFILLED_STATES = {S.OUT_FOR_DELIVERY, S.DELIVERED}


def assert_order_transition(previous: OrderStatus, new: OrderStatus) -> None:
    """Raise unless ``new`` is a legal next state after ``previous``."""
    if new == previous:
        raise ConflictError(
            f"This order is already {previous.label}.", code="invalid_transition"
        )
    if new not in ALLOWED_ORDER_TRANSITIONS.get(previous, set()):
        raise ConflictError(
            f"Cannot move an order from {previous.label} to {new.label}.",
            code="invalid_transition",
        )


# ── Return status machine ─────────────────────────────────────────────────────
R = ReturnStatus
ALLOWED_RETURN_TRANSITIONS: dict[ReturnStatus, set[ReturnStatus]] = {
    R.REQUESTED: {R.APPROVED, R.REJECTED, R.CANCELLED},
    R.APPROVED: {R.IN_TRANSIT, R.RECEIVED, R.REJECTED, R.CANCELLED},
    R.IN_TRANSIT: {R.RECEIVED, R.REJECTED},
    R.RECEIVED: {R.REFUNDED, R.REJECTED},
    R.REFUNDED: set(),
    R.REJECTED: set(),
    R.CANCELLED: set(),
}


def assert_return_transition(previous: ReturnStatus, new: ReturnStatus) -> None:
    if new == previous:
        raise ConflictError(
            f"This return is already {new.value.replace('_', ' ')}.",
            code="invalid_transition",
        )
    if new not in ALLOWED_RETURN_TRANSITIONS.get(previous, set()):
        raise ConflictError(
            f"Cannot move a return from {previous.value.replace('_', ' ')} to "
            f"{new.value.replace('_', ' ')}.",
            code="invalid_transition",
        )


# ── Loyalty ───────────────────────────────────────────────────────────────────
def tier_for(lifetime_points: int) -> str:
    if lifetime_points > 1000:
        return "gold"
    if lifetime_points > 300:
        return "silver"
    return "bronze"


def credit_loyalty_on_delivery(db: Session, order: Order) -> None:
    """Credit the points an order earned, once, on its first delivery.

    Guarded by an existence check on an EARNED transaction for the order, so a
    delivered->shipped->delivered bounce cannot credit twice.
    """
    if not order.user_id or not order.loyalty_points_earned:
        return

    already = db.scalar(
        select(func.count())
        .select_from(LoyaltyTransaction)
        .where(
            LoyaltyTransaction.order_id == order.id,
            LoyaltyTransaction.kind == LoyaltyTransactionKind.EARNED,
        )
    )
    if already:
        return

    account = db.scalar(
        select(LoyaltyAccount)
        .where(LoyaltyAccount.user_id == order.user_id)
        .with_for_update()
    )
    if account is None:
        account = LoyaltyAccount(user_id=order.user_id)
        db.add(account)
        db.flush()

    account.points_balance += order.loyalty_points_earned
    account.lifetime_points_earned += order.loyalty_points_earned
    account.tier = tier_for(account.lifetime_points_earned)
    db.add(
        LoyaltyTransaction(
            account_id=account.id,
            order_id=order.id,
            kind=LoyaltyTransactionKind.EARNED,
            delta_points=order.loyalty_points_earned,
            balance_after=account.points_balance,
            note=f"Earned on {order.order_number}",
        )
    )


# ── Payment ledger ────────────────────────────────────────────────────────────
def record_payment_refund(db: Session, order: Order, amount_paisa: int) -> None:
    """Reflect a refund on the payment row and its ledger.

    Without this the order ledger and the payment ledger disagree and every
    partial refund reads as an unexplained difference during reconciliation.
    """
    if amount_paisa <= 0:
        return
    payment = db.scalar(
        select(Payment)
        .where(Payment.order_id == order.id)
        .order_by(Payment.created_at)
        .with_for_update()
    )
    if payment is None:
        return
    payment.refunded_paisa = min(
        payment.amount_paisa, payment.refunded_paisa + amount_paisa
    )
    payment.status = (
        PaymentStatus.REFUNDED
        if payment.refunded_paisa >= payment.amount_paisa
        else PaymentStatus.PARTIALLY_REFUNDED
    )
    db.add(
        PaymentTransaction(
            payment_id=payment.id,
            kind="refund",
            amount_paisa=amount_paisa,
            message=f"Refund on {order.order_number}",
        )
    )


# ── Whole-order reversal ──────────────────────────────────────────────────────
def reverse_order(
    db: Session,
    order: Order,
    *,
    actor_id: uuid.UUID | None = None,
    note: str | None = None,
) -> None:
    """Undo the side effects of a placed order when it is cancelled.

    Restocks, credits redeemed loyalty points back, releases the coupon hold,
    decrements sales counts and voids the pending payment. Called once per
    cancellation from both the customer and the admin path.
    """
    _restock(db, order, actor_id=actor_id, note=note)
    _refund_redeemed_loyalty(db, order)
    _release_coupon(db, order)
    _decrement_sales(db, order)
    _void_payments(db, order)


def _restock(
    db: Session, order: Order, *, actor_id: uuid.UUID | None, note: str | None
) -> None:
    for item in order.items:
        if item.variant_id is None:
            continue
        level = db.scalar(
            select(StockLevel)
            .where(StockLevel.variant_id == item.variant_id)
            .with_for_update()
        )
        if level is None:
            continue
        level.on_hand += item.quantity
        db.add(
            StockMovement(
                variant_id=item.variant_id,
                delta=item.quantity,
                balance_after=level.on_hand,
                reason=MovementReason.CANCELLATION,
                order_id=order.id,
                actor_id=actor_id,
                note=note or f"Order {order.order_number} cancelled",
            )
        )


def _refund_redeemed_loyalty(db: Session, order: Order) -> None:
    if not order.user_id or not order.loyalty_points_redeemed:
        return
    account = db.scalar(
        select(LoyaltyAccount)
        .where(LoyaltyAccount.user_id == order.user_id)
        .with_for_update()
    )
    if account is None:
        return
    account.points_balance += order.loyalty_points_redeemed
    db.add(
        LoyaltyTransaction(
            account_id=account.id,
            order_id=order.id,
            kind=LoyaltyTransactionKind.REFUNDED,
            delta_points=order.loyalty_points_redeemed,
            balance_after=account.points_balance,
            note=f"Points returned from cancelled {order.order_number}",
        )
    )


def _release_coupon(db: Session, order: Order) -> None:
    if not order.coupon_code:
        return
    coupon = db.scalar(
        select(Coupon).where(Coupon.code == order.coupon_code).with_for_update()
    )
    if coupon is not None and coupon.used_count:
        coupon.used_count = max(0, coupon.used_count - 1)
    redemption = db.scalar(
        select(CouponRedemption).where(CouponRedemption.order_id == order.id)
    )
    if redemption is not None:
        db.delete(redemption)


def _decrement_sales(db: Session, order: Order) -> None:
    by_product: dict[uuid.UUID, int] = {}
    for item in order.items:
        if item.product_id is None:
            continue
        by_product[item.product_id] = by_product.get(item.product_id, 0) + item.quantity
    for product_id, sold in by_product.items():
        product = db.get(Product, product_id)
        if product is not None:
            product.sales_count = max(0, (product.sales_count or 0) - sold)


def _void_payments(db: Session, order: Order) -> None:
    for payment in order.payments:
        if payment.status in (PaymentStatus.PENDING, PaymentStatus.AUTHORIZED):
            payment.status = PaymentStatus.CANCELLED
            db.add(
                PaymentTransaction(
                    payment_id=payment.id,
                    kind="void",
                    amount_paisa=payment.amount_paisa,
                    message=f"Order {order.order_number} cancelled",
                )
            )
