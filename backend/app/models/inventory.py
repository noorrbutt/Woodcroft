"""Stock levels, checkout reservations and the movement ledger.

Three tables, three distinct jobs:

``stock_level``
    The current truth for one variant. ``on_hand`` is physical stock;
    ``reserved`` is how much of it is spoken for by in-flight checkouts.
    Sellable quantity is ``on_hand - reserved``, exposed as a generated column
    so no caller can compute it differently.

``stock_reservation``
    A short-lived hold taken when checkout begins and released on completion,
    abandonment or expiry. This is what prevents two shoppers buying the last
    dining table at the same moment.

``stock_movement``
    Append-only audit ledger. Every change to ``on_hand`` writes a row, so the
    admin can always answer "why is this 3 and not 5?". Never updated or
    deleted.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel
from app.models.enums import MovementReason, ReservationStatus


def _enum(py_enum: type, name: str) -> SAEnum:
    return SAEnum(py_enum, name=name, values_callable=lambda e: [m.value for m in e])


class StockLevel(BaseModel):
    __tablename__ = "stock_level"

    variant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("product_variant.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    on_hand: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    #: Held by active checkout reservations. Kept in step by the inventory
    #: service inside the same transaction that writes the reservation.
    reserved: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    #: Generated so "how many can I sell?" has exactly one definition.
    available: Mapped[int] = mapped_column(
        Integer, Computed("on_hand - reserved", persisted=True)
    )

    low_stock_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("5")
    )
    #: Cached for the PDP "only X left" badge without a second query.
    restocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("on_hand >= 0", name="on_hand_non_negative"),
        CheckConstraint("reserved >= 0", name="reserved_non_negative"),
        # The hard guarantee against overselling: you cannot reserve stock that
        # does not physically exist, whatever the application layer believes.
        CheckConstraint("reserved <= on_hand", name="reserved_within_on_hand"),
        Index(
            "ix_stock_level_low",
            "variant_id",
            postgresql_where=text("on_hand - reserved <= low_stock_threshold"),
        ),
    )

    @property
    def is_low(self) -> bool:
        return self.available <= self.low_stock_threshold

    @property
    def is_out_of_stock(self) -> bool:
        return self.available <= 0


class StockReservation(BaseModel):
    """A time-limited hold on stock during checkout.

    Created when a checkout session starts, consumed when the order is placed,
    and swept back by the background worker once ``expires_at`` passes. The
    sweeper is what stops an abandoned checkout locking inventory forever.
    """

    __tablename__ = "stock_reservation"

    variant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("product_variant.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cart_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("cart.id", ondelete="CASCADE"), index=True
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("order.id", ondelete="SET NULL")
    )

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ReservationStatus] = mapped_column(
        _enum(ReservationStatus, "reservation_status"),
        nullable=False,
        server_default=ReservationStatus.ACTIVE.value,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        # The sweeper's hot path: active reservations past their expiry.
        Index(
            "ix_stock_reservation_expiring",
            "expires_at",
            postgresql_where=text("status = 'active'"),
        ),
    )


class StockMovement(BaseModel):
    """Append-only ledger of every change to physical stock.

    Rows are never updated or deleted. Summing ``delta`` for a variant must
    always reproduce its ``on_hand``, which makes discrepancies auditable.
    """

    __tablename__ = "stock_movement"

    variant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("product_variant.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Signed: negative for a sale, positive for a restock or return.
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    #: on_hand immediately after applying this movement, for point-in-time audit.
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)

    reason: Mapped[MovementReason] = mapped_column(
        _enum(MovementReason, "movement_reason"), nullable=False, index=True
    )
    note: Mapped[str | None] = mapped_column(Text)

    # Provenance: which order, or which admin made a manual adjustment.
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("order.id", ondelete="SET NULL")
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL")
    )
    #: Unit cost at the time, for the inventory-valuation report.
    unit_cost_paisa: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (
        CheckConstraint("delta <> 0", name="delta_non_zero"),
        CheckConstraint("balance_after >= 0", name="balance_non_negative"),
        Index("ix_stock_movement_history", "variant_id", "created_at"),
    )
