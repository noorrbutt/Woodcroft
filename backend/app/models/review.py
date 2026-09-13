"""Reviews, review media, helpfulness votes, reports and official replies."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel
from app.models.enums import ReviewStatus


def _enum(py_enum: type, name: str) -> SAEnum:
    return SAEnum(py_enum, name=name, values_callable=lambda e: [m.value for m in e])


class Review(BaseModel):
    __tablename__ = "review"

    product_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), index=True
    )
    #: The order line this review is about. Its presence is what earns the
    #: "verified purchase" badge - the badge is derived, never hand-set.
    order_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("order_item.id", ondelete="SET NULL")
    )

    author_name: Mapped[str] = mapped_column(String(120), nullable=False)
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[ReviewStatus] = mapped_column(
        _enum(ReviewStatus, "review_status"),
        nullable=False,
        server_default=ReviewStatus.PENDING.value,
        index=True,
    )
    moderated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL")
    )
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(String(300))

    helpful_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    not_helpful_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    report_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    media: Mapped[list[ReviewMedia]] = relationship(
        back_populates="review", cascade="all, delete-orphan", lazy="selectin"
    )
    replies: Mapped[list[ReviewReply]] = relationship(
        back_populates="review", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="rating_in_range"),
        # One review per customer per product.
        UniqueConstraint("product_id", "user_id", name="uq_review_per_user_product"),
        # Listing a product's reviews only ever wants approved ones.
        Index(
            "ix_review_published",
            "product_id",
            "created_at",
            postgresql_where=text("status = 'approved'"),
        ),
        # The moderation queue.
        Index(
            "ix_review_pending",
            "created_at",
            postgresql_where=text("status = 'pending'"),
        ),
    )

    @property
    def is_verified_purchase(self) -> bool:
        return self.order_item_id is not None


class ReviewMedia(BaseModel):
    __tablename__ = "review_media"

    review_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("review.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(10), nullable=False, server_default="image")
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_path: Mapped[str | None] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    review: Mapped[Review] = relationship(back_populates="media")

    __table_args__ = (
        CheckConstraint("kind IN ('image', 'video')", name="kind_is_known"),
    )


class ReviewVote(BaseModel):
    """One helpfulness vote. Unique per user so votes cannot be stuffed."""

    __tablename__ = "review_vote"

    review_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("review.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    is_helpful: Mapped[bool] = mapped_column(Boolean, nullable=False)

    __table_args__ = (
        UniqueConstraint("review_id", "user_id", name="uq_review_vote_per_user"),
    )


class ReviewReport(BaseModel):
    __tablename__ = "review_report"

    review_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("review.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    reporter_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL")
    )
    reason: Mapped[str] = mapped_column(String(60), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (
        UniqueConstraint("review_id", "reporter_id", name="uq_review_report_per_user"),
    )


class ReviewReply(BaseModel):
    """A public reply from Woodcroft beneath a review."""

    __tablename__ = "review_reply"

    review_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("review.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL")
    )
    #: Shown instead of the staff member's real name.
    display_name: Mapped[str] = mapped_column(
        String(120), nullable=False, server_default="Woodcroft"
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    review: Mapped[Review] = relationship(back_populates="replies")
