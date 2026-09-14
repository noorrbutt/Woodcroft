"""Seed order history, shipments, returns and refunds.

Every total here is produced by ``services.pricing.quote``, the same function
the live checkout uses. That matters more than it sounds: if the seeder invented
its own arithmetic, the admin revenue dashboard, the tax report and the invoice
PDFs would all disagree with each other, and every analytics screen would be
quietly wrong while looking perfectly plausible.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.catalog import Product, ProductVariant
from app.models.enums import (
    Courier,
    MovementReason,
    OrderStatus,
    PakistanProvince,
    PaymentMethodCode,
    PaymentStatus,
    ReturnReason,
    ReturnStatus,
    ShipmentStatus,
    TaxMode,
)
from app.models.identity import Address
from app.models.inventory import StockLevel, StockMovement
from app.models.order import (
    Order,
    OrderEvent,
    OrderItem,
    Payment,
    Refund,
    ReturnItem,
    ReturnRequest,
    Shipment,
    ShipmentItem,
)
from app.models.promotion import CouponRedemption
from app.services.pricing import (
    CouponInput,
    LineInput,
    PersonalizationChoice,
    QuoteRequest,
    quote,
)

GST_BP = 1800
MONTHS_OF_HISTORY = 18

#: Roughly how a real furniture shop's orders sit at any moment. Most are
#: delivered; a handful are mid-flight; a few went wrong.
STATUS_MIX: list[tuple[OrderStatus, float]] = [
    (OrderStatus.DELIVERED, 0.58),
    (OrderStatus.SHIPPED, 0.09),
    (OrderStatus.OUT_FOR_DELIVERY, 0.04),
    (OrderStatus.PROCESSING, 0.08),
    (OrderStatus.CONFIRMED, 0.06),
    (OrderStatus.PENDING, 0.05),
    (OrderStatus.CANCELLED, 0.06),
    (OrderStatus.REFUNDED, 0.04),
]

SHIPPING_BY_PROVINCE = {
    PakistanProvince.PUNJAB: 45_000,
    PakistanProvince.ISLAMABAD: 45_000,
    PakistanProvince.SINDH: 75_000,
    PakistanProvince.KHYBER_PAKHTUNKHWA: 85_000,
    PakistanProvince.BALOCHISTAN: 120_000,
    PakistanProvince.GILGIT_BALTISTAN: 120_000,
    PakistanProvince.AZAD_JAMMU_KASHMIR: 120_000,
}

FREE_SHIPPING_OVER = 2_000_000
COD_SURCHARGE = 20_000


def seed_orders(s, count: int = 260) -> None:
    counters = {"orders": 0, "shipments": 0, "returns": 0, "refunds": 0}
    sequence = _next_order_number(s)

    sellable = [
        v for v in s.variants
        if s.db.scalar(
            select(StockLevel.on_hand).where(StockLevel.variant_id == v.id)
        )
    ]
    if not sellable:
        sellable = s.variants

    for i in range(count):
        placed = _placed_at(s, i, count)
        status = _weighted_status(s)
        order = _make_order(s, sequence + i, placed, status, sellable)
        if order is None:
            continue
        counters["orders"] += 1

        if status in (OrderStatus.SHIPPED, OrderStatus.OUT_FOR_DELIVERY,
                      OrderStatus.DELIVERED, OrderStatus.REFUNDED):
            counters["shipments"] += _make_shipments(s, order, status)

        if status is OrderStatus.DELIVERED and s.rng.random() < 0.09:
            counters["returns"] += 1
            _make_return(s, order)

        if status is OrderStatus.REFUNDED:
            counters["refunds"] += 1
            _make_refund(s, order)

    s.db.flush()
    s.log(
        f"{counters['orders']} orders over {MONTHS_OF_HISTORY} months, "
        f"{counters['shipments']} shipments, {counters['returns']} returns, "
        f"{counters['refunds']} refunds"
    )


def _next_order_number(s) -> int:
    existing = s.db.scalar(select(Order.order_number).order_by(Order.order_number.desc()))
    if not existing:
        return 1
    try:
        return int(existing.split("-")[-1]) + 1
    except (ValueError, IndexError):
        return 1


def _placed_at(s, index: int, total: int) -> datetime:
    """Spread orders over the history window, weighted towards recent months.

    A flat distribution makes every trend chart a straight line, which tells
    you nothing about whether the chart works.
    """
    now = datetime.now(UTC)
    progress = index / max(1, total - 1)
    # Squaring pulls the distribution towards the present.
    days_ago = int((1 - progress ** 0.65) * MONTHS_OF_HISTORY * 30)
    jitter = s.rng.randint(-4, 4)
    days_ago = max(0, days_ago + jitter)
    return now - timedelta(
        days=days_ago,
        hours=s.rng.randint(8, 22),
        minutes=s.rng.randint(0, 59),
    )


def _weighted_status(s) -> OrderStatus:
    roll = s.rng.random()
    cumulative = 0.0
    for status, weight in STATUS_MIX:
        cumulative += weight
        if roll <= cumulative:
            return status
    return OrderStatus.DELIVERED


def _make_order(s, number: int, placed: datetime, status: OrderStatus,
                sellable: list[ProductVariant]) -> Order | None:
    user = s.rng.choice(s.users)
    address = s.db.scalar(
        select(Address).where(Address.user_id == user.id).limit(1)
    )
    if address is None:
        return None

    line_count = s.rng.choices([1, 2, 3, 4], weights=[52, 28, 14, 6])[0]
    chosen = s.rng.sample(sellable, min(line_count, len(sellable)))

    lines: list[LineInput] = []
    meta: list[dict] = []

    for variant in chosen:
        product = s.db.get(Product, variant.product_id)
        if product is None:
            continue
        quantity = s.rng.choices([1, 2, 4], weights=[74, 20, 6])[0]
        unit = variant.price_paisa or product.base_price_paisa

        personalizations: tuple[PersonalizationChoice, ...] = ()
        if product.personalization_options and s.rng.random() < 0.18:
            option = product.personalization_options[0]
            value = s.rng.choice(
                ["For Ayesha", "Khan Family", "1998", "AK", "With love"]
            )
            personalizations = (
                PersonalizationChoice(
                    key=option.key,
                    label=option.label,
                    value=value,
                    surcharge_paisa=option.surcharge_paisa,
                    surcharge_per_char_paisa=option.surcharge_per_char_paisa,
                ),
            )

        lines.append(LineInput(
            variant_id=variant.id,
            quantity=quantity,
            unit_price_paisa=unit,
            personalizations=personalizations,
            product_id=product.id,
        ))
        meta.append({"variant": variant, "product": product})

    if not lines:
        return None

    coupon = None
    coupon_code = None
    if s.coupons and s.rng.random() < 0.22:
        candidate = s.rng.choice([c for c in s.coupons if c.code != "EXPIRED20"])
        coupon_code = candidate.code
        coupon = CouponInput(
            code=candidate.code,
            kind=candidate.kind,
            value_bp=candidate.value_bp,
            value_paisa=candidate.value_paisa,
            max_discount_paisa=candidate.max_discount_paisa,
            min_order_paisa=candidate.min_order_paisa,
        )

    goods = sum(
        (line.unit_price_paisa
         + sum(p.total_surcharge() for p in line.personalizations)) * line.quantity
        for line in lines
    )
    shipping = SHIPPING_BY_PROVINCE.get(address.province, 75_000)
    free_shipping = goods >= FREE_SHIPPING_OVER

    # The real engine. Not a reimplementation.
    priced = quote(QuoteRequest(
        lines=tuple(lines),
        tax_mode=TaxMode.INCLUSIVE,
        tax_rate_bp=GST_BP,
        coupon=coupon,
        shipping_paisa=shipping,
        free_shipping=free_shipping,
        cod_surcharge_paisa=COD_SURCHARGE,
    ))

    order = Order(
        order_number=f"WC-{placed.year}-{number:06d}",
        user_id=user.id,
        status=status,
        subtotal_paisa=priced.subtotal_paisa,
        discount_paisa=priced.discount_paisa,
        shipping_paisa=priced.shipping_paisa,
        cod_surcharge_paisa=priced.cod_surcharge_paisa,
        tax_paisa=priced.tax_paisa,
        total_paisa=priced.total_paisa,
        tax_mode=TaxMode.INCLUSIVE,
        tax_rate_bp=GST_BP,
        coupon_code=coupon_code if priced.discount_paisa else None,
        loyalty_points_earned=priced.loyalty_points_earned,
        shipping_name=address.full_name,
        shipping_phone=address.phone,
        shipping_line1=address.line1,
        shipping_area=address.area,
        shipping_landmark=address.landmark,
        shipping_city=address.city,
        shipping_province=address.province,
        shipping_postal_code=address.postal_code,
        shipping_method="Standard",
        courier=s.rng.choice(list(Courier)),
        placed_at=placed,
        customer_note=(
            s.rng.choice([
                "Please call before delivery.",
                "Leave with the guard if we are out.",
                "Deliver after 5pm please.",
            ]) if s.rng.random() < 0.2 else None
        ),
        # A few high value orders get flagged, so the fraud queue is not empty.
        is_flagged=priced.total_paisa > 25_000_000 and s.rng.random() < 0.4,
        fraud_flags=(
            {"high_value": True} if priced.total_paisa > 25_000_000 else {}
        ),
    )
    s.db.add(order)
    s.db.flush()

    for line, quote_line, info in zip(lines, priced.lines, meta, strict=True):
        product = info["product"]
        variant = info["variant"]
        primary = next((i for i in product.images if i.is_primary), None)

        s.db.add(OrderItem(
            order_id=order.id,
            product_id=product.id,
            variant_id=variant.id,
            product_name=product.name,
            variant_name=variant.name,
            sku=variant.sku,
            image_path=primary.base_path if primary else None,
            quantity=line.quantity,
            unit_price_paisa=line.unit_price_paisa,
            personalization_surcharge_paisa=quote_line.personalization_surcharge_paisa,
            discount_paisa=quote_line.total_discount_paisa,
            tax_paisa=quote_line.tax_paisa,
            tax_rate_bp=quote_line.tax_rate_bp,
            line_total_paisa=quote_line.subtotal_paisa,
            personalization={
                p.key: {
                    "label": p.label,
                    "value": p.value,
                    "surcharge_paisa": p.total_surcharge(),
                }
                for p in line.personalizations
            },
            quantity_shipped=(
                line.quantity
                if status in (OrderStatus.DELIVERED, OrderStatus.SHIPPED,
                              OrderStatus.OUT_FOR_DELIVERY)
                else 0
            ),
        ))

    _payment(s, order, status)
    _timeline(s, order, status, placed)
    _stock_movements(s, order, status, meta, lines)

    if coupon_code and priced.discount_paisa:
        s.db.add(CouponRedemption(
            coupon_id=next(c.id for c in s.coupons if c.code == coupon_code),
            order_id=order.id,
            user_id=user.id,
            discount_paisa=priced.discount_paisa,
        ))

    # The session runs with autoflush off, so order.items would come back empty
    # for the shipment and return builders without this.
    s.db.flush()
    return order


def _payment(s, order: Order, status: OrderStatus) -> None:
    paid = status in (OrderStatus.DELIVERED, OrderStatus.REFUNDED)
    s.db.add(Payment(
        order_id=order.id,
        method_code=PaymentMethodCode.COD,
        status=(
            PaymentStatus.REFUNDED if status is OrderStatus.REFUNDED
            else PaymentStatus.PAID if paid
            else PaymentStatus.CANCELLED if status is OrderStatus.CANCELLED
            else PaymentStatus.PENDING
        ),
        amount_paisa=order.total_paisa,
        refunded_paisa=order.total_paisa if status is OrderStatus.REFUNDED else 0,
        captured_at=order.placed_at + timedelta(days=4) if paid else None,
        provider_reference=f"COD-{order.order_number}",
    ))


def _timeline(s, order: Order, status: OrderStatus, placed: datetime) -> None:
    """Build a plausible event trail up to the order's current state."""
    journey = [
        (OrderStatus.PENDING, "Order placed", timedelta()),
        (OrderStatus.CONFIRMED, "Order confirmed over the phone", timedelta(hours=6)),
        (OrderStatus.PROCESSING, "In the workshop", timedelta(days=1)),
        (OrderStatus.SHIPPED, "Dispatched", timedelta(days=4)),
        (OrderStatus.OUT_FOR_DELIVERY, "Out for delivery", timedelta(days=6)),
        (OrderStatus.DELIVERED, "Delivered", timedelta(days=7)),
    ]
    order_index = {step[0]: i for i, step in enumerate(journey)}
    stop_at = order_index.get(status, len(journey) - 1)

    previous = None
    for target, message, offset in journey[: stop_at + 1]:
        s.db.add(OrderEvent(
            order_id=order.id,
            event_type="status_change",
            message=message,
            from_status=previous,
            to_status=target,
            created_at=placed + offset,
        ))
        previous = target

    if status is OrderStatus.DELIVERED:
        order.delivered_at = placed + timedelta(days=7)
        order.confirmed_at = placed + timedelta(hours=6)
    elif status is OrderStatus.CANCELLED:
        order.cancelled_at = placed + timedelta(days=s.rng.randint(1, 3))
        order.cancellation_reason = s.rng.choice([
            "Customer changed their mind",
            "Could not reach customer to confirm",
            "Item no longer available in this finish",
        ])
        s.db.add(OrderEvent(
            order_id=order.id, event_type="status_change",
            message=f"Cancelled: {order.cancellation_reason}",
            from_status=OrderStatus.PENDING, to_status=OrderStatus.CANCELLED,
            created_at=order.cancelled_at,
        ))
    elif status is OrderStatus.REFUNDED:
        order.delivered_at = placed + timedelta(days=7)
        order.confirmed_at = placed + timedelta(hours=6)
    elif status in (OrderStatus.CONFIRMED, OrderStatus.PROCESSING,
                    OrderStatus.SHIPPED, OrderStatus.OUT_FOR_DELIVERY):
        order.confirmed_at = placed + timedelta(hours=6)


