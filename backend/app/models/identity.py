"""Users, authentication artefacts, addresses and guest identity."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

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
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.permissions import Permission, Role, permissions_for
from app.db.base import BaseModel
from app.models.enums import AddressType, PakistanProvince

#: +92 mobile numbers, stored normalised as 03XXXXXXXXX (11 digits).
PK_MOBILE_REGEX = r"^03[0-9]{9}$"


def _enum(py_enum: type, name: str) -> SAEnum:
    """Native PG enum that stores the StrEnum *value*, not the member name."""
    return SAEnum(py_enum, name=name, values_callable=lambda e: [m.value for m in e])


class User(BaseModel):
    __tablename__ = "user"

    # CITEXT makes email comparison case-insensitive in the database, so
    # 'Ali@x.com' and 'ali@x.com' cannot both be registered.
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    avatar_path: Mapped[str | None] = mapped_column(String(500))

    role: Mapped[Role] = mapped_column(
        _enum(Role, "user_role"),
        nullable=False,
        server_default=Role.CUSTOMER.value,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Lockout counters, reset to zero on any successful login.
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Store credit in paisa. Loyalty points live on loyalty_account.
    store_credit_paisa: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )

    # Referrals: every user gets a code; referred_by points at the referrer.
    referral_code: Mapped[str | None] = mapped_column(String(16), unique=True)
    referred_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL")
    )

    # Soft delete. The row is retained so historical orders keep referential
    # integrity; the account simply stops working.
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    addresses: Mapped[list[Address]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    permission_grants: Mapped[list[StaffPermissionGrant]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        foreign_keys="StaffPermissionGrant.user_id",
    )
    notification_preference: Mapped[NotificationPreference | None] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint(
            f"phone IS NULL OR phone ~ '{PK_MOBILE_REGEX}'",
            name="phone_is_pk_mobile",
        ),
        Index("ix_user_active_role", "role", postgresql_where=text("is_active")),
    )

    @property
    def is_locked(self) -> bool:
        return self.locked_until is not None and self.locked_until > datetime.now(UTC)

    @property
    def granted_permissions(self) -> set[str]:
        return {g.permission for g in self.permission_grants}

    def has_permission(self, permission: Permission) -> bool:
        return permission in permissions_for(self.role, self.granted_permissions)


class StaffPermissionGrant(BaseModel):
    """One row per permission granted to a staff user.

    Row-per-grant rather than an array column so the admin UI can show who
    granted what and when, using the inherited created_at.
    """

    __tablename__ = "staff_permission_grant"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    permission: Mapped[str] = mapped_column(String(64), nullable=False)
    granted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL")
    )

    user: Mapped[User] = relationship(
        back_populates="permission_grants", foreign_keys=[user_id]
    )

    __table_args__ = (
        UniqueConstraint("user_id", "permission", name="uq_staff_permission"),
    )


class RefreshToken(BaseModel):
    """A member of a refresh-token family.

    Tokens rotate: each use issues a new row and revokes the old one. If an
    already-revoked token is presented again that is a replay, and the whole
    family (same session_id) is revoked. This is standard reuse detection and
    makes a stolen refresh token self-limiting.
    """

    __tablename__ = "refresh_token"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Groups every rotation of a single login together.
    session_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Set when rotated, pointing at the replacement token.
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("refresh_token.id", ondelete="SET NULL")
    )

    # Shown in "active sessions" so a user can recognise their own devices.
    user_agent: Mapped[str | None] = mapped_column(String(400))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    remember_me: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")

    __table_args__ = (
        Index(
            "ix_refresh_token_active",
            "user_id",
            "session_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    @property
    def is_usable(self) -> bool:
        return self.revoked_at is None and self.expires_at > datetime.now(UTC)


class EmailVerification(BaseModel):
    __tablename__ = "email_verification"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Set when verifying a changed email rather than the signup address.
    new_email: Mapped[str | None] = mapped_column(CITEXT)


class PasswordReset(BaseModel):
    __tablename__ = "password_reset"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_ip: Mapped[str | None] = mapped_column(String(45))


class Address(BaseModel):
    """A Pakistani postal address.

    ``landmark`` is not decoration: addressing in Pakistan routinely relies on a
    nearby landmark rather than a precise street number, and couriers expect it.
    """

    __tablename__ = "address"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), index=True
    )

    label: Mapped[str | None] = mapped_column(String(40))  # "Home", "Office"
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)

    line1: Mapped[str] = mapped_column(String(200), nullable=False)
    line2: Mapped[str | None] = mapped_column(String(200))
    area: Mapped[str | None] = mapped_column(String(120))  # sector / block / colony
    landmark: Mapped[str | None] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    province: Mapped[PakistanProvince] = mapped_column(
        _enum(PakistanProvince, "pakistan_province"), nullable=False, index=True
    )
    postal_code: Mapped[str | None] = mapped_column(String(10))

    address_type: Mapped[AddressType] = mapped_column(
        _enum(AddressType, "address_type"),
        nullable=False,
        server_default=AddressType.BOTH.value,
    )
    is_default_shipping: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_default_billing: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    delivery_instructions: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User | None] = relationship(back_populates="addresses")

    __table_args__ = (
        CheckConstraint(f"phone ~ '{PK_MOBILE_REGEX}'", name="phone_is_pk_mobile"),
        CheckConstraint(
            "postal_code IS NULL OR postal_code ~ '^[0-9]{5}$'",
            name="postal_code_is_5_digits",
        ),
        # At most one default of each kind per user.
        Index(
            "uq_address_default_shipping",
            "user_id",
            unique=True,
            postgresql_where=text("is_default_shipping AND user_id IS NOT NULL"),
        ),
        Index(
            "uq_address_default_billing",
            "user_id",
            unique=True,
            postgresql_where=text("is_default_billing AND user_id IS NOT NULL"),
        ),
    )


class GuestSession(BaseModel):
    """Identity for a shopper who has not signed in.

    Carries the cart, wishlist and recently-viewed list so a guest can shop and
    check out; on login the contents are merged into the account.
    """

    __tablename__ = "guest_session"

    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    #: Set once the guest signs in and their data is merged.
    merged_into_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL")
    )
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(400))
    ip_address: Mapped[str | None] = mapped_column(String(45))


class NotificationPreference(BaseModel):
    __tablename__ = "notification_preference"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    email_order_updates: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    # Marketing is opt-in (PECA / anti-spam): off unless the customer chooses it.
    email_marketing: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    email_back_in_stock: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    email_price_drop: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    email_review_reminder: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    sms_order_updates: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    sms_marketing: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    user: Mapped[User] = relationship(back_populates="notification_preference")
