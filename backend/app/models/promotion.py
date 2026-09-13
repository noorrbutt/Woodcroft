"""Coupons, automatic discounts, flash sales, bundles, gift cards, loyalty.

Discount rules are stored as typed columns for the parts the query planner
needs (active window, usage caps, minimum spend) and JSONB for the parts that
vary by rule kind (which categories, buy-N-get-M shape). That split keeps the
"which promotions apply right now?" query indexable while still allowing rules
the schema did not anticipate.

Nothing here computes money. ``app.services.pricing`` reads these rows and is
the only place a discount is ever applied.
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
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel
from app.models.enums import (
    DiscountKind,
    DiscountTarget,
    GiftCardStatus,
    LoyaltyTransactionKind,
)


def _enum(py_enum: type, name: str) -> SAEnum:
    return SAEnum(py_enum, name=name, values_callable=lambda e: [m.value for m in e])


class Coupon(BaseModel):
    """A code the customer types in."""

    __tablename__ = "coupon"

    # CITEXT so "WELCOME10" and "welcome10" are the same coupon.
    code: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(300))

    kind: Mapped[DiscountKind] = mapped_column(_enum(DiscountKind, "discount_kind"), nullable=False)
    #: Percentage in basis points (1000 = 10%), used when kind is PERCENTAGE.
    value_bp: Mapped[int | None] = mapped_column(Integer)
    #: Flat amount in paisa, used when kind is FIXED_AMOUNT.
    value_paisa: Mapped[int | None] = mapped_column(BigInteger)
    #: Ceiling on a percentage discount, e.g. "20% off, up to Rs 5,000".
    max_discount_paisa: Mapped[int | None] = mapped_column(BigInteger)

    min_order_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    #: Null means unlimited.
    usage_limit: Mapped[int | None] = mapped_column(Integer)
    usage_limit_per_user: Mapped[int | None] = mapped_column(Integer)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    #: Restrict to first-time buyers, specific categories, or named products.
    first_order_only: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    target: Mapped[DiscountTarget] = mapped_column(
        _enum(DiscountTarget, "discount_target"),
        nullable=False,
        server_default=DiscountTarget.ORDER.value,
    )
    #: {"category_ids": [...], "product_ids": [...], "exclude_sale_items": true}
    conditions: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    redemptions: Mapped[list[CouponRedemption]] = relationship(
        back_populates="coupon", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "(kind = 'percentage' AND value_bp IS NOT NULL) OR "
            "(kind = 'fixed_amount' AND value_paisa IS NOT NULL) OR "
            "(kind = 'free_shipping')",
            name="coupon_value_matches_kind",
        ),
        CheckConstraint(
            "value_bp IS NULL OR (value_bp > 0 AND value_bp <= 10000)",
            name="value_bp_is_valid_percentage",
        ),
        CheckConstraint("value_paisa IS NULL OR value_paisa > 0", name="value_paisa_positive"),
        CheckConstraint(
            "ends_at IS NULL OR starts_at IS NULL OR ends_at > starts_at",
            name="window_is_ordered",
        ),
        CheckConstraint("used_count >= 0", name="used_count_non_negative"),
        Index(
            "ix_coupon_live",
            "code",
            postgresql_where=text("is_active"),
        ),
    )

    def is_live(self, now: datetime) -> bool:
        if not self.is_active:
            return False
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return self.usage_limit is None or self.used_count < self.usage_limit


class CouponRedemption(BaseModel):
    __tablename__ = "coupon_redemption"

    coupon_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("coupon.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("order.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), index=True
    )
    #: What it actually saved, for the coupon-performance report.
    discount_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)

    coupon: Mapped[Coupon] = relationship(back_populates="redemptions")

    __table_args__ = (
        UniqueConstraint("coupon_id", "order_id", name="uq_coupon_per_order"),
    )


class DiscountRule(BaseModel):
    """An automatic discount: no code, applies when conditions are met.

    Covers category-wide sales and buy-N-get-M. ``config`` carries the
    kind-specific shape, e.g. {"buy": 2, "get": 1, "category_ids": [...]}.
    """

    __tablename__ = "discount_rule"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300))
    kind: Mapped[DiscountKind] = mapped_column(_enum(DiscountKind, "discount_kind"), nullable=False)
    target: Mapped[DiscountTarget] = mapped_column(
        _enum(DiscountTarget, "discount_target"), nullable=False
    )

    value_bp: Mapped[int | None] = mapped_column(Integer)
    value_paisa: Mapped[int | None] = mapped_column(BigInteger)
    min_order_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))

    config: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    #: Lower runs first. Rules are applied in priority order, best-value-first
    #: within a tie, and only one order-level rule can win unless stackable.
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("100"))
    is_stackable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "ends_at IS NULL OR starts_at IS NULL OR ends_at > starts_at",
            name="window_is_ordered",
        ),
        Index("ix_discount_rule_live", "priority", postgresql_where=text("is_active")),
    )


class FlashSale(BaseModel):
    """A time-boxed sale with a countdown, activated by the background worker."""

    __tablename__ = "flash_sale"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    banner_image_path: Mapped[str | None] = mapped_column(String(500))

    discount_bp: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    #: Optional cap on units sold at the sale price.
    max_units: Mapped[int | None] = mapped_column(Integer)
    units_sold: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    items: Mapped[list[FlashSaleItem]] = relationship(
        back_populates="flash_sale", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="window_is_ordered"),
        CheckConstraint(
            "discount_bp > 0 AND discount_bp <= 10000", name="discount_bp_is_valid"
        ),
        Index("ix_flash_sale_window", "starts_at", "ends_at"),
    )


class FlashSaleItem(BaseModel):
    __tablename__ = "flash_sale_item"

    flash_sale_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("flash_sale.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product.id", ondelete="CASCADE"), nullable=False
    )
    #: Overrides the sale's blanket percentage for this product.
    discount_bp: Mapped[int | None] = mapped_column(Integer)

    flash_sale: Mapped[FlashSale] = relationship(back_populates="items")

    __table_args__ = (
        UniqueConstraint("flash_sale_id", "product_id", name="uq_flash_sale_product"),
    )


class Bundle(BaseModel):
    """Buy these together for a combined price."""

    __tablename__ = "bundle"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    #: Null means "sum of members, minus discount_bp".
    bundle_price_paisa: Mapped[int | None] = mapped_column(BigInteger)
    discount_bp: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    items: Mapped[list[BundleItem]] = relationship(
        back_populates="bundle", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "bundle_price_paisa IS NOT NULL OR discount_bp IS NOT NULL",
            name="bundle_needs_a_price_rule",
        ),
    )


class BundleItem(BaseModel):
    __tablename__ = "bundle_item"

    bundle_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("bundle.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product.id", ondelete="CASCADE"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    bundle: Mapped[Bundle] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        UniqueConstraint("bundle_id", "product_id", name="uq_bundle_product"),
    )


class GiftCard(BaseModel):
    """A prepaid balance.

    ``balance_paisa`` is the truth; ``gift_card_transaction`` is the ledger that
    explains it, exactly as with stock.
    """

    __tablename__ = "gift_card"

    code: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    initial_balance_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[GiftCardStatus] = mapped_column(
        _enum(GiftCardStatus, "gift_card_status"),
        nullable=False,
        server_default=GiftCardStatus.ACTIVE.value,
        index=True,
    )

    #: Who bought it, and the order it was bought on.
    purchaser_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL")
    )
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("order.id", ondelete="SET NULL")
    )
    recipient_email: Mapped[str | None] = mapped_column(String(255))
    recipient_name: Mapped[str | None] = mapped_column(String(120))
    message: Mapped[str | None] = mapped_column(Text)

    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    transactions: Mapped[list[GiftCardTransaction]] = relationship(
        back_populates="gift_card", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("initial_balance_paisa > 0", name="initial_balance_positive"),
        CheckConstraint(
            "balance_paisa >= 0 AND balance_paisa <= initial_balance_paisa",
            name="balance_within_initial",
        ),
    )


class GiftCardTransaction(BaseModel):
    __tablename__ = "gift_card_transaction"

    gift_card_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("gift_card.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("order.id", ondelete="SET NULL")
    )
    #: Negative when spent, positive when issued or refunded back.
    delta_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    note: Mapped[str | None] = mapped_column(String(300))

    gift_card: Mapped[GiftCard] = relationship(back_populates="transactions")

    __table_args__ = (
        CheckConstraint("delta_paisa <> 0", name="delta_non_zero"),
        CheckConstraint("balance_after_paisa >= 0", name="balance_non_negative"),
    )


class LoyaltyAccount(BaseModel):
    __tablename__ = "loyalty_account"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    points_balance: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    lifetime_points_earned: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    #: VIP / Gold tiers, recomputed on each earn.
    tier: Mapped[str] = mapped_column(String(30), nullable=False, server_default="bronze")

    transactions: Mapped[list[LoyaltyTransaction]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("points_balance >= 0", name="points_balance_non_negative"),
    )


class LoyaltyTransaction(BaseModel):
    __tablename__ = "loyalty_transaction"

    account_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("loyalty_account.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("order.id", ondelete="SET NULL")
    )
    kind: Mapped[LoyaltyTransactionKind] = mapped_column(
        _enum(LoyaltyTransactionKind, "loyalty_transaction_kind"), nullable=False
    )
    #: Negative when redeemed.
    delta_points: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(String(300))
    #: Points can expire; null means they do not.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    account: Mapped[LoyaltyAccount] = relationship(back_populates="transactions")

    __table_args__ = (
        CheckConstraint("delta_points <> 0", name="delta_non_zero"),
        CheckConstraint("balance_after >= 0", name="balance_non_negative"),
    )


class Referral(BaseModel):
    """One referred signup, and the reward it earned once qualified."""

    __tablename__ = "referral"

    referrer_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    referred_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), unique=True
    )
    referred_email: Mapped[str] = mapped_column(String(255), nullable=False)
    code_used: Mapped[str] = mapped_column(String(16), nullable=False)

    #: Rewards land only after the referred user's first delivered order.
    qualifying_order_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("order.id", ondelete="SET NULL")
    )
    qualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    referrer_reward_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    referred_reward_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    rewarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