def _stock_movements(s, order: Order, status: OrderStatus, meta, lines) -> None:
    """Record the stock effect, so the ledger reconciles with on_hand."""
    if status in (OrderStatus.CANCELLED, OrderStatus.PENDING):
        return

    for info, line in zip(meta, lines, strict=True):
        variant = info["variant"]
        level = s.db.scalar(
            select(StockLevel).where(StockLevel.variant_id == variant.id)
        )
        if level is None or level.on_hand < line.quantity:
            continue
        level.on_hand -= line.quantity
        s.db.add(StockMovement(
            variant_id=variant.id,
            delta=-line.quantity,
            balance_after=level.on_hand,
            reason=MovementReason.SALE,
            order_id=order.id,
            created_at=order.placed_at,
        ))


def _make_shipments(s, order: Order, status: OrderStatus) -> int:
    items = list(order.items)
    if not items:
        return 0

    # Roughly one order in six ships in two boxes, which is what makes the
    # partial shipment UI worth having.
    split = len(items) > 1 and s.rng.random() < 0.18
    groups = [items[: len(items) // 2], items[len(items) // 2 :]] if split else [items]

    shipment_status = {
        OrderStatus.SHIPPED: ShipmentStatus.IN_TRANSIT,
        OrderStatus.OUT_FOR_DELIVERY: ShipmentStatus.OUT_FOR_DELIVERY,
        OrderStatus.DELIVERED: ShipmentStatus.DELIVERED,
        OrderStatus.REFUNDED: ShipmentStatus.DELIVERED,
    }.get(status, ShipmentStatus.DISPATCHED)

    made = 0
    for index, group in enumerate(groups):
        if not group:
            continue
        courier = order.courier or Courier.TCS
        shipment = Shipment(
            order_id=order.id,
            courier=courier,
            tracking_number=f"{courier.value.upper()}{s.rng.randint(10**9, 10**10 - 1)}",
            status=shipment_status,
            cod_amount_paisa=order.total_paisa if index == 0 else 0,
            dispatched_at=order.placed_at + timedelta(days=4 + index),
            delivered_at=(
                order.placed_at + timedelta(days=7 + index)
                if shipment_status is ShipmentStatus.DELIVERED else None
            ),
            estimated_delivery=order.placed_at + timedelta(days=6 + index),
        )
        s.db.add(shipment)
        s.db.flush()
        for item in group:
            s.db.add(ShipmentItem(
                shipment_id=shipment.id,
                order_item_id=item.id,
                quantity=item.quantity,
            ))
        made += 1
    return made


def _make_return(s, order: Order) -> None:
    items = list(order.items)
    if not items:
        return

    item = s.rng.choice(items)
    status = s.rng.choice([
        ReturnStatus.REQUESTED, ReturnStatus.APPROVED,
        ReturnStatus.RECEIVED, ReturnStatus.REFUNDED, ReturnStatus.REJECTED,
    ])
    reason = s.rng.choice(list(ReturnReason))
    requested = (order.delivered_at or order.placed_at) + timedelta(
        days=s.rng.randint(1, 12)
    )

    request = ReturnRequest(
        return_number=f"WC-RET-{s.rng.randint(100000, 999999)}",
        order_id=order.id,
        user_id=order.user_id,
        status=status,
        reason=reason,
        customer_note=s.rng.choice([
            "One leg arrived with a chip in the finish.",
            "The colour is much darker than it looked online.",
            "Too large for the space, my mistake.",
            "Arrived with a crack along the top edge.",
        ]),
        approved_at=requested + timedelta(days=1) if status is not ReturnStatus.REQUESTED else None,
        received_at=(
            requested + timedelta(days=5)
            if status in (ReturnStatus.RECEIVED, ReturnStatus.REFUNDED) else None
        ),
        resolved_at=requested + timedelta(days=7) if status is ReturnStatus.REFUNDED else None,
        admin_note="Inspected, damage confirmed." if status is ReturnStatus.RECEIVED else None,
    )
    s.db.add(request)
    s.db.flush()

    s.db.add(ReturnItem(
        return_request_id=request.id,
        order_item_id=item.id,
        quantity=1,
        refundable_paisa=item.line_total_paisa // max(1, item.quantity),
        restock=reason not in (ReturnReason.DAMAGED, ReturnReason.DEFECTIVE),
    ))


def _make_refund(s, order: Order) -> None:
    order.refunded_paisa = order.total_paisa
    payment = s.db.scalar(select(Payment).where(Payment.order_id == order.id))
    s.db.add(Refund(
        order_id=order.id,
        payment_id=payment.id if payment else None,
        amount_paisa=order.total_paisa,
        reason=s.rng.choice([
            "Damaged in transit",
            "Customer cancelled after dispatch",
            "Wrong finish delivered",
        ]),
        # COD money is refunded out of band, so store credit is the honest
        # default rather than pretending a card was reversed.
        method="store_credit",
        processed_by_id=s.admin.id if s.admin else None,
        processed_at=(order.delivered_at or order.placed_at) + timedelta(days=9),
    ))
    s.db.add(OrderEvent(
        order_id=order.id,
        event_type="refund",
        message=f"Refunded {order.total_paisa / 100:,.0f} PKR to store credit",
        to_status=OrderStatus.REFUNDED,
        created_at=(order.delivered_at or order.placed_at) + timedelta(days=9),
    ))
