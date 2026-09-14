"""Scheduled and queued job handlers.

Every handler must be idempotent. A worker can crash after doing the work but
before marking the job done, in which case the job runs again.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.cart import AbandonedCart, Cart
from app.models.catalog import BackInStockSubscription, PriceWatch, Product, ProductVariant
from app.models.enums import (
    NotificationChannel,
    ProductStatus,
    ReservationStatus,
)
from app.models.identity import User
from app.models.inventory import StockLevel, StockReservation
from app.models.order import Order, OrderItem
from app.models.promotion import FlashSale
from app.workers.runner import handler

log = logging.getLogger("woodcroft.jobs")


def _now() -> datetime:
    return datetime.now(UTC)


@handler("sweep_expired_reservations")
def sweep_expired_reservations(db: Session, payload: dict[str, Any]) -> None:
    """Release checkout holds that were never completed.

    Without this, an abandoned checkout would keep stock locked forever and the
    last dining table would look sold out to everyone.
    """
    expired = db.scalars(
        select(StockReservation).where(
            StockReservation.status == ReservationStatus.ACTIVE,
            StockReservation.expires_at < _now(),
        )
    ).all()

    for reservation in expired:
        stock = db.scalar(
            select(StockLevel)
            .where(StockLevel.variant_id == reservation.variant_id)
            .with_for_update()
        )
        if stock is not None:
            # max() guards against the counter going negative if a release was
            # partially applied before a crash.
            stock.reserved = max(0, stock.reserved - reservation.quantity)
        reservation.status = ReservationStatus.EXPIRED
        reservation.released_at = _now()

    if expired:
        log.info("released %d expired reservations", len(expired))


@handler("detect_abandoned_carts")
def detect_abandoned_carts(db: Session, payload: dict[str, Any]) -> None:
    """Flag carts that went quiet, and queue the first reminder."""
    from app.workers.runner import enqueue

    cutoff = _now() - timedelta(hours=payload.get("idle_hours", 4))

    carts = db.scalars(
        select(Cart).where(
            Cart.is_active.is_(True),
            Cart.last_activity_at < cutoff,
            Cart.user_id.is_not(None),
            ~Cart.id.in_(select(AbandonedCart.cart_id)),
        )
    ).all()

    for cart in carts:
        if not cart.items:
            continue
        user = db.get(User, cart.user_id) if cart.user_id else None
        value = sum(item.line_total_paisa for item in cart.items)

        db.add(
            AbandonedCart(
                cart_id=cart.id,
                user_id=cart.user_id,
                email=user.email if user else None,
                cart_value_paisa=value,
                item_count=sum(i.quantity for i in cart.items),
            )
        )
        enqueue(
            db,
            "send_abandoned_cart_reminder",
            {"cart_id": str(cart.id), "sequence": 1},
            run_after=_now() + timedelta(hours=1),
            dedupe_key=f"abandoned:{cart.id}:1",
        )

    if carts:
        log.info("flagged %d abandoned carts", len(carts))


@handler("send_abandoned_cart_reminder")
def send_abandoned_cart_reminder(db: Session, payload: dict[str, Any]) -> None:
    import uuid as _uuid

    from app.services import notifications

    cart_id = _uuid.UUID(payload["cart_id"])
    record = db.scalar(select(AbandonedCart).where(AbandonedCart.cart_id == cart_id))
    if record is None or record.recovered_at is not None or not record.email:
        return

    cart = db.get(Cart, cart_id)
    if cart is None or not cart.is_active or not cart.items:
        return

    notifications.email(
        db,
        "abandoned_cart",
        record.email,
        user_id=record.user_id,
        context={
            "cart_url": f"{settings.PUBLIC_URL}/cart",
            "item_count": record.item_count,
            "cart_value_paisa": record.cart_value_paisa,
            "sequence": payload.get("sequence", 1),
        },
    )
    record.reminder_count += 1
    record.last_reminder_at = _now()


@handler("notify_back_in_stock")
def notify_back_in_stock(db: Session, payload: dict[str, Any]) -> None:
    """Tell everyone waiting that a variant is buyable again."""
    import uuid as _uuid

    from app.services import notifications

    variant_id = _uuid.UUID(payload["variant_id"])
    stock = db.scalar(select(StockLevel).where(StockLevel.variant_id == variant_id))
    if stock is None or stock.available <= 0:
        return

    variant = db.get(ProductVariant, variant_id)
    if variant is None:
        return
    product = db.get(Product, variant.product_id)
    if product is None:
        return

    waiting = db.scalars(
        select(BackInStockSubscription).where(
            BackInStockSubscription.variant_id == variant_id,
            BackInStockSubscription.notified_at.is_(None),
        )
    ).all()

    for subscription in waiting:
        notifications.email(
            db,
            "back_in_stock",
            subscription.email,
            user_id=subscription.user_id,
            context={
                "product_name": product.name,
                "product_url": f"{settings.PUBLIC_URL}/product/{product.slug}",
            },
        )
        subscription.notified_at = _now()


@handler("notify_price_drop")
def notify_price_drop(db: Session, payload: dict[str, Any]) -> None:
    """Alert watchers whose product is now cheaper than when they saved it."""
    from app.services import notifications

    watches = db.scalars(
        select(PriceWatch).where(PriceWatch.notified_at.is_(None))
    ).all()

    for watch in watches:
        product = db.get(Product, watch.product_id)
        user = db.get(User, watch.user_id)
        if product is None or user is None:
            continue
        if product.base_price_paisa >= watch.watched_price_paisa:
            continue

        notifications.email(
            db,
            "price_drop",
            user.email,
            user=user,
            context={
                "product_name": product.name,
                "product_url": f"{settings.PUBLIC_URL}/product/{product.slug}",
                "old_price_paisa": watch.watched_price_paisa,
                "new_price_paisa": product.base_price_paisa,
            },
        )
        watch.notified_at = _now()


@handler("send_review_reminders")
def send_review_reminders(db: Session, payload: dict[str, Any]) -> None:
    """Ask for a review a while after delivery, once per order."""
    from app.models.review import Review
    from app.services import notifications
    from app.workers.runner import enqueue

    days = payload.get("days_after_delivery", 7)
    window_start = _now() - timedelta(days=days + 1)
    window_end = _now() - timedelta(days=days)

    orders = db.scalars(
        select(Order).where(
            Order.delivered_at.is_not(None),
            Order.delivered_at.between(window_start, window_end),
            Order.user_id.is_not(None),
        )
    ).all()

    for order in orders:
        user = db.get(User, order.user_id) if order.user_id else None
        if user is None:
            continue

        already = db.scalar(
            select(func.count())
            .select_from(Review)
            .join(OrderItem, Review.order_item_id == OrderItem.id)
            .where(OrderItem.order_id == order.id)
        )
        if already:
            continue

        notifications.email(
            db,
            "review_reminder",
            user.email,
            user=user,
            order_id=order.id,
            context={
                "order_number": order.order_number,
                "review_url": f"{settings.PUBLIC_URL}/account/orders/{order.id}",
            },
        )


@handler("publish_scheduled_products")
def publish_scheduled_products(db: Session, payload: dict[str, Any]) -> None:
    """Apply scheduled publish and unpublish times."""
    now = _now()

    published = db.execute(
        update(Product)
        .where(
            Product.publish_at.is_not(None),
            Product.publish_at <= now,
            Product.status == ProductStatus.DRAFT,
        )
        .values(status=ProductStatus.ACTIVE, published_at=now, publish_at=None)
    ).rowcount

    archived = db.execute(
        update(Product)
        .where(
            Product.unpublish_at.is_not(None),
            Product.unpublish_at <= now,
            Product.status == ProductStatus.ACTIVE,
        )
        .values(status=ProductStatus.ARCHIVED, unpublish_at=None)
    ).rowcount

    if published or archived:
        log.info("scheduled publish: +%d, -%d", published, archived)


@handler("activate_flash_sales")
def activate_flash_sales(db: Session, payload: dict[str, Any]) -> None:
    """Turn flash sales on and off at their boundaries."""
    now = _now()

    db.execute(
        update(FlashSale)
        .where(
            FlashSale.starts_at <= now,
            FlashSale.ends_at > now,
            FlashSale.is_active.is_(False),
        )
        .values(is_active=True)
    )
    db.execute(
        update(FlashSale)
        .where(FlashSale.ends_at <= now, FlashSale.is_active.is_(True))
        .values(is_active=False)
    )


@handler("expire_guest_sessions")
def expire_guest_sessions(db: Session, payload: dict[str, Any]) -> None:
    """Clear out guest sessions and their carts once they lapse."""
    from app.models.identity import GuestSession

    stale = db.scalars(
        select(GuestSession).where(
            GuestSession.expires_at < _now() - timedelta(days=7),
            GuestSession.merged_at.is_(None),
        )
    ).all()
    for guest in stale:
        db.delete(guest)


#: Jobs the scheduler re-queues on a fixed cadence, with the gap between runs.
RECURRING: dict[str, timedelta] = {
    "sweep_expired_reservations": timedelta(minutes=2),
    "detect_abandoned_carts": timedelta(hours=1),
    "publish_scheduled_products": timedelta(minutes=5),
    "activate_flash_sales": timedelta(minutes=1),
    "send_review_reminders": timedelta(hours=6),
    "notify_price_drop": timedelta(hours=3),
    "expire_guest_sessions": timedelta(days=1),
}


@handler("schedule_recurring")
def schedule_recurring(db: Session, payload: dict[str, Any]) -> None:
    """Re-arm every recurring job, then re-arm itself.

    A self-rescheduling job rather than a cron table: it keeps the whole
    schedule in one place and survives restarts, because the next tick is
    already sitting in the queue.
    """
    from app.workers.runner import enqueue

    now = _now()
    for job_type, interval in RECURRING.items():
        enqueue(
            db,
            job_type,
            run_after=now,
            dedupe_key=f"recurring:{job_type}:{int(now.timestamp() // interval.total_seconds())}",
        )

    enqueue(
        db,
        "schedule_recurring",
        run_after=now + timedelta(minutes=1),
        priority=1,
        dedupe_key=f"scheduler:{int(now.timestamp() // 60) + 1}",
    )
