"""Admin API: dashboard, catalog, inventory, orders, customers, moderation.

Every mutation writes an audit row. Read endpoints are gated on a granular
permission so a warehouse operator can fulfil orders without being able to
issue refunds or change store settings.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import String, and_, cast, func, or_, select, update
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.deps import DbSession, require_permission
from app.core.errors import NotFoundError, ValidationError
from app.core.money import format_pkr, paisa_to_rupees
from app.core.permissions import Permission
from app.models.catalog import Category, Product, ProductImage, ProductVariant
from app.models.content import SupportTicket
from app.models.enums import (
    MovementReason,
    NotificationStatus,
    OrderStatus,
    ProductStatus,
    ReturnStatus,
    ReviewStatus,
    ShipmentStatus,
    WoodSpecies,
)
from app.models.identity import User
from app.models.inventory import StockLevel, StockMovement
from app.models.ops import AuditLog, NotificationOutbox, SearchQueryLog, StoreSetting
from app.models.order import (
    Order,
    OrderEvent,
    OrderItem,
    Refund,
    ReturnRequest,
    Shipment,
)
from app.models.review import Review, ReviewReply
from app.schemas.common import Message, Money, Page, Schema
from app.services import notifications
from app.services.order_ops import (
    assert_order_transition,
    credit_loyalty_on_delivery,
    record_payment_refund,
    reverse_order,
)

router = APIRouter(prefix="/admin", tags=["admin"])

FULFILLED = (OrderStatus.DELIVERED, OrderStatus.SHIPPED, OrderStatus.OUT_FOR_DELIVERY)


def audit(
    db,
    actor: User,
    *,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None,
    summary: str,
    changes: dict | None = None,
) -> None:
    db.add(AuditLog(
        actor_id=actor.id,
        actor_email=actor.email,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        changes=changes or {},
    ))


# ── Dashboard ────────────────────────────────────────────────────────────────
@router.get("/dashboard")
def dashboard(
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.ANALYTICS_VIEW))],
    days: int = Query(30, ge=1, le=365),
) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=days)
    previous_since = since - timedelta(days=days)

    def totals(start: datetime, end: datetime) -> tuple[int, int]:
        row = db.execute(
            select(func.coalesce(func.sum(Order.total_paisa), 0), func.count(Order.id))
            .where(
                Order.placed_at >= start,
                Order.placed_at < end,
                Order.status.notin_([OrderStatus.CANCELLED]),
            )
        ).one()
        return int(row[0]), int(row[1])

    now = datetime.now(UTC)
    revenue, orders = totals(since, now)
    prev_revenue, prev_orders = totals(previous_since, since)

    def change(current: float, previous: float) -> float | None:
        if not previous:
            return None
        return round((current - previous) / previous * 100, 1)

    # Daily series for the trend chart.
    series = db.execute(
        select(
            func.date_trunc("day", Order.placed_at).label("day"),
            func.coalesce(func.sum(Order.total_paisa), 0),
            func.count(Order.id),
        )
        .where(Order.placed_at >= since, Order.status != OrderStatus.CANCELLED)
        .group_by("day")
        .order_by("day")
    ).all()

    status_counts = dict(
        db.execute(
            select(Order.status, func.count()).group_by(Order.status)
        ).all()
    )

    best_sellers = db.execute(
        select(
            OrderItem.product_name,
            func.sum(OrderItem.quantity).label("units"),
            func.sum(OrderItem.line_total_paisa).label("revenue"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.placed_at >= since, Order.status != OrderStatus.CANCELLED)
        .group_by(OrderItem.product_name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(8)
    ).all()

    low_stock = db.execute(
        select(Product.name, ProductVariant.sku, StockLevel.on_hand, StockLevel.available)
        .join(ProductVariant, ProductVariant.id == StockLevel.variant_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .where(StockLevel.available <= StockLevel.low_stock_threshold)
        .order_by(StockLevel.available)
        .limit(10)
    ).all()

    new_customers = db.scalar(
        select(func.count()).select_from(User).where(User.created_at >= since)
    ) or 0

    pending_reviews = db.scalar(
        select(func.count()).select_from(Review).where(Review.status == ReviewStatus.PENDING)
    ) or 0

    open_returns = db.scalar(
        select(func.count()).select_from(ReturnRequest).where(
            ReturnRequest.status.in_([ReturnStatus.REQUESTED, ReturnStatus.APPROVED])
        )
    ) or 0

    zero_result_searches = db.execute(
        select(SearchQueryLog.query, func.count())
        .where(SearchQueryLog.result_count == 0)
        .group_by(SearchQueryLog.query)
        .order_by(func.count().desc())
        .limit(8)
    ).all()

    return {
        "period_days": days,
        "revenue": {"paisa": revenue, "display": format_pkr(revenue),
                    "change_percent": change(revenue, prev_revenue)},
        "orders": {"count": orders, "change_percent": change(orders, prev_orders)},
        "average_order_value": {
            "paisa": revenue // orders if orders else 0,
            "display": format_pkr(revenue // orders if orders else 0),
        },
        "new_customers": new_customers,
        "series": [
            {"date": row[0].date().isoformat(), "revenue_paisa": int(row[1]),
             "revenue_rupees": int(row[1]) // 100, "orders": int(row[2])}
            for row in series
        ],
        "status_counts": {k.value: v for k, v in status_counts.items()},
        "best_sellers": [
            {"name": row[0], "units": int(row[1]),
             "revenue": format_pkr(int(row[2]))}
            for row in best_sellers
        ],
        "low_stock": [
            {"product": row[0], "sku": row[1], "on_hand": row[2], "available": row[3]}
            for row in low_stock
        ],
        "attention": {
            "pending_reviews": pending_reviews,
            "open_returns": open_returns,
            "flagged_orders": db.scalar(
                select(func.count()).select_from(Order).where(Order.is_flagged)
            ) or 0,
            "open_tickets": db.scalar(
                select(func.count()).select_from(SupportTicket)
                .where(SupportTicket.status == "open")
            ) or 0,
        },
        "zero_result_searches": [
            {"query": row[0], "count": int(row[1])} for row in zero_result_searches
        ],
    }


# ── Orders ───────────────────────────────────────────────────────────────────
class OrderRow(Schema):
    id: uuid.UUID
    order_number: str
    customer: str
    email: str | None
    status: OrderStatus
    status_label: str
    total: Money
    item_count: int
    city: str
    placed_at: datetime
    is_flagged: bool


@router.get("/orders", response_model=Page[OrderRow])
def list_orders(
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.ORDER_VIEW))],
    q: str | None = None,
    status_filter: Annotated[OrderStatus | None, Query(alias="status")] = None,
    flagged: bool = False,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
) -> Page[OrderRow]:
    conditions = []
    if status_filter:
        conditions.append(Order.status == status_filter)
    if flagged:
        conditions.append(Order.is_flagged.is_(True))
    if q:
        term = f"%{q.lower()}%"
        conditions.append(
            or_(
                func.lower(Order.order_number).like(term),
                func.lower(Order.shipping_name).like(term),
                func.lower(Order.shipping_city).like(term),
                func.lower(func.coalesce(Order.guest_email, "")).like(term),
            )
        )

    where = and_(*conditions) if conditions else True
    total = db.scalar(select(func.count()).select_from(Order).where(where)) or 0

    rows = db.scalars(
        select(Order)
        .where(where)
        .order_by(Order.placed_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .options(selectinload(Order.items))
    ).all()

    items = [
        OrderRow(
            id=order.id,
            order_number=order.order_number,
            customer=order.shipping_name,
            email=order.user.email if order.user else order.guest_email,
            status=order.status,
            status_label=order.status.label,
            total=Money.of(order.total_paisa),
            item_count=sum(i.quantity for i in order.items),
            city=order.shipping_city,
            placed_at=order.placed_at,
            is_flagged=order.is_flagged,
        )
        for order in rows
    ]
    return Page.of(items, total, page, per_page)


class StatusUpdate(BaseModel):
    status: OrderStatus
    note: str | None = None
    tracking_number: str | None = None


@router.post("/orders/{order_id}/status", response_model=Message)
def update_order_status(
    order_id: uuid.UUID,
    payload: StatusUpdate,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.ORDER_UPDATE_STATUS))],
) -> Message:
    order = db.scalar(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items), selectinload(Order.payments))
    )
    if order is None:
        raise NotFoundError("Order not found.")

    previous = order.status
    # A real state machine: this rejects delivered->cancelled, refunded->shipped,
    # and setting the same status twice, so cancelling can never restock twice.
    assert_order_transition(previous, payload.status)
    order.status = payload.status
    now = datetime.now(UTC)

    if payload.status is OrderStatus.CONFIRMED and not order.confirmed_at:
        order.confirmed_at = now
    if payload.status is OrderStatus.DELIVERED:
        order.delivered_at = now
        # Points promised at checkout are only credited now, once, on delivery.
        credit_loyalty_on_delivery(db, order)
    if payload.status is OrderStatus.CANCELLED:
        order.cancelled_at = now
        order.cancellation_reason = payload.note or "Cancelled by staff"
        # Full reversal: stock, redeemed loyalty, coupon, sales count, payment.
        reverse_order(db, order, actor_id=actor.id)

    if payload.status is OrderStatus.SHIPPED and payload.tracking_number:
        db.add(Shipment(
            order_id=order.id,
            courier=order.courier,
            tracking_number=payload.tracking_number,
            status=ShipmentStatus.IN_TRANSIT,
            dispatched_at=now,
        ))

    db.add(OrderEvent(
        order_id=order.id,
        event_type="status_change",
        message=payload.note or f"Status changed to {payload.status.label}",
        from_status=previous,
        to_status=payload.status,
        actor_id=actor.id,
    ))

    recipient = order.user.email if order.user else order.guest_email
    template = {
        OrderStatus.SHIPPED: "order_shipped",
        OrderStatus.DELIVERED: "order_delivered",
        OrderStatus.CANCELLED: "order_cancelled",
    }.get(payload.status)
    if recipient and template:
        notifications.email(
            db, template, recipient, user=order.user, order_id=order.id,
            context={
                "order_number": order.order_number,
                "order_url": f"{settings.PUBLIC_URL}/account/orders/{order.order_number}",
                "courier": order.courier.label if order.courier else "our courier",
                "tracking_number": payload.tracking_number,
                "reason": payload.note,
            },
        )

    audit(db, actor, action="order.status_change", entity_type="order",
          entity_id=order.id,
          summary=f"{order.order_number}: {previous.label} to {payload.status.label}",
          changes={"from": previous.value, "to": payload.status.value})

    return Message(message=f"Order marked as {payload.status.label}.")


class RefundIn(BaseModel):
    amount_paisa: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=300)
    method: str = "store_credit"


@router.post("/orders/{order_id}/refund", response_model=Message)
def refund_order(
    order_id: uuid.UUID,
    payload: RefundIn,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.ORDER_REFUND))],
) -> Message:
    # Lock the order so two overlapping refunds cannot both read the same
    # starting balance and each write an absolute total, losing one refund.
    order = db.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if order is None:
        raise NotFoundError("Order not found.")

    remaining = order.total_paisa - order.refunded_paisa
    if payload.amount_paisa > remaining:
        raise ValidationError(
            f"Only {format_pkr(remaining)} is left to refund on this order."
        )

    order.refunded_paisa = Order.refunded_paisa + payload.amount_paisa
    db.flush()
    db.refresh(order, ["refunded_paisa"])
    if order.refunded_paisa >= order.total_paisa:
        order.status = OrderStatus.REFUNDED

    db.add(Refund(
        order_id=order.id,
        amount_paisa=payload.amount_paisa,
        reason=payload.reason,
        method=payload.method,
        processed_by_id=actor.id,
        processed_at=datetime.now(UTC),
    ))
    record_payment_refund(db, order, payload.amount_paisa)

    # COD money is refunded out of band, so store credit is the honest default.
    if payload.method == "store_credit" and order.user_id:
        customer = db.get(User, order.user_id, with_for_update=True)
        if customer:
            customer.store_credit_paisa = User.store_credit_paisa + payload.amount_paisa

    db.add(OrderEvent(
        order_id=order.id,
        event_type="refund",
        message=f"Refunded {format_pkr(payload.amount_paisa)}: {payload.reason}",
        actor_id=actor.id,
    ))

    recipient = order.user.email if order.user else order.guest_email
    if recipient:
        notifications.email(
            db, "refund_processed", recipient, user=order.user, order_id=order.id,
            context={"order_number": order.order_number,
                     "amount_paisa": payload.amount_paisa,
                     "method": payload.method.replace("_", " ")},
        )

    audit(db, actor, action="order.refund", entity_type="order", entity_id=order.id,
          summary=f"Refunded {format_pkr(payload.amount_paisa)} on {order.order_number}")

    return Message(message=f"Refunded {format_pkr(payload.amount_paisa)}.")


def _csv_cell(value: object) -> str:
    """Neutralise spreadsheet formula injection in customer-supplied text.

    Excel and Sheets evaluate a cell that starts with =, +, -, @, tab or CR as a
    formula. A customer whose name is =HYPERLINK(...) would otherwise run code on
    the workstation of any admin who opens the export.
    """
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


@router.get("/orders/export")
def export_orders(
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.ORDER_VIEW))],
) -> Response:
    rows = db.scalars(
        select(Order).order_by(Order.placed_at.desc()).options(selectinload(Order.items))
    ).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Order", "Date", "Customer", "City", "Province", "Status", "Items",
        "Subtotal", "Discount", "Shipping", "COD fee", "GST", "Total",
    ])
    for order in rows:
        writer.writerow([
            order.order_number,
            order.placed_at.date().isoformat(),
            _csv_cell(order.shipping_name),
            _csv_cell(order.shipping_city),
            order.shipping_province.label,
            order.status.label,
            sum(i.quantity for i in order.items),
            paisa_to_rupees(order.subtotal_paisa),
            paisa_to_rupees(order.discount_paisa),
            paisa_to_rupees(order.shipping_paisa),
            paisa_to_rupees(order.cod_surcharge_paisa),
            paisa_to_rupees(order.tax_paisa),
            paisa_to_rupees(order.total_paisa),
        ])

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="woodcroft-orders.csv"'},
    )


# ── Products ─────────────────────────────────────────────────────────────────
class ProductRow(Schema):
    id: uuid.UUID
    name: str
    slug: str
    category: str
    status: ProductStatus
    price: Money
    stock: int
    variant_count: int
    rating_average: float
    is_featured: bool


@router.get("/products", response_model=Page[ProductRow])
def list_products(
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.PRODUCT_VIEW))],
    q: str | None = None,
    status_filter: Annotated[ProductStatus | None, Query(alias="status")] = None,
    low_stock: bool = False,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
) -> Page[ProductRow]:
    conditions = [Product.deleted_at.is_(None)]
    if status_filter:
        conditions.append(Product.status == status_filter)
    if q:
        conditions.append(func.lower(Product.name).like(f"%{q.lower()}%"))

    where = and_(*conditions)
    total = db.scalar(select(func.count()).select_from(Product).where(where)) or 0

    products = db.scalars(
        select(Product)
        .where(where)
        .order_by(Product.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .options(selectinload(Product.variants), selectinload(Product.category))
    ).all()

    stock_rows = dict(
        db.execute(
            select(ProductVariant.product_id, func.sum(StockLevel.available))
            .join(StockLevel, StockLevel.variant_id == ProductVariant.id)
            .where(ProductVariant.product_id.in_([p.id for p in products] or [uuid.uuid4()]))
            .group_by(ProductVariant.product_id)
        ).all()
    )

    items = [
        ProductRow(
            id=product.id,
            name=product.name,
            slug=product.slug,
            category=product.category.name if product.category else "",
            status=product.status,
            price=Money.of(product.base_price_paisa),
            stock=int(stock_rows.get(product.id) or 0),
            variant_count=len(product.variants),
            rating_average=float(product.rating_average),
            is_featured=product.is_featured,
        )
        for product in products
    ]
    if low_stock:
        items = [row for row in items if row.stock <= 5]
    return Page.of(items, total, page, per_page)


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    category_id: uuid.UUID
    base_price_paisa: int = Field(gt=0)
    sku: str = Field(min_length=2, max_length=64)
    initial_stock: int = Field(0, ge=0)
    wood_species: WoodSpecies | None = None
    subtitle: str | None = Field(None, max_length=300)
    description: str = ""
    status: ProductStatus = ProductStatus.DRAFT


def _product_slug(db, name: str) -> str:
    import re

    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "product"
    slug = base
    n = 2
    while db.scalar(select(Product.id).where(Product.slug == slug)):
        slug = f"{base}-{n}"
        n += 1
    return slug


@router.post("/products", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.PRODUCT_EDIT))],
) -> dict:
    """Create a product with one default variant, stock and a placeholder image.

    The admin then adds real photos and any extra variants. Keeps the minimum
    needed for a sellable listing in one step."""
    category = db.get(Category, payload.category_id)
    if category is None:
        raise ValidationError("Choose a valid category.")
    if db.scalar(select(ProductVariant.id).where(ProductVariant.sku == payload.sku)):
        raise ValidationError("That SKU is already in use.")

    product = Product(
        category_id=payload.category_id,
        name=payload.name.strip(),
        slug=_product_slug(db, payload.name),
        subtitle=payload.subtitle,
        description=payload.description or "",
        base_price_paisa=payload.base_price_paisa,
        wood_species=payload.wood_species,
        status=payload.status,
        published_at=datetime.now(UTC) if payload.status is ProductStatus.ACTIVE else None,
    )
    db.add(product)
    db.flush()

    variant = ProductVariant(product_id=product.id, sku=payload.sku.strip())
    db.add(variant)
    db.flush()
    db.add(StockLevel(variant_id=variant.id, on_hand=payload.initial_stock))

    # A placeholder image so the listing is never blank; the admin replaces it.
    from app.services.media.photos import write_placeholder

    meta = write_placeholder(
        settings.media_path,
        f"products/{product.slug}/0",
        payload.wood_species or WoodSpecies.SHEESHAM,
        product.name,
    )
    db.add(ProductImage(
        product_id=product.id, alt_text=product.name,
        sort_order=0, is_primary=True, **meta,
    ))

    audit(db, actor, action="product.create", entity_type="product",
          entity_id=product.id, summary=f"Created {product.name}")
    return {"id": str(product.id), "slug": product.slug, "message": "Product created."}


class ProductUpdate(BaseModel):
    name: str | None = None
    base_price_paisa: int | None = Field(None, gt=0)
    status: ProductStatus | None = None
    is_featured: bool | None = None
    is_new_arrival: bool | None = None
    is_bestseller: bool | None = None
    description: str | None = None
    meta_title: str | None = None
    meta_description: str | None = None


@router.patch("/products/{product_id}", response_model=Message)
def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.PRODUCT_EDIT))],
) -> Message:
    product = db.get(Product, product_id)
    if product is None:
        raise NotFoundError("Product not found.")

    changes: dict[str, Any] = {}
    for field, value in payload.model_dump(exclude_none=True).items():
        before = getattr(product, field)
        if before != value:
            changes[field] = {"from": str(before), "to": str(value)}
            setattr(product, field, value)

    if changes:
        audit(db, actor, action="product.update", entity_type="product",
              entity_id=product.id, summary=f"Updated {product.name}", changes=changes)

    return Message(message="Product updated.")


# ── Product images ────────────────────────────────────────────────────────────
class ProductImageOut(Schema):
    id: uuid.UUID
    url: str
    thumb_url: str
    alt_text: str
    is_primary: bool
    sort_order: int
    source: str


MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _image_out(image: ProductImage) -> ProductImageOut:
    return ProductImageOut(
        id=image.id,
        url=f"{settings.MEDIA_URL}/{image.base_path}_800.webp",
        thumb_url=f"{settings.MEDIA_URL}/{image.base_path}_400.webp",
        alt_text=image.alt_text,
        is_primary=image.is_primary,
        sort_order=image.sort_order,
        source=image.source,
    )


@router.get("/products/{product_id}/images", response_model=list[ProductImageOut])
def list_product_images(
    product_id: uuid.UUID,
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.PRODUCT_EDIT))],
) -> list[ProductImageOut]:
    images = db.scalars(
        select(ProductImage)
        .where(ProductImage.product_id == product_id)
        .order_by(ProductImage.sort_order, ProductImage.created_at)
    ).all()
    return [_image_out(i) for i in images]


@router.post(
    "/products/{product_id}/images",
    response_model=ProductImageOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_product_image(
    product_id: uuid.UUID,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.PRODUCT_EDIT))],
    file: Annotated[UploadFile, File()],
) -> ProductImageOut:
    """Upload a real product photo, processed into the webp size family.

    Lets an admin replace the seeded placeholder with the actual product.
    """
    from app.services.media.photos import write_upload

    product = db.get(Product, product_id)
    if product is None:
        raise NotFoundError("Product not found.")

    if file.content_type and not file.content_type.startswith("image/"):
        raise ValidationError("Please upload an image file.")
    data = await file.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise ValidationError("Images must be 8 MB or smaller.")

    existing = db.scalars(
        select(ProductImage).where(ProductImage.product_id == product_id)
    ).all()
    next_order = max((i.sort_order for i in existing), default=-1) + 1
    rel = f"products/{product.slug}/upload-{uuid.uuid4().hex[:8]}"
    try:
        meta = write_upload(settings.media_path, rel, data)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    image = ProductImage(
        product_id=product_id,
        alt_text=f"{product.name}",
        sort_order=next_order,
        is_primary=not existing,  # first image of a product becomes primary
        **meta,
    )
    db.add(image)
    db.flush()
    audit(db, actor, action="product.image_add", entity_type="product",
          entity_id=product_id, summary=f"Added an image to {product.name}")
    return _image_out(image)


@router.post("/products/images/{image_id}/primary", response_model=Message)
def set_primary_image(
    image_id: uuid.UUID,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.PRODUCT_EDIT))],
) -> Message:
    image = db.get(ProductImage, image_id)
    if image is None:
        raise NotFoundError("Image not found.")
    db.execute(
        update(ProductImage)
        .where(ProductImage.product_id == image.product_id)
        .values(is_primary=False)
    )
    image.is_primary = True
    audit(db, actor, action="product.image_primary", entity_type="product",
          entity_id=image.product_id, summary="Changed the primary image")
    return Message(message="Primary image updated.")


@router.delete("/products/images/{image_id}", response_model=Message)
def delete_product_image(
    image_id: uuid.UUID,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.PRODUCT_EDIT))],
) -> Message:
    image = db.get(ProductImage, image_id)
    if image is None:
        raise NotFoundError("Image not found.")

    product_id = image.product_id
    was_primary = image.is_primary
    # Remove the generated files, ignoring any that are already gone.
    for size in image.sizes or ():
        path = settings.media_path / f"{image.base_path}_{size}.webp"
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    db.delete(image)
    db.flush()

    # Keep exactly one primary: promote the next image if we removed the primary.
    if was_primary:
        nxt = db.scalar(
            select(ProductImage)
            .where(ProductImage.product_id == product_id)
            .order_by(ProductImage.sort_order, ProductImage.created_at)
        )
        if nxt is not None:
            nxt.is_primary = True

    audit(db, actor, action="product.image_delete", entity_type="product",
          entity_id=product_id, summary="Removed a product image")
    return Message(message="Image removed.")


# ── Inventory ────────────────────────────────────────────────────────────────
class StockAdjustment(BaseModel):
    variant_id: uuid.UUID
    delta: int
    reason: MovementReason
    note: str | None = None


@router.post("/inventory/adjust", response_model=Message)
def adjust_stock(
    payload: StockAdjustment,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.INVENTORY_ADJUST))],
) -> Message:
    if payload.delta == 0:
        raise ValidationError("An adjustment of zero does nothing.")

    level = db.scalar(
        select(StockLevel)
        .where(StockLevel.variant_id == payload.variant_id)
        .with_for_update()
    )
    if level is None:
        raise NotFoundError("That variant has no stock record.")

    reserved = level.reserved or 0
    old_available = level.on_hand - reserved
    new_balance = level.on_hand + payload.delta
    if new_balance < 0:
        raise ValidationError(
            f"That would take stock to {new_balance}. Only {level.on_hand} on hand."
        )
    if new_balance < level.reserved:
        raise ValidationError(
            f"{level.reserved} units are reserved by open checkouts, so stock "
            f"cannot go below that."
        )

    level.on_hand = new_balance
    if payload.delta > 0:
        level.restocked_at = datetime.now(UTC)

    # A variant coming back into stock is when the "notify me" subscribers are
    # told. Nothing else enqueues this job, so without it the alert never fires.
    if old_available <= 0 < (new_balance - reserved):
        from app.workers.runner import enqueue

        enqueue(
            db,
            "notify_back_in_stock",
            {"variant_id": str(payload.variant_id)},
            dedupe_key=f"back_in_stock:{payload.variant_id}",
        )

    db.add(StockMovement(
        variant_id=payload.variant_id,
        delta=payload.delta,
        balance_after=new_balance,
        reason=payload.reason,
        note=payload.note,
        actor_id=actor.id,
    ))

    audit(db, actor, action="inventory.adjust", entity_type="stock_level",
          entity_id=level.id,
          summary=f"Adjusted stock by {payload.delta:+d} ({payload.reason.value})")

    return Message(message=f"Stock is now {new_balance}.")


@router.get("/inventory")
def inventory(
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.INVENTORY_VIEW))],
    low_only: bool = False,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    stmt = (
        select(
            ProductVariant.id, ProductVariant.sku, Product.name, ProductVariant.name,
            StockLevel.on_hand, StockLevel.reserved, StockLevel.available,
            StockLevel.low_stock_threshold,
        )
        .join(StockLevel, StockLevel.variant_id == ProductVariant.id)
        .join(Product, Product.id == ProductVariant.product_id)
    )
    if low_only:
        stmt = stmt.where(StockLevel.available <= StockLevel.low_stock_threshold)

    rows = db.execute(
        stmt.order_by(StockLevel.available).offset((page - 1) * per_page).limit(per_page)
    ).all()

    return {
        "items": [
            {
                "variant_id": str(row[0]), "sku": row[1], "product": row[2],
                "variant": row[3], "on_hand": row[4], "reserved": row[5],
                "available": row[6], "threshold": row[7],
                "is_low": row[6] <= row[7],
            }
            for row in rows
        ],
        "page": page,
    }


@router.get("/inventory/{variant_id}/movements")
def stock_movements(
    variant_id: uuid.UUID,
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.INVENTORY_VIEW))],
) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(StockMovement)
        .where(StockMovement.variant_id == variant_id)
        .order_by(StockMovement.created_at.desc())
        .limit(100)
    ).all()
    return [
        {
            "delta": row.delta, "balance_after": row.balance_after,
            "reason": row.reason.value, "note": row.note, "at": row.created_at,
        }
        for row in rows
    ]


# ── Customers ────────────────────────────────────────────────────────────────
@router.get("/customers")
def list_customers(
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.CUSTOMER_VIEW))],
    q: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
) -> dict[str, Any]:
    conditions = []
    if q:
        term = f"%{q.lower()}%"
        conditions.append(
            or_(
                func.lower(cast(User.email, String)).like(term),
                func.lower(User.full_name).like(term),
            )
        )
    where = and_(*conditions) if conditions else True

    total = db.scalar(select(func.count()).select_from(User).where(where)) or 0

    # Lifetime value in the same query, so the list does not N+1.
    spend = (
        select(
            Order.user_id,
            func.count(Order.id).label("orders"),
            func.coalesce(func.sum(Order.total_paisa), 0).label("spend"),
        )
        .where(Order.status.notin_([OrderStatus.CANCELLED]))
        .group_by(Order.user_id)
        .subquery()
    )

    rows = db.execute(
        select(User, spend.c.orders, spend.c.spend)
        .outerjoin(spend, spend.c.user_id == User.id)
        .where(where)
        .order_by(func.coalesce(spend.c.spend, 0).desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()

    return {
        "items": [
            {
                "id": str(user.id), "email": user.email, "name": user.full_name,
                "phone": user.phone, "role": user.role.value,
                "is_active": user.is_active,
                "verified": user.email_verified_at is not None,
                "orders": int(orders or 0),
                "lifetime_value": format_pkr(int(spend_total or 0)),
                "lifetime_value_paisa": int(spend_total or 0),
                "joined": user.created_at,
                "segment": (
                    "vip" if (spend_total or 0) > 10_000_000
                    else "returning" if (orders or 0) > 1
                    else "new" if orders else "inactive"
                ),
            }
            for user, orders, spend_total in rows
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


# ── Reviews ──────────────────────────────────────────────────────────────────
@router.get("/reviews")
def list_reviews(
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.REVIEW_MODERATE))],
    status_filter: Annotated[ReviewStatus | None, Query(alias="status")] = ReviewStatus.PENDING,
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
) -> dict[str, Any]:
    where = Review.status == status_filter if status_filter else True
    total = db.scalar(select(func.count()).select_from(Review).where(where)) or 0

    rows = db.scalars(
        select(Review)
        .where(where)
        .order_by(Review.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()

    products = {
        p.id: p.name
        for p in db.scalars(
            select(Product).where(Product.id.in_([r.product_id for r in rows] or [uuid.uuid4()]))
        ).all()
    }

    return {
        "items": [
            {
                "id": str(review.id),
                "product": products.get(review.product_id, ""),
                "author": review.author_name,
                "rating": review.rating,
                "title": review.title,
                "body": review.body,
                "status": review.status.value,
                "verified_purchase": review.order_item_id is not None,
                "helpful_count": review.helpful_count,
                "created_at": review.created_at,
            }
            for review in rows
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


class ModerationIn(BaseModel):
    status: ReviewStatus
    rejection_reason: str | None = None
    reply: str | None = None


@router.post("/reviews/{review_id}/moderate", response_model=Message)
def moderate_review(
    review_id: uuid.UUID,
    payload: ModerationIn,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.REVIEW_MODERATE))],
) -> Message:
    review = db.get(Review, review_id)
    if review is None:
        raise NotFoundError("Review not found.")

    review.status = payload.status
    review.moderated_at = datetime.now(UTC)
    review.moderated_by_id = actor.id
    review.rejection_reason = payload.rejection_reason

    if payload.reply:
        db.add(ReviewReply(
            review_id=review.id, author_id=actor.id,
            display_name="Woodcroft", body=payload.reply,
        ))

    # Approving or rejecting changes the product's public rating, so the
    # denormalised aggregate has to be recomputed now rather than drifting.
    stats = db.execute(
        select(func.avg(Review.rating), func.count(Review.id))
        .where(Review.product_id == review.product_id, Review.status == ReviewStatus.APPROVED)
    ).one()
    product = db.get(Product, review.product_id)
    if product is not None:
        product.rating_average = round(float(stats[0] or 0), 2)
        product.rating_count = int(stats[1] or 0)

    audit(db, actor, action=f"review.{payload.status.value}", entity_type="review",
          entity_id=review.id, summary=f"Review {payload.status.value}")

    return Message(message=f"Review {payload.status.value}.")


# ── Notifications outbox ─────────────────────────────────────────────────────
@router.get("/notifications")
def list_notifications(
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.NOTIFICATION_VIEW))],
    status_filter: Annotated[NotificationStatus | None, Query(alias="status")] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
) -> dict[str, Any]:
    where = NotificationOutbox.status == status_filter if status_filter else True
    total = db.scalar(select(func.count()).select_from(NotificationOutbox).where(where)) or 0

    rows = db.scalars(
        select(NotificationOutbox)
        .where(where)
        .order_by(NotificationOutbox.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()

    return {
        "items": [
            {
                "id": str(row.id), "channel": row.channel.value,
                "template": row.template_key, "recipient": row.recipient,
                "subject": row.subject, "status": row.status.value,
                "driver": row.driver, "attempts": row.attempts,
                "error": row.last_error, "suppressed_reason": row.suppressed_reason,
                "at": row.created_at,
            }
            for row in rows
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/notifications/{message_id}")
def read_notification(
    message_id: uuid.UUID,
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.NOTIFICATION_VIEW))],
) -> dict[str, Any]:
    message = db.get(NotificationOutbox, message_id)
    if message is None:
        raise NotFoundError("Message not found.")
    return {
        "id": str(message.id),
        "channel": message.channel.value,
        "recipient": message.recipient,
        "subject": message.subject,
        "body_html": message.body_html,
        "body_text": message.body_text,
        "status": message.status.value,
        "at": message.created_at,
    }


@router.post("/notifications/{message_id}/resend", response_model=Message)
def resend_notification(
    message_id: uuid.UUID,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.NOTIFICATION_VIEW))],
) -> Message:
    message = notifications.resend(db, message_id)
    if message is None:
        raise NotFoundError("Message not found.")
    return Message(message=f"Resent, status is now {message.status.value}.")


# ── Audit log and settings ───────────────────────────────────────────────────
@router.get("/audit")
def audit_log(
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.AUDIT_VIEW))],
    limit: int = Query(100, le=500),
) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
    ).all()
    return [
        {
            "actor": row.actor_email, "action": row.action,
            "entity": row.entity_type, "summary": row.summary,
            "changes": row.changes, "at": row.created_at,
        }
        for row in rows
    ]


@router.get("/settings")
def list_settings(
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.SETTINGS_MANAGE))],
) -> list[dict[str, Any]]:
    rows = db.scalars(select(StoreSetting).order_by(StoreSetting.group, StoreSetting.key)).all()
    return [
        {
            "key": row.key, "group": row.group, "label": row.label,
            "description": row.description, "value_type": row.value_type,
            "value": row.value,
        }
        for row in rows
    ]


class SettingIn(BaseModel):
    value: Any


@router.put("/settings/{key}", response_model=Message)
def update_setting(
    key: str,
    payload: SettingIn,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.SETTINGS_MANAGE))],
) -> Message:
    setting = db.scalar(select(StoreSetting).where(StoreSetting.key == key))
    if setting is None:
        raise NotFoundError("Setting not found.")

    before = setting.value
    if setting.value_type == "bool":
        setting.value_bool = bool(payload.value)
    elif setting.value_type in ("int", "money"):
        setting.value_int = int(payload.value)
    elif setting.value_type == "json":
        setting.value_json = payload.value
    else:
        setting.value_text = str(payload.value)

    audit(db, actor, action="settings.update", entity_type="store_setting",
          entity_id=setting.id, summary=f"Changed {setting.label}",
          changes={"from": str(before), "to": str(payload.value)})

    return Message(message=f"{setting.label} updated.")
