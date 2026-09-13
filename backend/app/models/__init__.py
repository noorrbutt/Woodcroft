"""All ORM models.

Imported eagerly so ``Base.metadata`` is fully populated before Alembic
autogenerate or ``create_all`` runs. Import order does not matter because
relationships are resolved lazily by string name.
"""

from app.models.identity import (  # noqa: F401
    Address,
    EmailVerification,
    GuestSession,
    NotificationPreference,
    PasswordReset,
    RefreshToken,
    StaffPermissionGrant,
    User,
)

__all__ = [
    "Address",
    "EmailVerification",
    "GuestSession",
    "NotificationPreference",
    "PasswordReset",
    "RefreshToken",
    "StaffPermissionGrant",
    "User",
]
