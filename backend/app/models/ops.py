"""Operational tables: settings, tax, shipping, notifications, jobs, audit.

The job queue deserves a note. With no Redis and no Celery available, the
background worker is a single asyncio task polling this table. ``claimed_at``
plus ``claimed_by`` form a lease: a worker claims a batch with
``UPDATE ... WHERE status='pending' ... RETURNING``, which is atomic in
Postgres, so even if two workers ever run, a job executes once. A crashed
worker's lease expires and the job is retried.
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
    DataRequestKind,
    DataRequestStatus,
    JobStatus,
    NotificationChannel,
    NotificationStatus,
)


def _enum(py_enum: type, name: str) -> SAEnum:
    return SAEnum(py_enum, name=name, values_callable=lambda e: [m.value for m in e])


class StoreSetting(BaseModel):
    """Runtime-editable store configuration.

    Typed value columns rather than a single JSON blob, so a bad admin edit
    fails at write time instead of at render time.
    """

    __tablename__ = "store_setting"

    key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    group: Mapped[str] = mapped_column(String(40), nullable=False, server_default="general", index=True)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(400))

    value_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text)
    value_int: Mapped[int | None] = mapped_column(BigInteger)
    value_bool: Mapped[bool | None] = mapped_column(Boolean)
    value_json: Mapped[dict | None] = mapped_column(JSONB)

    #: Settings the UI should not expose (secrets, internal toggles).
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (
        CheckConstraint(
            "value_type IN ('text','int','bool','json','money')",
            name="value_type_is_known",
        ),
    )

    @property
    def value(self):
        return {
            "text": self.value_text,
            "int": self.value_int,
            "money": self.value_int,
            "bool": self.value_bool,
            "json": self.value_json,
        }[self.value_type]


class TaxClass(BaseModel):
    """Named tax treatment, e.g. Standard 18%, Zero-rated."""

    __tablename__ = "tax_class"

    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    rate_bp: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(String(300))
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    __table_args__ = (
        CheckConstraint("rate_bp >= 0 AND rate_bp <= 10000", name="rate_bp_is_valid"),
        Index(
            "uq_tax_class_default",
            "is_default",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )


class ShippingZone(BaseModel):
    """A set of provinces sharing shipping rates."""

    __tablename__ = "shipping_zone"

    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    #: Province codes covered by this zone.
    provinces: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    #: Whether Cash on Delivery is offered in this zone at all.
    cod_available: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    cod_surcharge_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    cod_max_order_paisa: Mapped[int | None] = mapped_column(BigInteger)

    rates: Mapped[list[ShippingRate]] = relationship(
        back_populates="zone", cascade="all, delete-orphan", lazy="selectin"
    )


class ShippingRate(BaseModel):
    __tablename__ = "shipping_rate"

    zone_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("shipping_zone.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    courier: Mapped[Courier | None] = mapped_column(_enum(Courier, "courier"))

    price_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: Orders at or above this subtotal ship free on this rate.
    free_above_paisa: Mapped[int | None] = mapped_column(BigInteger)
    #: Weight bracket, in grams. Null bounds mean unbounded.
    min_weight_g: Mapped[int | None] = mapped_column(Integer)
    max_weight_g: Mapped[int | None] = mapped_column(Integer)

    min_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("2"))
    max_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("5"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    zone: Mapped[ShippingZone] = relationship(back_populates="rates")

    __table_args__ = (
        CheckConstraint("price_paisa >= 0", name="price_non_negative"),
        CheckConstraint("max_days >= min_days", name="days_are_ordered"),
        CheckConstraint(
            "max_weight_g IS NULL OR min_weight_g IS NULL OR max_weight_g > min_weight_g",
            name="weight_bracket_is_ordered",
        ),
    )


class NotificationTemplate(BaseModel):
    """Jinja2 source for one notification, editable in admin."""

    __tablename__ = "notification_template"

    key: Mapped[str] = mapped_column(String(80), nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(
        _enum(NotificationChannel, "notification_channel"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(400))

    subject_template: Mapped[str | None] = mapped_column(Text)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    #: Variables the template may reference, for the admin editor's help panel.
    available_variables: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    __table_args__ = (
        UniqueConstraint("key", "channel", name="uq_notification_template"),
    )


class NotificationOutbox(BaseModel):
    """Every email and SMS, fully rendered and stored.

    This is the default delivery target: with no SMTP or SMS credentials
    configured, messages land here and are readable in Admin -> Notifications,
    so the whole notification surface is testable offline. Setting a real
    driver in .env makes delivery additionally attempt the wire; the row is
    written either way, which also gives a permanent audit trail.
    """

    __tablename__ = "notification_outbox"

    channel: Mapped[NotificationChannel] = mapped_column(
        _enum(NotificationChannel, "notification_channel"), nullable=False, index=True
    )
    template_key: Mapped[str | None] = mapped_column(String(80), index=True)

    recipient: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    recipient_name: Mapped[str | None] = mapped_column(String(120))
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), index=True
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("order.id", ondelete="SET NULL"), index=True
    )

    subject: Mapped[str | None] = mapped_column(String(400))
    body_html: Mapped[str | None] = mapped_column(Text)
    body_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    status: Mapped[NotificationStatus] = mapped_column(
        _enum(NotificationStatus, "notification_status"),
        nullable=False,
        server_default=NotificationStatus.QUEUED.value,
        index=True,
    )
    #: Which driver handled it: outbox, smtp, sms_gateway.
    driver: Mapped[str] = mapped_column(String(30), nullable=False, server_default="outbox")
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Set when the user's preferences blocked this message.
    suppressed_reason: Mapped[str | None] = mapped_column(String(160))

    context: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    __table_args__ = (
        Index("ix_outbox_recent", "created_at"),
        Index(
            "ix_outbox_failed",
            "created_at",
            postgresql_where=text("status = 'failed'"),
        ),
    )


class JobQueue(BaseModel):
    """DB-backed job queue, polled by the in-process worker.

    Chosen over Celery because no broker is available in this environment. The
    claim is a single atomic UPDATE ... RETURNING, so jobs cannot double-run.
    """

    __tablename__ = "job_queue"

    job_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[JobStatus] = mapped_column(
        _enum(JobStatus, "job_status"),
        nullable=False,
        server_default=JobStatus.PENDING.value,
    )

    #: Earliest time this job may run. Also the retry backoff mechanism.
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("100"))

    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("3"))
    last_error: Mapped[str | None] = mapped_column(Text)

    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_by: Mapped[str | None] = mapped_column(String(80))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Prevents scheduling the same logical job twice (e.g. one reminder per cart).
    dedupe_key: Mapped[str | None] = mapped_column(String(160))

    __table_args__ = (
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        # The worker's claim query, covered end to end.
        Index(
            "ix_job_queue_runnable",
            "priority",
            "run_after",
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "uq_job_dedupe",
            "dedupe_key",
            unique=True,
            postgresql_where=text(
                "dedupe_key IS NOT NULL AND status IN ('pending', 'claimed')"
            ),
        ),
    )


class AuditLog(BaseModel):
    """Append-only record of every admin mutation."""

    __tablename__ = "audit_log"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL"), index=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    #: Table and row the action touched.
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    summary: Mapped[str] = mapped_column(String(400), nullable=False)

    #: Before/after for the changed fields only, never the whole row.
    changes: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(400))

    __table_args__ = (Index("ix_audit_log_entity", "entity_type", "entity_id"),)


class DataRequest(BaseModel):
    """GDPR-style data export or deletion request."""

    __tablename__ = "data_request"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    kind: Mapped[DataRequestKind] = mapped_column(
        _enum(DataRequestKind, "data_request_kind"), nullable=False
    )
    status: Mapped[DataRequestStatus] = mapped_column(
        _enum(DataRequestStatus, "data_request_status"),
        nullable=False,
        server_default=DataRequestStatus.REQUESTED.value,
        index=True,
    )
    reason: Mapped[str | None] = mapped_column(Text)
    #: Where the generated export archive landed.
    export_path: Mapped[str | None] = mapped_column(String(500))
    export_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL")
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    admin_note: Mapped[str | None] = mapped_column(Text)


class SearchQueryLog(BaseModel):
    """What people searched for. Powers search history and trending terms."""

    __tablename__ = "search_query_log"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    guest_session_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("guest_session.id", ondelete="CASCADE")
    )
    query: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    #: Set when the searcher clicked a result, for relevance analysis.
    clicked_product_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product.id", ondelete="SET NULL")
    )

    __table_args__ = (
        Index("ix_search_trending", "created_at", "query"),
        # Zero-result searches are the most actionable merchandising signal
        # the store produces: they name demand the catalogue cannot meet.
        Index(
            "ix_search_no_results",
            "query",
            postgresql_where=text("result_count = 0"),
        ),
    )
