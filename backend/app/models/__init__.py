"""All ORM models.

Imported eagerly so ``Base.metadata`` is fully populated before Alembic
autogenerate or ``create_all`` runs. Import order does not matter because
relationships are resolved lazily by string name.
"""

from app.models.catalog import (  # noqa: F401
    BackInStockSubscription,
    Category,
    PersonalizationOption,
    PriceWatch,
    Product,
    ProductAnswer,
    ProductAsset,
    ProductImage,
    ProductOptionType,
    ProductOptionValue,
    ProductQuestion,
    ProductTag,
    ProductVariant,
    RecentlyViewed,
    Tag,
    VariantOptionValue,
)
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
    "BackInStockSubscription",
    "Category",
    "EmailVerification",
    "GuestSession",
    "NotificationPreference",
    "PasswordReset",
    "PersonalizationOption",
    "PriceWatch",
    "Product",
    "ProductAnswer",
    "ProductAsset",
    "ProductImage",
    "ProductOptionType",
    "ProductOptionValue",
    "ProductQuestion",
    "ProductTag",
    "ProductVariant",
    "RecentlyViewed",
    "RefreshToken",
    "StaffPermissionGrant",
    "Tag",
    "User",
    "VariantOptionValue",
]
