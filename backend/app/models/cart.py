"""Cart, saved-for-later, wishlist and abandoned-cart tracking.

A cart belongs to either a signed-in user or a guest session, never both and
never neither - enforced by a CHECK. On login the guest cart is merged into the
account cart rather than discarded, so nothing a shopper collected is lost.

Money on ``cart_item`` is a *cache*, not the truth. The pricing service
recomputes on every read so a price change, a new sale or an expired coupon is
reflected immediately; the cached columns exist so listing a cart does not
require re-running the whole pipeline for a simple badge count.
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel

#: Exactly one of user_id / guest_session_id must be set.
_ONE_OWNER = "(user_id IS NOT NULL) <> (guest_session_id IS NOT NULL)"


class Cart(BaseModel):
    __tablename__ = "cart"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    guest_session_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("guest_session.id", ondelete="CASCADE"), index=True
    )

    #: Cleared when the cart is converted to an order.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    converted_order_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("order.id", ondelete="SET NULL")
    )

    # Applied promotions. Validity is re-checked at checkout; storing the code
    # here only remembers the shopper's intent.
    coupon_code: Mapped[str | None] = mapped_column(String(40))
    gift_card_code: Mapped[str | None] = mapped_column(String(40))
    loyalty_points_to_redeem: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    # Gift options
    is_gift: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    gift_message: Mapped[str | None] = mapped_column(Text)
    gift_wrap: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    note: Mapped[str | None] = mapped_column(Text)
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    items: Mapped[list[CartItem]] = relationship(
        back_populates="cart",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="CartItem.created_at",
    )

    __table_args__ = (
        CheckConstraint(_ONE_OWNER, name="exactly_one_owner"),
        CheckConstraint(
            "loyalty_points_to_redeem >= 0", name="loyalty_points_non_negative"
        ),
        # One active cart per owner.
        Index(
            "uq_cart_active_user",
            "user_id",
            unique=True,
            postgresql_where=text("is_active AND user_id IS NOT NULL"),
        ),
        Index(
            "uq_cart_active_guest",
            "guest_session_id",
            unique=True,
            postgresql_where=text("is_active AND guest_session_id IS NOT NULL"),
        ),
    )

    @property
    def item_count(self) -> int:
        return sum(item.quantity for item in self.items)


class CartItem(BaseModel):
    __tablename__ = "cart_item"

    cart_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("cart.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product_variant.id", ondelete="CASCADE"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    # ── Personalization ──────────────────────────────────────────────────────
    # The shopper's chosen values, shaped as:
    #   {"engraving": {"label": "Engraving", "value": "For Ayesha",
    #                  "surcharge_paisa": 50000}}
    # Captured as data rather than FK references so that editing or deleting the
    # option definition later cannot rewrite what someone already configured.
    personalization: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    #: Stable hash of the personalization, so two differently-engraved units of
    #: the same variant stay separate lines instead of merging into quantity 2.
    personalization_key: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=""
    )

    # ── Cached pricing (recomputed by the pricing service on every read) ─────
    unit_price_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    personalization_surcharge_paisa: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    line_total_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))

    cart: Mapped[Cart] = relationship(back_populates="items")

    __table_args__ = (
        CheckConstraint("quantity > 0 AND quantity <= 99", name="quantity_in_range"),
        # Same variant + same personalization collapses into one line.
        UniqueConstraint(
            "cart_id", "variant_id", "personalization_key", name="uq_cart_line"
        ),
    )


class SavedForLater(BaseModel):
    """Moved out of the cart but not discarded."""

    __tablename__ = "saved_for_later"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    guest_session_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("guest_session.id", ondelete="CASCADE"), index=True
    )
    variant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product_variant.id", ondelete="CASCADE"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    personalization: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    __table_args__ = (
        CheckConstraint(_ONE_OWNER, name="exactly_one_owner"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
    )


class WishlistItem(BaseModel):
    """Wishlist is product-level, not variant-level.

    A shopper saving "that walnut console" has not usually decided on a finish
    yet; forcing a variant choice at save time is the wrong model.
    """

    __tablename__ = "wishlist_item"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    guest_session_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("guest_session.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product.id", ondelete="CASCADE"), nullable=False
    )
    #: Optional preferred variant, when the shopper has decided.
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product_variant.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (
        CheckConstraint(_ONE_OWNER, name="exactly_one_owner"),
        UniqueConstraint("user_id", "product_id", name="uq_wishlist_user_product"),
        UniqueConstraint(
            "guest_session_id", "product_id", name="uq_wishlist_guest_product"
        ),
    )


class AbandonedCart(BaseModel):
    """A cart that went quiet, and the recovery emails sent about it.

    Kept separate from ``cart`` so the recovery campaign has its own lifecycle
    and the analytics query does not have to reason about live carts.
    """

    __tablename__ = "abandoned_cart"

    cart_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("cart.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL")
    )
    email: Mapped[str | None] = mapped_column(String(255))

    #: Cart value when abandonment was detected, for the revenue-at-risk report.
    cart_value_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    reminder_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Incentive issued with the final reminder, if any.
    incentive_coupon_code: Mapped[str | None] = mapped_column(String(40))
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recovered_order_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("order.id", ondelete="SET NULL")
    )

    __table_args__ = (
        Index(
            "ix_abandoned_cart_pending",
            "detected_at",
            postgresql_where=text("recovered_at IS NULL"),
        ),
    )
