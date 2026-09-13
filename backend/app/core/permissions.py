"""Roles and granular staff permissions.

Three roles exist. ``customer`` and ``admin`` are the endpoints of the range;
``staff`` sits between them and carries an explicit permission set, so a
warehouse operator can fulfil orders without being able to issue refunds or
change store settings.

The frontend mirrors this list to hide controls, but the backend is the
authority - every admin route enforces its permission via a dependency.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    CUSTOMER = "customer"
    STAFF = "staff"
    ADMIN = "admin"


class Permission(StrEnum):
    # Catalog
    PRODUCT_VIEW = "product:view"
    PRODUCT_EDIT = "product:edit"
    PRODUCT_DELETE = "product:delete"
    PRODUCT_PUBLISH = "product:publish"
    CATEGORY_MANAGE = "category:manage"

    # Inventory
    INVENTORY_VIEW = "inventory:view"
    INVENTORY_ADJUST = "inventory:adjust"

    # Orders
    ORDER_VIEW = "order:view"
    ORDER_UPDATE_STATUS = "order:update_status"
    ORDER_REFUND = "order:refund"
    ORDER_CANCEL = "order:cancel"
    RETURN_MANAGE = "return:manage"
    SHIPMENT_MANAGE = "shipment:manage"

    # Customers
    CUSTOMER_VIEW = "customer:view"
    CUSTOMER_EDIT = "customer:edit"
    CUSTOMER_ROLE_ASSIGN = "customer:role_assign"
    CUSTOMER_CREDIT_ADJUST = "customer:credit_adjust"

    # Marketing
    PROMO_MANAGE = "promo:manage"
    GIFT_CARD_MANAGE = "gift_card:manage"
    LOYALTY_MANAGE = "loyalty:manage"
    CAMPAIGN_MANAGE = "campaign:manage"

    # Content & moderation
    REVIEW_MODERATE = "review:moderate"
    QA_MODERATE = "qa:moderate"
    CONTENT_MANAGE = "content:manage"

    # Support
    TICKET_VIEW = "ticket:view"
    TICKET_REPLY = "ticket:reply"

    # Ops
    ANALYTICS_VIEW = "analytics:view"
    NOTIFICATION_VIEW = "notification:view"
    SETTINGS_MANAGE = "settings:manage"
    AUDIT_VIEW = "audit:view"
    DATA_REQUEST_MANAGE = "data_request:manage"


#: Admins implicitly hold every permission; this is only the default grant for
#: a newly created staff account. Individual grants are editable in Admin.
DEFAULT_STAFF_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.PRODUCT_VIEW,
        Permission.PRODUCT_EDIT,
        Permission.CATEGORY_MANAGE,
        Permission.INVENTORY_VIEW,
        Permission.INVENTORY_ADJUST,
        Permission.ORDER_VIEW,
        Permission.ORDER_UPDATE_STATUS,
        Permission.SHIPMENT_MANAGE,
        Permission.RETURN_MANAGE,
        Permission.CUSTOMER_VIEW,
        Permission.REVIEW_MODERATE,
        Permission.QA_MODERATE,
        Permission.TICKET_VIEW,
        Permission.TICKET_REPLY,
        Permission.NOTIFICATION_VIEW,
    }
)

ALL_PERMISSIONS: frozenset[Permission] = frozenset(Permission)


def permissions_for(role: Role, granted: set[str] | None = None) -> frozenset[Permission]:
    """Effective permissions for a user.

    Admins get everything regardless of stored grants. Staff get exactly what is
    stored against them. Customers get nothing from this set.
    """
    if role is Role.ADMIN:
        return ALL_PERMISSIONS
    if role is Role.STAFF:
        if granted is None:
            return DEFAULT_STAFF_PERMISSIONS
        return frozenset(
            Permission(p) for p in granted if p in Permission._value2member_map_
        )
    return frozenset()
