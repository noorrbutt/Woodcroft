"""Orders, line items, timeline, shipments, returns and refunds.

The price snapshot contract
---------------------------
``order_item`` stores every money component of the line *as it was at purchase*:
unit price, personalization surcharge, allocated discount and tax. Nothing on an
order dereferences the live catalogue for money. An invoice regenerated three
years later must produce byte-identical figures even if the product has since
been repriced, renamed, discounted or deleted - so the product name and SKU are
copied here too, not joined.

Partial shipments
-----------------
An order can ship in several boxes, each with its own courier and tracking
number. ``shipment_item`` records how much of each line went in which box, so
"2 of 3 chairs dispatched" is representable.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel
from app.models.enums import (
    Courier,
    OrderStatus,
    PakistanProvince,
    PaymentMethodCode,
    PaymentStatus,
    ReturnReason,
    ReturnStatus,
    ShipmentStatus,
    TaxMode,
)
from app.models.identity import User


def _enum(py_enum: type, name: str) -> SAEnum:
    return SAEnum(py_enum, name=name, values_callable=lambda e: [m.value for m in e])


class Order(BaseModel):
    __tablename__ = "order"

    #: Human-facing reference, e.g. WC-2026-000412. Unique, never reused.
    order_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    #: Unguessable capability handed to a guest at checkout so they, and only
    #: they, can view their order by its number. Signed-in orders use the owner
    #: check instead and never expose this.
    access_token: Mapped[str | None] = mapped_column(String(64), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128))

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), index=True
    )
    #: Guest checkout keeps only the contact details below.
    guest_email: Mapped[str | None] = mapped_column(String(255))
    guest_phone: Mapped[str | None] = mapped_column(String(20))

    status: Mapped[OrderStatus] = mapped_column(
        _enum(OrderStatus, "order_status"),
        nullable=False,
        server_default=OrderStatus.PENDING.value,
        index=True,
    )

    # ── Money, all paisa, all snapshotted ────────────────────────────────────
    #: Goods total before any discount (line-level or coupon). The coupon and
    #: line discounts are carried in discount_paisa, so subtotal - discount +
    #: shipping + surcharges (+ tax when exclusive) equals total_paisa exactly.
    subtotal_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discount_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    shipping_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    cod_surcharge_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    gift_wrap_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    tax_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    #: Redemptions, stored positive and subtracted in the total.
    gift_card_applied_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    loyalty_applied_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    store_credit_applied_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    #: What the customer actually pays.
    total_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    refunded_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))

    #: Which mode produced these figures, so an old invoice renders its own way.
    tax_mode: Mapped[TaxMode] = mapped_column(
        _enum(TaxMode, "tax_mode"), nullable=False, server_default=TaxMode.INCLUSIVE.value
    )
    tax_rate_bp: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1800"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="PKR")

    # ── Promotions applied ───────────────────────────────────────────────────
    coupon_code: Mapped[str | None] = mapped_column(String(40))
    loyalty_points_redeemed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    loyalty_points_earned: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    # ── Address snapshots ────────────────────────────────────────────────────
    # Copied, not referenced: a customer editing their address book must not
    # retroactively change where a past order was sent.
    shipping_name: Mapped[str] = mapped_column(String(120), nullable=False)
    shipping_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    shipping_line1: Mapped[str] = mapped_column(String(200), nullable=False)
    shipping_line2: Mapped[str | None] = mapped_column(String(200))
    shipping_area: Mapped[str | None] = mapped_column(String(120))
    shipping_landmark: Mapped[str | None] = mapped_column(String(200))
    shipping_city: Mapped[str] = mapped_column(String(80), nullable=False)
    shipping_province: Mapped[PakistanProvince] = mapped_column(
        _enum(PakistanProvince, "pakistan_province"), nullable=False
    )
    shipping_postal_code: Mapped[str | None] = mapped_column(String(10))
    billing_address: Mapped[dict | None] = mapped_column(JSONB)

    # ── Fulfilment ───────────────────────────────────────────────────────────
    shipping_method: Mapped[str | None] = mapped_column(String(80))
    courier: Mapped[Courier | None] = mapped_column(_enum(Courier, "courier"))
    delivery_instructions: Mapped[str | None] = mapped_column(Text)
    customer_note: Mapped[str | None] = mapped_column(Text)
    is_gift: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    gift_message: Mapped[str | None] = mapped_column(Text)

    # ── Ops ──────────────────────────────────────────────────────────────────
    internal_note: Mapped[str | None] = mapped_column(Text)
    #: Rule-based fraud signals, e.g. {"high_value": true, "velocity": 4}.
    fraud_flags: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    is_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    placed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), index=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(Text)

    #: The account that placed this order, when it was not a guest checkout.
    #: Read-only from the order's side: an order never edits a customer.
    #: selectin, not joined: a joined outer-join to the nullable user table makes
    #: Postgres refuse SELECT ... FOR UPDATE on the order ("FOR UPDATE cannot be
    #: applied to the nullable side of an outer join"), which broke refunds and
    #: other order-locking flows. selectin keeps it eager via a separate query.
    user: Mapped[User | None] = relationship(
        "User", lazy="selectin", viewonly=True
    )
    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )
    events: Mapped[list[OrderEvent]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderEvent.created_at",
    )
    shipments: Mapped[list[Shipment]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )
    payments: Mapped[list[Payment]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("subtotal_paisa >= 0", name="subtotal_non_negative"),
        CheckConstraint("total_paisa >= 0", name="total_non_negative"),
        CheckConstraint("discount_paisa >= 0", name="discount_non_negative"),
        CheckConstraint(
            "refunded_paisa >= 0 AND refunded_paisa <= total_paisa",
            name="refund_within_total",
        ),
        # A guest order must carry contact details; an account order need not.
        CheckConstraint(
            "user_id IS NOT NULL OR guest_email IS NOT NULL",
            name="order_has_a_contact",
        ),
        Index("ix_order_user_recent", "user_id", "placed_at"),
        Index(
            "uq_order_idempotency_key",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "ix_order_open",
            "status",
            "placed_at",
            postgresql_where=text(
                "status NOT IN ('delivered', 'cancelled', 'refunded')"
            ),
        ),
        Index("ix_order_flagged", "placed_at", postgresql_where=text("is_flagged")),
    )

    @property
    def is_cancellable(self) -> bool:
        """Self-service cancellation is allowed only before dispatch."""
        return self.status in {OrderStatus.PENDING, OrderStatus.CONFIRMED}


class OrderItem(BaseModel):
    """One purchased line, fully snapshotted."""

    __tablename__ = "order_item"

    order_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("order.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # Kept for reporting joins, but nullable and ON DELETE SET NULL: deleting a
    # product must never destroy order history.
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product.id", ondelete="SET NULL")
    )
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product_variant.id", ondelete="SET NULL")
    )

    # ── Snapshot of what was bought ──────────────────────────────────────────
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    variant_name: Mapped[str | None] = mapped_column(String(200))
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    image_path: Mapped[str | None] = mapped_column(String(500))

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── Snapshot of the money ────────────────────────────────────────────────
    unit_price_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    personalization_surcharge_paisa: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    #: This line's share of any order-level discount, allocated proportionally.
    discount_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    #: Tax attributable to this line, whichever mode was in force.
    tax_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    tax_rate_bp: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1800"))
    #: (unit_price + surcharge) * quantity - discount. Tax handling depends on mode.
    line_total_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)

    #: The configured personalization, copied from the cart line verbatim.
    personalization: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    #: How many units have shipped / been returned, for partial fulfilment.
    quantity_shipped: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    quantity_returned: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    order: Mapped[Order] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price_paisa >= 0", name="unit_price_non_negative"),
        CheckConstraint("line_total_paisa >= 0", name="line_total_non_negative"),
        CheckConstraint(
            "quantity_shipped >= 0 AND quantity_shipped <= quantity",
            name="shipped_within_quantity",
        ),
        CheckConstraint(
            "quantity_returned >= 0 AND quantity_returned <= quantity",
            name="returned_within_quantity",
        ),
    )


class OrderEvent(BaseModel):
    """Append-only timeline entry shown to both customer and admin."""

    __tablename__ = "order_event"

    order_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("order.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    from_status: Mapped[OrderStatus | None] = mapped_column(_enum(OrderStatus, "order_status"))
    to_status: Mapped[OrderStatus | None] = mapped_column(_enum(OrderStatus, "order_status"))

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL")
    )
    #: Internal notes are hidden from the customer-facing timeline.
    is_customer_visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    meta: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    order: Mapped[Order] = relationship(back_populates="events")


class Shipment(BaseModel):
    """One box. An order may have many."""

    __tablename__ = "shipment"

    order_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("order.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    courier: Mapped[Courier] = mapped_column(_enum(Courier, "courier"), nullable=False)
    tracking_number: Mapped[str | None] = mapped_column(String(80), index=True)
    status: Mapped[ShipmentStatus] = mapped_column(
        _enum(ShipmentStatus, "shipment_status"),
        nullable=False,
        server_default=ShipmentStatus.PENDING.value,
    )

    weight_g: Mapped[int | None] = mapped_column(Integer)
    #: COD amount this box collects, when the courier handles cash.
    cod_amount_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))

    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimated_delivery: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)

    order: Mapped[Order] = relationship(back_populates="shipments")
    items: Mapped[list[ShipmentItem]] = relationship(
        back_populates="shipment", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def tracking_url(self) -> str | None:
        if not self.tracking_number:
            return None
        return self.courier.tracking_url


class ShipmentItem(BaseModel):
    __tablename__ = "shipment_item"

    shipment_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("shipment.id", ondelete="CASCADE"), nullable=False
    )
    order_item_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("order_item.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    shipment: Mapped[Shipment] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        UniqueConstraint("shipment_id", "order_item_id", name="uq_shipment_line"),
    )


class ReturnRequest(BaseModel):
    __tablename__ = "return_request"

    #: Customer-facing reference, e.g. WC-RET-000041.
    return_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    order_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("order.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL")
    )

    status: Mapped[ReturnStatus] = mapped_column(
        _enum(ReturnStatus, "return_status"),
        nullable=False,
        server_default=ReturnStatus.REQUESTED.value,
        index=True,
    )
    reason: Mapped[ReturnReason] = mapped_column(
        _enum(ReturnReason, "return_reason"), nullable=False
    )
    customer_note: Mapped[str | None] = mapped_column(Text)
    admin_note: Mapped[str | None] = mapped_column(Text)
    #: Photo evidence uploaded by the customer.
    evidence_paths: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    #: True when the customer wants a replacement rather than money back.
    is_exchange: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list[ReturnItem]] = relationship(
        back_populates="return_request", cascade="all, delete-orphan", lazy="selectin"
    )


class ReturnItem(BaseModel):
    __tablename__ = "return_item"

    return_request_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("return_request.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_item_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("order_item.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Portion of the line refundable for this quantity, snapshotted.
    refundable_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    #: Set on inspection; a damaged return may be restocked or written off.
    restock: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    return_request: Mapped[ReturnRequest] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        UniqueConstraint(
            "return_request_id", "order_item_id", name="uq_return_line"
        ),
    )


class PaymentMethod(BaseModel):
    """Configured payment methods.

    COD is live. JazzCash and Easypaisa exist as rows with ``is_enabled``
    false so checkout can render them as deliberately "coming soon" rather than
    hiding them, and enabling them later is a settings change, not a code change.
    """

    __tablename__ = "payment_method"

    code: Mapped[PaymentMethodCode] = mapped_column(
        _enum(PaymentMethodCode, "payment_method_code"), nullable=False, unique=True
    )
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300))
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    #: Shown in the UI when disabled, e.g. "Coming soon".
    unavailable_label: Mapped[str | None] = mapped_column(String(80))

    surcharge_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    min_order_paisa: Mapped[int | None] = mapped_column(BigInteger)
    max_order_paisa: Mapped[int | None] = mapped_column(BigInteger)
    #: Provinces this method is available in; empty means everywhere.
    allowed_provinces: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    icon: Mapped[str | None] = mapped_column(String(80))


class Payment(BaseModel):
    __tablename__ = "payment"

    order_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("order.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    method_code: Mapped[PaymentMethodCode] = mapped_column(
        _enum(PaymentMethodCode, "payment_method_code"), nullable=False
    )
    status: Mapped[PaymentStatus] = mapped_column(
        _enum(PaymentStatus, "payment_status"),
        nullable=False,
        server_default=PaymentStatus.PENDING.value,
        index=True,
    )

    amount_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    refunded_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))

    #: Provider reference, e.g. a courier's COD collection id.
    provider_reference: Mapped[str | None] = mapped_column(String(120))
    #: Raw provider payload, kept for reconciliation. Never contains card data.
    provider_payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    failure_reason: Mapped[str | None] = mapped_column(String(300))

    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    order: Mapped[Order] = relationship(back_populates="payments")
    transactions: Mapped[list[PaymentTransaction]] = relationship(
        back_populates="payment", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("amount_paisa > 0", name="amount_positive"),
        CheckConstraint(
            "refunded_paisa >= 0 AND refunded_paisa <= amount_paisa",
            name="refund_within_amount",
        ),
    )


class PaymentTransaction(BaseModel):
    """Append-only record of each provider interaction."""

    __tablename__ = "payment_transaction"

    payment_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("payment.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    amount_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    is_success: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    provider_reference: Mapped[str | None] = mapped_column(String(120))
    payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    message: Mapped[str | None] = mapped_column(String(400))

    payment: Mapped[Payment] = relationship(back_populates="transactions")

    __table_args__ = (
        CheckConstraint(
            "kind IN ('authorize','capture','refund','void','status_check')",
            name="kind_is_known",
        ),
    )


class Refund(BaseModel):
    __tablename__ = "refund"

    order_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("order.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("payment.id", ondelete="SET NULL")
    )
    return_request_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("return_request.id", ondelete="SET NULL")
    )

    amount_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    #: COD orders are refunded out-of-band; this records how.
    method: Mapped[str] = mapped_column(String(40), nullable=False, server_default="store_credit")
    reference: Mapped[str | None] = mapped_column(String(120))
    processed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL")
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("amount_paisa > 0", name="amount_positive"),)
