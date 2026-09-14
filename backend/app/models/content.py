"""CMS: blog, static pages, homepage banners, testimonials, FAQ, newsletter."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class BlogPost(BaseModel):
    """Care guides, styling tips, craftsmanship stories."""

    __tablename__ = "blog_post"

    title: Mapped[str] = mapped_column(String(220), nullable=False)
    slug: Mapped[str] = mapped_column(String(240), nullable=False, unique=True)
    excerpt: Mapped[str | None] = mapped_column(String(500))
    #: Tiptap HTML output.
    body_html: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    cover_image_path: Mapped[str | None] = mapped_column(String(500))

    author_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL")
    )
    author_name: Mapped[str] = mapped_column(String(120), nullable=False, server_default="Woodcroft")
    category: Mapped[str | None] = mapped_column(String(60), index=True)
    tags: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))

    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reading_minutes: Mapped[int | None] = mapped_column(Integer)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    meta_title: Mapped[str | None] = mapped_column(String(200))
    meta_description: Mapped[str | None] = mapped_column(String(400))

    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('english', coalesce(excerpt, '')), 'B')",
            persisted=True,
        ),
    )

    __table_args__ = (
        Index("ix_blog_post_search", "search_vector", postgresql_using="gin"),
        Index(
            "ix_blog_post_live",
            "published_at",
            postgresql_where=text("is_published"),
        ),
    )


class StaticPage(BaseModel):
    """About, Sustainability, Terms, Privacy, Shipping and Return policies."""

    __tablename__ = "static_page"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), nullable=False, unique=True)
    body_html: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    #: Policy pages are linked from the footer; About from the main nav.
    show_in_footer: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    meta_title: Mapped[str | None] = mapped_column(String(200))
    meta_description: Mapped[str | None] = mapped_column(String(400))
    #: Set on system pages so an admin cannot delete Terms by accident.
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class Banner(BaseModel):
    """A homepage hero or promotional block."""

    __tablename__ = "banner"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(400))
    #: Where it renders: hero, strip, category_tile, promo_block.
    placement: Mapped[str] = mapped_column(String(40), nullable=False, index=True)

    image_path: Mapped[str | None] = mapped_column(String(500))
    mobile_image_path: Mapped[str | None] = mapped_column(String(500))
    link_url: Mapped[str | None] = mapped_column(String(500))
    cta_label: Mapped[str | None] = mapped_column(String(60))
    #: Overlay tone, so text stays legible over a light or dark photograph.
    overlay: Mapped[str] = mapped_column(String(20), nullable=False, server_default="dark")

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    __table_args__ = (
        CheckConstraint(
            "ends_at IS NULL OR starts_at IS NULL OR ends_at > starts_at",
            name="window_is_ordered",
        ),
        CheckConstraint("overlay IN ('dark','light','none')", name="overlay_is_known"),
    )


class Testimonial(BaseModel):
    __tablename__ = "testimonial"

    author_name: Mapped[str] = mapped_column(String(120), nullable=False)
    author_title: Mapped[str | None] = mapped_column(String(160))
    author_city: Mapped[str | None] = mapped_column(String(80))
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    avatar_path: Mapped[str | None] = mapped_column(String(500))
    #: Press mentions render differently from customer quotes.
    is_press: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    publication: Mapped[str | None] = mapped_column(String(120))
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class Faq(BaseModel):
    __tablename__ = "faq"

    question: Mapped[str] = mapped_column(String(300), nullable=False)
    answer_html: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False, server_default="general", index=True)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    helpful_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class NewsletterSubscriber(BaseModel):
    __tablename__ = "newsletter_subscriber"

    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String(120))
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL")
    )
    #: Where they signed up: footer, popup, checkout.
    source: Mapped[str | None] = mapped_column(String(40))
    #: Double opt-in; only confirmed addresses receive campaigns.
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirm_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    unsubscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The welcome incentive issued on confirmation.
    welcome_coupon_code: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        Index(
            "ix_newsletter_active",
            "email",
            postgresql_where=text(
                "confirmed_at IS NOT NULL AND unsubscribed_at IS NULL"
            ),
        ),
    )


class SupportTicket(BaseModel):
    """A support conversation, optionally attached to an order."""

    __tablename__ = "support_ticket"

    ticket_number: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), index=True
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("order.id", ondelete="SET NULL"), index=True
    )

    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str] = mapped_column(String(120), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, server_default="general")
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="open", index=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, server_default="normal")

    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reply_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list[SupportMessage]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="SupportMessage.created_at",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('open','pending_customer','resolved','closed')",
            name="status_is_known",
        ),
        CheckConstraint(
            "priority IN ('low','normal','high','urgent')", name="priority_is_known"
        ),
    )


class SupportMessage(BaseModel):
    __tablename__ = "support_message"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("support_ticket.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL")
    )
    #: Distinguishes the customer's messages from Woodcroft's replies.
    is_staff: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    #: Staff-only notes are hidden from the customer view.
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    attachments: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    ticket: Mapped[SupportTicket] = relationship(back_populates="messages")
