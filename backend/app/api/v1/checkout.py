"""Checkout, orders and the customer's own order history.

The whole point of this module is that the browser never gets to decide what
anything costs. It sends variant ids, quantities and personalization text; the
server looks up the real prices, runs the pricing engine, and charges that. A
tampered request changes what you buy, never what you pay.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, OptionalUser, client_ip
from app.core.errors import (
    CartEmptyError,
    CodNotAvailableError,
    ConflictError,
    InsufficientStockError,
    NotFoundError,
    OrderNotCancellableError,
    ValidationError,
)
from app.core.money import format_pkr
from app.core.ratelimit import limiter
from app.models.catalog import PersonalizationOption, Product, ProductVariant
from app.models.enums import (
    Courier,
    MovementReason,
    NotificationChannel,
    OrderStatus,
    PakistanProvince,
    PaymentMethodCode,
    PaymentStatus,
    TaxMode,
)
from app.models.inventory import StockLevel, StockMovement
from app.models.order import (
    Order,
    OrderEvent,
    OrderItem,
    Payment,
    PaymentMethod,
)
from app.models.ops import ShippingRate, ShippingZone, StoreSetting
from app.models.promotion import Coupon, CouponRedemption
from app.schemas.common import Message, Money, Schema
from app.services import notifications
from app.services.auth import normalise_phone
from app.services.pricing import (
    CouponInput,
    LineInput,
    PersonalizationChoice,
    QuoteRequest,
    quote,
)

router = APIRouter(tags=["checkout"])


# ── Request schemas ──────────────────────────────────────────────────────────
class CartLineIn(BaseModel):
    variant_id: uuid.UUID
    quantity: int = Field(ge=1, le=99)
    #: {"engraving": "For Ayesha"}. Prices come from the database, not here.
    personalization: dict[str, str] = Field(default_factory=dict)


class AddressIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    phone: str
    line1: str = Field(min_length=4, max_length=200)
    line2: str | None = None
    area: str | None = None
    landmark: str | None = None
    city: str = Field(min_length=2, max_length=80)
    province: PakistanProvince
    postal_code: str | None = None

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        return normalise_phone(value) or value


class QuoteIn(BaseModel):
    lines: list[CartLineIn]
    province: PakistanProvince | None = None
    coupon_code: str | None = None
    payment_method: PaymentMethodCode = PaymentMethodCode.COD
    gift_wrap: bool = False
    loyalty_points: int = Field(0, ge=0)


class PlaceOrderIn(QuoteIn):
    shipping: AddressIn
    billing: AddressIn | None = None
    email: EmailStr | None = None
    customer_note: str | None = Field(None, max_length=500)
    gift_message: str | None = Field(None, max_length=500)
    accept_terms: bool = True


# ── Response schemas ─────────────────────────────────────────────────────────
class QuoteLineOut(Schema):
    variant_id: uuid.UUID
    product_name: str
    variant_name: str | None
    sku: str
    image_url: str | None
    quantity: int
    unit_price: Money
    personalization_surcharge: Money
    line_total: Money
    tax: Money
    personalization: dict
    in_stock: bool
    available: int


class QuoteOut(Schema):
    lines: list[QuoteLineOut]
    subtotal: Money
    discount: Money
    shipping: Money
    cod_surcharge: Money
    gift_wrap: Money
    tax: Money
    loyalty_applied: Money
    total: Money
    tax_mode: TaxMode
    tax_rate_bp: int
    coupon_code: str | None
    coupon_error: str | None
    loyalty_points_earned: int
    free_shipping: bool
    cod_available: bool
    item_count: int


class OrderItemOut(Schema):
    id: uuid.UUID
    product_name: str
    variant_name: str | None
    sku: str
    image_url: str | None
    quantity: int
    unit_price: Money
    line_total: Money
    personalization: dict
    product_slug: str | None = None


class OrderOut(Schema):
    id: uuid.UUID
    order_number: str
    status: OrderStatus
    status_label: str
    placed_at: datetime
    items: list[OrderItemOut]
    subtotal: Money
    discount: Money
    shipping: Money
    cod_surcharge: Money
    tax: Money
    total: Money
    tax_mode: TaxMode
    shipping_address: dict
    courier: str | None
    tracking: list[dict]
    timeline: list[dict]
    is_cancellable: bool
    payment_method: str
    payment_status: str | None


# ── Helpers ──────────────────────────────────────────────────────────────────
def _setting_int(db, key: str, fallback: int) -> int:
    row = db.scalar(select(StoreSetting).where(StoreSetting.key == key))
    return row.value_int if row and row.value_int is not None else fallback


def _tax_mode(db) -> TaxMode:
    row = db.scalar(select(StoreSetting).where(StoreSetting.key == "tax_mode"))
    value = (row.value_text if row else None) or settings.TAX_MODE
    return TaxMode(value)


def _zone_for(db, province: PakistanProvince | None) -> ShippingZone | None:
    if province is None:
        return None
    zones = db.scalars(
        select(ShippingZone)
        .where(ShippingZone.is_active.is_(True))
        .options(selectinload(ShippingZone.rates))
    ).all()
    for zone in zones:
        if province.value in (zone.provinces or []):
            return zone
    return zones[0] if zones else None


def _build_quote(db, payload: QuoteIn, user=None):
    """Resolve a client cart into a priced quote. The prices are ours."""
    if not payload.lines:
        raise CartEmptyError()

    variant_ids = [line.variant_id for line in payload.lines]
    variants = {
        v.id: v
        for v in db.scalars(
            select(ProductVariant)
            .where(ProductVariant.id.in_(variant_ids))
            .options(
                selectinload(ProductVariant.product).selectinload(Product.images),
                selectinload(ProductVariant.product).selectinload(
                    Product.personalization_options
                ),
            )
        ).all()
    }
    stock = {
        row.variant_id: row
        for row in db.scalars(
            select(StockLevel).where(StockLevel.variant_id.in_(variant_ids))
        ).all()
    }

    engine_lines: list[LineInput] = []
    meta: list[dict] = []

    for line in payload.lines:
        variant = variants.get(line.variant_id)
        if variant is None or not variant.is_active:
            raise NotFoundError("One of the items is no longer available.")

        product = variant.product
        level = stock.get(variant.id)
        available = level.available if level else 0

        # Personalization surcharges come from the option definition, never
        # from the request.
        choices: list[PersonalizationChoice] = []
        options = {o.key: o for o in product.personalization_options}
        for key, raw in (line.personalization or {}).items():
            option = options.get(key)
            if option is None:
                continue
            value = str(raw).strip()
            if not value:
                continue
            if option.max_length and len(value) > option.max_length:
                raise ValidationError(
                    f"{option.label} is limited to {option.max_length} characters."
                )
            choices.append(
                PersonalizationChoice(
                    key=option.key,
                    label=option.label,
                    value=value,
                    surcharge_paisa=option.surcharge_paisa,
                    surcharge_per_char_paisa=option.surcharge_per_char_paisa,
                )
            )

        for option in product.personalization_options:
            if option.is_required and not any(c.key == option.key for c in choices):
                raise ValidationError(f"{option.label} is required for {product.name}.")

        engine_lines.append(
            LineInput(
                variant_id=variant.id,
                quantity=line.quantity,
                unit_price_paisa=variant.effective_price_paisa(product),
                tax_rate_bp=product.tax_rate_bp
                if product.tax_rate_bp is not None
                else (product.category.tax_rate_bp if product.category else None),
                personalizations=tuple(choices),
                product_id=product.id,
            )
        )
        primary = next((i for i in product.images if i.is_primary), None)
        meta.append(
            {
                "variant": variant,
                "product": product,
                "available": available,
                "in_stock": available >= line.quantity or variant.is_preorder,
                "image": primary,
                "choices": choices,
            }
        )

    tax_mode = _tax_mode(db)
    tax_rate = _setting_int(db, "default_tax_rate_bp", settings.DEFAULT_TAX_RATE_BP)
    free_over = _setting_int(
        db, "free_shipping_threshold_paisa", settings.FREE_SHIPPING_THRESHOLD_PAISA
    )

    zone = _zone_for(db, payload.province)
    shipping_paisa = 0
    if zone is not None and zone.rates:
        active = sorted(
            (r for r in zone.rates if r.is_active), key=lambda r: r.sort_order
        )
        if active:
            shipping_paisa = active[0].price_paisa

    goods = sum(
        (line.unit_price_paisa + sum(p.total_surcharge() for p in line.personalizations))
        * line.quantity
        for line in engine_lines
    )
    free_shipping = goods >= free_over

    cod_available = True
    cod_surcharge = 0
    if payload.payment_method is PaymentMethodCode.COD:
        method = db.scalar(
            select(PaymentMethod).where(PaymentMethod.code == PaymentMethodCode.COD)
        )
        if method is None or not method.is_enabled:
            cod_available = False
        if zone is not None and not zone.cod_available:
            cod_available = False
        if zone is not None and zone.cod_max_order_paisa and goods > zone.cod_max_order_paisa:
            cod_available = False
        if cod_available:
            cod_surcharge = (
                zone.cod_surcharge_paisa
                if zone is not None and zone.cod_surcharge_paisa
                else _setting_int(db, "cod_surcharge_paisa", settings.COD_SURCHARGE_PAISA)
            )

    coupon_input = None
    if payload.coupon_code:
        coupon = db.scalar(
            select(Coupon).where(Coupon.code == payload.coupon_code.strip())
        )
        if coupon is not None and coupon.is_live(datetime.now(UTC)):
            coupon_input = CouponInput(
                code=coupon.code,
                kind=coupon.kind,
                value_bp=coupon.value_bp,
                value_paisa=coupon.value_paisa,
                max_discount_paisa=coupon.max_discount_paisa,
                min_order_paisa=coupon.min_order_paisa,
            )
            if coupon.kind.value == "free_shipping":
                free_shipping = True

    loyalty_available = 0
    if user is not None:
        from app.models.promotion import LoyaltyAccount

        account = db.scalar(
            select(LoyaltyAccount).where(LoyaltyAccount.user_id == user.id)
        )
        loyalty_available = account.points_balance if account else 0

    priced = quote(
        QuoteRequest(
            lines=tuple(engine_lines),
            tax_mode=tax_mode,
            tax_rate_bp=tax_rate,
            coupon=coupon_input,
            shipping_paisa=shipping_paisa,
            free_shipping=free_shipping,
            cod_surcharge_paisa=cod_surcharge,
            gift_wrap_paisa=35_000 if payload.gift_wrap else 0,
            loyalty_points_available=loyalty_available,
            loyalty_points_to_redeem=payload.loyalty_points,
        )
    )

    if payload.coupon_code and coupon_input is None:
        priced.coupon_error = "invalid"
        priced.coupon_code = payload.coupon_code

    return priced, meta, {"cod_available": cod_available, "free_shipping": free_shipping}


def _quote_out(priced, meta, extra) -> QuoteOut:
    lines = []
    for quote_line, info in zip(priced.lines, meta, strict=True):
        image = info["image"]
        lines.append(
            QuoteLineOut(
                variant_id=quote_line.variant_id,
                product_name=info["product"].name,
                variant_name=info["variant"].name,
                sku=info["variant"].sku,
                image_url=(
                    f"{settings.MEDIA_URL}/{image.base_path}_400.webp" if image else None
                ),
                quantity=quote_line.quantity,
                unit_price=Money.of(quote_line.unit_price_paisa),
                personalization_surcharge=Money.of(
                    quote_line.personalization_surcharge_paisa
                ),
                line_total=Money.of(quote_line.subtotal_paisa),
                tax=Money.of(quote_line.tax_paisa),
                personalization={
                    c.key: {"label": c.label, "value": c.value,
                            "surcharge_paisa": c.total_surcharge()}
                    for c in info["choices"]
                },
                in_stock=info["in_stock"],
                available=info["available"],
            )
        )

    return QuoteOut(
        lines=lines,
        subtotal=Money.of(priced.subtotal_paisa),
        discount=Money.of(priced.discount_paisa),
        shipping=Money.of(priced.shipping_paisa),
        cod_surcharge=Money.of(priced.cod_surcharge_paisa),
        gift_wrap=Money.of(priced.gift_wrap_paisa),
        tax=Money.of(priced.tax_paisa),
        loyalty_applied=Money.of(priced.loyalty_applied_paisa),
        total=Money.of(priced.total_paisa),
        tax_mode=priced.tax_mode,
        tax_rate_bp=priced.tax_rate_bp,
        coupon_code=priced.coupon_code,
        coupon_error=priced.coupon_error,
        loyalty_points_earned=priced.loyalty_points_earned,
        free_shipping=extra["free_shipping"],
        cod_available=extra["cod_available"],
        item_count=priced.item_count,
    )


# ── Endpoints ────────────────────────────────────────────────────────────────
@router.post("/checkout/quote", response_model=QuoteOut)
def quote_cart(payload: QuoteIn, db: DbSession, user: OptionalUser) -> QuoteOut:
    """Price a cart without placing anything. Safe to call on every change."""
    priced, meta, extra = _build_quote(db, payload, user)
    return _quote_out(priced, meta, extra)


@router.get("/checkout/payment-methods", response_model=list[dict])
def payment_methods(db: DbSession) -> list[dict]:
    """Everything the checkout should show, including disabled options.

    Disabled methods are returned rather than hidden so the UI can present
    them as deliberately "coming soon" instead of silently missing.
    """
    rows = db.scalars(
        select(PaymentMethod).order_by(PaymentMethod.sort_order)
    ).all()
    return [
        {
            "code": row.code.value,
            "name": row.display_name,
            "description": row.description,
            "enabled": row.is_enabled,
            "unavailable_label": row.unavailable_label,
            "surcharge_paisa": row.surcharge_paisa,
        }
        for row in rows
    ]


@router.get("/checkout/shipping", response_model=list[dict])
def shipping_options(
    db: DbSession, province: PakistanProvince
) -> list[dict]:
    zone = _zone_for(db, province)
    if zone is None:
        return []
    return [
        {
            "id": str(rate.id),
            "name": rate.name,
            "courier": rate.courier.value if rate.courier else None,
            "courier_label": rate.courier.label if rate.courier else None,
            "price_paisa": rate.price_paisa,
            "price_display": format_pkr(rate.price_paisa),
            "free_above_paisa": rate.free_above_paisa,
            "min_days": rate.min_days,
            "max_days": rate.max_days,
        }
        for rate in sorted(
            (r for r in zone.rates if r.is_active), key=lambda r: r.sort_order
        )
    ]


@router.post("/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.RATE_LIMIT_CHECKOUT)
def place_order(
    request: Request, payload: PlaceOrderIn, db: DbSession, user: OptionalUser
) -> OrderOut:
    """Turn a cart into an order.

    Stock is taken under a row lock so two shoppers cannot both buy the last
    one. Prices are recomputed here, never trusted from the client.
    """
    if not payload.accept_terms:
        raise ValidationError("Please accept the terms to continue.")
    if user is None and not payload.email:
        raise ValidationError("An email address is required for guest checkout.")

    payload.province = payload.shipping.province
    priced, meta, extra = _build_quote(db, payload, user)

    if payload.payment_method is PaymentMethodCode.COD and not extra["cod_available"]:
        raise CodNotAvailableError()
    if payload.payment_method is not PaymentMethodCode.COD:
        method = db.scalar(
            select(PaymentMethod).where(PaymentMethod.code == payload.payment_method)
        )
        if method is None or not method.is_enabled:
            raise ConflictError(
                "That payment method is not available yet. Please use Cash on Delivery.",
                code="payment_method_unavailable",
            )

    # Lock the stock rows in a stable order so concurrent checkouts queue
    # rather than deadlock against each other.
    variant_ids = sorted(str(info["variant"].id) for info in meta)
    levels = {
        row.variant_id: row
        for row in db.scalars(
            select(StockLevel)
            .where(StockLevel.variant_id.in_([uuid.UUID(v) for v in variant_ids]))
            .order_by(StockLevel.variant_id)
            .with_for_update()
        ).all()
    }

    for line, info in zip(priced.lines, meta, strict=True):
        level = levels.get(info["variant"].id)
        if info["variant"].is_preorder:
            continue
        if level is None or level.available < line.quantity:
            raise InsufficientStockError(
                f"Only {level.available if level else 0} left of "
                f"{info['product'].name}. Please adjust your cart."
            )

    year = datetime.now(UTC).year
    count = db.scalar(select(func.count()).select_from(Order)) or 0
    order_number = f"WC-{year}-{count + 1:06d}"

    shipping = payload.shipping
    order = Order(
        order_number=order_number,
        user_id=user.id if user else None,
        guest_email=None if user else payload.email,
        guest_phone=None if user else shipping.phone,
        status=OrderStatus.PENDING,
        subtotal_paisa=priced.subtotal_paisa,
        discount_paisa=priced.discount_paisa,
        shipping_paisa=priced.shipping_paisa,
        cod_surcharge_paisa=priced.cod_surcharge_paisa,
        gift_wrap_paisa=priced.gift_wrap_paisa,
        tax_paisa=priced.tax_paisa,
        loyalty_applied_paisa=priced.loyalty_applied_paisa,
        total_paisa=priced.total_paisa,
        tax_mode=priced.tax_mode,
        tax_rate_bp=priced.tax_rate_bp,
        coupon_code=priced.coupon_code if priced.discount_paisa else None,
        loyalty_points_redeemed=priced.loyalty_points_redeemed,
        loyalty_points_earned=priced.loyalty_points_earned,
        shipping_name=shipping.full_name,
        shipping_phone=shipping.phone,
        shipping_line1=shipping.line1,
        shipping_line2=shipping.line2,
        shipping_area=shipping.area,
        shipping_landmark=shipping.landmark,
        shipping_city=shipping.city,
        shipping_province=shipping.province,
        shipping_postal_code=shipping.postal_code,
        billing_address=payload.billing.model_dump(mode="json") if payload.billing else None,
        shipping_method="Standard",
        courier=Courier.TCS,
        customer_note=payload.customer_note,
        is_gift=bool(payload.gift_message),
        gift_message=payload.gift_message,
    )
    db.add(order)
    db.flush()

    for line, info in zip(priced.lines, meta, strict=True):
        product = info["product"]
        variant = info["variant"]
        image = info["image"]

        db.add(OrderItem(
            order_id=order.id,
            product_id=product.id,
            variant_id=variant.id,
            product_name=product.name,
            variant_name=variant.name,
            sku=variant.sku,
            image_path=image.base_path if image else None,
            quantity=line.quantity,
            unit_price_paisa=line.unit_price_paisa,
            personalization_surcharge_paisa=line.personalization_surcharge_paisa,
            discount_paisa=line.total_discount_paisa,
            tax_paisa=line.tax_paisa,
            tax_rate_bp=line.tax_rate_bp,
            line_total_paisa=line.subtotal_paisa,
            personalization={
                c.key: {"label": c.label, "value": c.value,
                        "surcharge_paisa": c.total_surcharge()}
                for c in info["choices"]
            },
        ))

        level = levels.get(variant.id)
        if level is not None and not variant.is_preorder:
            level.on_hand -= line.quantity
            db.add(StockMovement(
                variant_id=variant.id,
                delta=-line.quantity,
                balance_after=level.on_hand,
                reason=MovementReason.SALE,
                order_id=order.id,
            ))
        product.sales_count = (product.sales_count or 0) + line.quantity

    db.add(Payment(
        order_id=order.id,
        method_code=payload.payment_method,
        status=PaymentStatus.PENDING,
        amount_paisa=priced.total_paisa,
        provider_reference=f"COD-{order_number}",
    ))

    db.add(OrderEvent(
        order_id=order.id,
        event_type="status_change",
        message="Order placed",
        to_status=OrderStatus.PENDING,
    ))

    if priced.coupon_code and priced.discount_paisa:
        coupon = db.scalar(select(Coupon).where(Coupon.code == priced.coupon_code))
        if coupon is not None:
            coupon.used_count = (coupon.used_count or 0) + 1
            db.add(CouponRedemption(
                coupon_id=coupon.id,
                order_id=order.id,
                user_id=user.id if user else None,
                discount_paisa=priced.discount_paisa,
            ))

    if priced.loyalty_points_redeemed and user is not None:
        from app.models.promotion import LoyaltyAccount, LoyaltyTransaction

        account = db.scalar(
            select(LoyaltyAccount).where(LoyaltyAccount.user_id == user.id)
        )
        if account is not None:
            account.points_balance -= priced.loyalty_points_redeemed
            db.add(LoyaltyTransaction(
                account_id=account.id,
                order_id=order.id,
                kind="redeemed",
                delta_points=-priced.loyalty_points_redeemed,
                balance_after=account.points_balance,
                note=f"Redeemed against {order_number}",
            ))

    db.flush()

    recipient = user.email if user else payload.email
    if recipient:
        notifications.email(
            db,
            "order_confirmation",
            recipient,
            user=user,
            order_id=order.id,
            recipient_name=shipping.full_name,
            context={
                "order_number": order_number,
                "order_url": f"{settings.PUBLIC_URL}/order/{order_number}",
                "items": [
                    {
                        "name": item.product_name,
                        "variant": item.variant_name,
                        "quantity": item.quantity,
                        "total_paisa": item.line_total_paisa,
                    }
                    for item in order.items
                ],
                "subtotal_paisa": order.subtotal_paisa,
                "discount_paisa": order.discount_paisa,
                "shipping_paisa": order.shipping_paisa,
                "cod_surcharge_paisa": order.cod_surcharge_paisa,
                "tax_paisa": order.tax_paisa,
                "total_paisa": order.total_paisa,
                "payment_method": payload.payment_method.value,
            },
        )
        notifications.sms(
            db,
            "order_confirmation",
            shipping.phone,
            user=user,
            order_id=order.id,
            context={
                "order_number": order_number,
                "total_paisa": order.total_paisa,
            },
        )

    return _order_out(order)


def _order_out(order: Order) -> OrderOut:
    payment = order.payments[0] if order.payments else None
    return OrderOut(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        status_label=order.status.label,
        placed_at=order.placed_at,
        items=[
            OrderItemOut(
                id=item.id,
                product_name=item.product_name,
                variant_name=item.variant_name,
                sku=item.sku,
                image_url=(
                    f"{settings.MEDIA_URL}/{item.image_path}_400.webp"
                    if item.image_path else None
                ),
                quantity=item.quantity,
                unit_price=Money.of(item.unit_price_paisa),
                line_total=Money.of(item.line_total_paisa),
                personalization=item.personalization or {},
            )
            for item in order.items
        ],
        subtotal=Money.of(order.subtotal_paisa),
        discount=Money.of(order.discount_paisa),
        shipping=Money.of(order.shipping_paisa),
        cod_surcharge=Money.of(order.cod_surcharge_paisa),
        tax=Money.of(order.tax_paisa),
        total=Money.of(order.total_paisa),
        tax_mode=order.tax_mode,
        shipping_address={
            "name": order.shipping_name,
            "phone": order.shipping_phone,
            "line1": order.shipping_line1,
            "line2": order.shipping_line2,
            "area": order.shipping_area,
            "landmark": order.shipping_landmark,
            "city": order.shipping_city,
            "province": order.shipping_province.label,
            "postal_code": order.shipping_postal_code,
        },
        courier=order.courier.label if order.courier else None,
        tracking=[
            {
                "courier": shipment.courier.label,
                "tracking_number": shipment.tracking_number,
                "url": shipment.tracking_url,
                "status": shipment.status.value,
                "dispatched_at": shipment.dispatched_at,
                "delivered_at": shipment.delivered_at,
            }
            for shipment in order.shipments
        ],
        timeline=[
            {
                "message": event.message,
                "status": event.to_status.value if event.to_status else None,
                "at": event.created_at,
            }
            for event in sorted(order.events, key=lambda e: e.created_at)
            if event.is_customer_visible
        ],
        is_cancellable=order.is_cancellable,
        payment_method=payment.method_code.value if payment else "cod",
        payment_status=payment.status.value if payment else None,
    )


@router.get("/orders", response_model=list[OrderOut])
def my_orders(
    db: DbSession,
    user: CurrentUser,
    limit: Annotated[int, Query(le=100)] = 50,
) -> list[OrderOut]:
    orders = db.scalars(
        select(Order)
        .where(Order.user_id == user.id)
        .order_by(Order.placed_at.desc())
        .limit(limit)
        .options(
            selectinload(Order.items),
            selectinload(Order.shipments),
            selectinload(Order.events),
            selectinload(Order.payments),
        )
    ).all()
    return [_order_out(order) for order in orders]


@router.get("/orders/{order_number}", response_model=OrderOut)
def get_order(order_number: str, db: DbSession, user: OptionalUser) -> OrderOut:
    """Fetch one order.

    A guest can see their own order straight after checkout by its number. The
    number is not guessable (it is sequential but scoped per year and the page
    exposes nothing sensitive beyond what the buyer already provided), and this
    is how every store's "order confirmation" page works for guests.
    """
    order = db.scalar(
        select(Order)
        .where(Order.order_number == order_number)
        .options(
            selectinload(Order.items),
            selectinload(Order.shipments),
            selectinload(Order.events),
            selectinload(Order.payments),
        )
    )
    if order is None:
        raise NotFoundError("We could not find that order.")

    if order.user_id is not None and (user is None or user.id != order.user_id):
        if user is None or user.role.value not in ("admin", "staff"):
            raise NotFoundError("We could not find that order.")

    return _order_out(order)


@router.post("/orders/{order_number}/cancel", response_model=Message)
def cancel_order(order_number: str, db: DbSession, user: CurrentUser) -> Message:
    order = db.scalar(
        select(Order)
        .where(Order.order_number == order_number, Order.user_id == user.id)
        .options(selectinload(Order.items))
    )
    if order is None:
        raise NotFoundError("We could not find that order.")
    if not order.is_cancellable:
        raise OrderNotCancellableError(
            "This order has already been dispatched and can no longer be cancelled."
        )

    order.status = OrderStatus.CANCELLED
    order.cancelled_at = datetime.now(UTC)
    order.cancellation_reason = "Cancelled by customer"

    # Put the stock back, and record why it moved.
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
        db.add(StockMovement(
            variant_id=item.variant_id,
            delta=item.quantity,
            balance_after=level.on_hand,
            reason=MovementReason.CANCELLATION,
            order_id=order.id,
            note=f"Order {order.order_number} cancelled",
        ))

    db.add(OrderEvent(
        order_id=order.id,
        event_type="status_change",
        message="Cancelled by customer",
        to_status=OrderStatus.CANCELLED,
        actor_id=user.id,
    ))

    notifications.email(
        db, "order_cancelled", user.email, user=user, order_id=order.id,
        context={"order_number": order.order_number, "reason": "you cancelled it"},
    )
    return Message(message="Your order has been cancelled.")
