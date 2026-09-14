"""Admin: CMS, promotions, returns, support and bulk import.

Split from admin.py purely for size. Same conventions: every mutation writes an
audit row, and every route is gated on a granular permission.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime
from decimal import InvalidOperation
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.api.v1.admin import _csv_cell, audit
from app.core.deps import DbSession, require_permission
from app.core.errors import NotFoundError, ValidationError
from app.core.money import format_pkr, paisa_to_rupees, rupees_to_paisa
from app.core.permissions import Permission
from app.models.catalog import Category, Product, ProductVariant
from app.models.content import (
    Banner,
    BlogPost,
    Faq,
    NewsletterSubscriber,
    StaticPage,
    SupportMessage,
    SupportTicket,
    Testimonial,
)
from app.models.enums import (
    DiscountKind,
    DiscountTarget,
    GiftCardStatus,
    MovementReason,
    OrderStatus,
    ProductStatus,
    ReturnStatus,
)
from app.models.identity import User
from app.models.inventory import StockLevel, StockMovement
from app.models.order import Order, OrderItem, ReturnItem, ReturnRequest
from app.models.promotion import Coupon, CouponRedemption, GiftCard, GiftCardTransaction
from app.schemas.common import Message
from app.core.sanitize import clean_html
from app.services import notifications
from app.services.order_ops import assert_return_transition, record_payment_refund

router = APIRouter(prefix="/admin", tags=["admin"])


def _slugify(value: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "untitled"


# ─────────────────────────────────────────────────────────────────────────────
# Blog
# ─────────────────────────────────────────────────────────────────────────────
class BlogPostIn(BaseModel):
    title: str = Field(min_length=3, max_length=220)
    slug: str | None = None
    excerpt: str | None = Field(None, max_length=500)
    body_html: str = ""

    _clean_body = field_validator("body_html")(lambda cls, v: clean_html(v))
    category: str | None = None
    author_name: str = "Woodcroft Workshop"
    is_published: bool = False
    reading_minutes: int | None = None
    meta_title: str | None = None
    meta_description: str | None = None


@router.get("/blog")
def admin_list_posts(
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.CONTENT_MANAGE))],
) -> list[dict[str, Any]]:
    rows = db.scalars(select(BlogPost).order_by(BlogPost.created_at.desc())).all()
    return [
        {
            "id": str(row.id), "title": row.title, "slug": row.slug,
            "category": row.category, "author_name": row.author_name,
            "is_published": row.is_published, "published_at": row.published_at,
            "view_count": row.view_count, "excerpt": row.excerpt,
        }
        for row in rows
    ]


@router.get("/blog/{post_id}")
def admin_get_post(
    post_id: uuid.UUID,
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.CONTENT_MANAGE))],
) -> dict[str, Any]:
    post = db.get(BlogPost, post_id)
    if post is None:
        raise NotFoundError("Article not found.")
    return {
        "id": str(post.id), "title": post.title, "slug": post.slug,
        "excerpt": post.excerpt, "body_html": post.body_html,
        "category": post.category, "author_name": post.author_name,
        "is_published": post.is_published, "reading_minutes": post.reading_minutes,
        "meta_title": post.meta_title, "meta_description": post.meta_description,
    }


@router.post("/blog", response_model=Message, status_code=status.HTTP_201_CREATED)
def admin_create_post(
    payload: BlogPostIn,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.CONTENT_MANAGE))],
) -> Message:
    slug = payload.slug or _slugify(payload.title)
    if db.scalar(select(BlogPost).where(BlogPost.slug == slug)):
        raise ValidationError("An article with that URL already exists.")

    post = BlogPost(
        **payload.model_dump(exclude={"slug"}),
        slug=slug,
        published_at=datetime.now(UTC) if payload.is_published else None,
    )
    db.add(post)
    db.flush()
    audit(db, actor, action="content.create", entity_type="blog_post",
          entity_id=post.id, summary=f"Created article '{post.title}'")
    return Message(message="Article created.")


@router.put("/blog/{post_id}", response_model=Message)
def admin_update_post(
    post_id: uuid.UUID,
    payload: BlogPostIn,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.CONTENT_MANAGE))],
) -> Message:
    post = db.get(BlogPost, post_id)
    if post is None:
        raise NotFoundError("Article not found.")

    was_published = post.is_published
    for field, value in payload.model_dump(exclude={"slug"}).items():
        setattr(post, field, value)
    if payload.slug:
        post.slug = payload.slug

    # Stamp the publish date the first time it goes live, and never again.
    if payload.is_published and not was_published:
        post.published_at = datetime.now(UTC)

    audit(db, actor, action="content.update", entity_type="blog_post",
          entity_id=post.id, summary=f"Updated article '{post.title}'")
    return Message(message="Article saved.")


@router.delete("/blog/{post_id}", response_model=Message)
def admin_delete_post(
    post_id: uuid.UUID,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.CONTENT_MANAGE))],
) -> Message:
    post = db.get(BlogPost, post_id)
    if post is None:
        raise NotFoundError("Article not found.")
    audit(db, actor, action="content.delete", entity_type="blog_post",
          entity_id=post.id, summary=f"Deleted article '{post.title}'")
    db.delete(post)
    return Message(message="Article deleted.")


# ─────────────────────────────────────────────────────────────────────────────
# Static pages
# ─────────────────────────────────────────────────────────────────────────────
class StaticPageIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    slug: str | None = None
    body_html: str = ""

    _clean_body = field_validator("body_html")(lambda cls, v: clean_html(v))
    is_published: bool = True
    show_in_footer: bool = True
    sort_order: int = 0
    meta_title: str | None = None
    meta_description: str | None = None


@router.get("/pages")
def admin_list_pages(
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.CONTENT_MANAGE))],
) -> list[dict[str, Any]]:
    rows = db.scalars(select(StaticPage).order_by(StaticPage.sort_order)).all()
    return [
        {
            "id": str(row.id), "title": row.title, "slug": row.slug,
            "is_published": row.is_published, "show_in_footer": row.show_in_footer,
            "is_system": row.is_system, "sort_order": row.sort_order,
        }
        for row in rows
    ]


@router.get("/pages/{page_id}")
def admin_get_page(
    page_id: uuid.UUID,
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.CONTENT_MANAGE))],
) -> dict[str, Any]:
    page = db.get(StaticPage, page_id)
    if page is None:
        raise NotFoundError("Page not found.")
    return {
        "id": str(page.id), "title": page.title, "slug": page.slug,
        "body_html": page.body_html, "is_published": page.is_published,
        "show_in_footer": page.show_in_footer, "sort_order": page.sort_order,
        "meta_title": page.meta_title, "meta_description": page.meta_description,
        "is_system": page.is_system,
    }


@router.post("/pages", response_model=Message, status_code=status.HTTP_201_CREATED)
def admin_create_page(
    payload: StaticPageIn,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.CONTENT_MANAGE))],
) -> Message:
    slug = payload.slug or _slugify(payload.title)
    if db.scalar(select(StaticPage).where(StaticPage.slug == slug)):
        raise ValidationError("A page with that URL already exists.")
    page = StaticPage(**payload.model_dump(exclude={"slug"}), slug=slug)
    db.add(page)
    db.flush()
    audit(db, actor, action="content.create", entity_type="static_page",
          entity_id=page.id, summary=f"Created page '{page.title}'")
    return Message(message="Page created.")


@router.put("/pages/{page_id}", response_model=Message)
def admin_update_page(
    page_id: uuid.UUID,
    payload: StaticPageIn,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.CONTENT_MANAGE))],
) -> Message:
    page = db.get(StaticPage, page_id)
    if page is None:
        raise NotFoundError("Page not found.")
    for field, value in payload.model_dump(exclude={"slug"}).items():
        setattr(page, field, value)
    if payload.slug and not page.is_system:
        page.slug = payload.slug
    audit(db, actor, action="content.update", entity_type="static_page",
          entity_id=page.id, summary=f"Updated page '{page.title}'")
    return Message(message="Page saved.")


@router.delete("/pages/{page_id}", response_model=Message)
def admin_delete_page(
    page_id: uuid.UUID,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.CONTENT_MANAGE))],
) -> Message:
    page = db.get(StaticPage, page_id)
    if page is None:
        raise NotFoundError("Page not found.")
    # Terms and Privacy are linked from the footer and from checkout. Deleting
    # one by accident would break a legal link, so system pages are protected.
    if page.is_system:
        raise ValidationError(
            f"'{page.title}' is a required page and cannot be deleted. "
            "You can unpublish it instead."
        )
    audit(db, actor, action="content.delete", entity_type="static_page",
          entity_id=page.id, summary=f"Deleted page '{page.title}'")
    db.delete(page)
    return Message(message="Page deleted.")


# ─────────────────────────────────────────────────────────────────────────────
# Banners, testimonials, FAQ
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/banners")
def admin_list_banners(
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.CONTENT_MANAGE))],
) -> list[dict[str, Any]]:
    rows = db.scalars(select(Banner).order_by(Banner.placement, Banner.sort_order)).all()
    return [
        {
            "id": str(row.id), "title": row.title, "subtitle": row.subtitle,
            "placement": row.placement, "link_url": row.link_url,
            "cta_label": row.cta_label, "is_active": row.is_active,
            "starts_at": row.starts_at, "ends_at": row.ends_at,
        }
        for row in rows
    ]


class BannerIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    subtitle: str | None = None
    placement: str = "hero"
    link_url: str | None = None
    cta_label: str | None = None
    overlay: str = "dark"
    is_active: bool = True
    sort_order: int = 0


@router.post("/banners", response_model=Message, status_code=status.HTTP_201_CREATED)
def admin_create_banner(
    payload: BannerIn,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.CONTENT_MANAGE))],
) -> Message:
    banner = Banner(**payload.model_dump())
    db.add(banner)
    db.flush()
    audit(db, actor, action="content.create", entity_type="banner",
          entity_id=banner.id, summary=f"Created banner '{banner.title}'")
    return Message(message="Banner created.")


@router.put("/banners/{banner_id}", response_model=Message)
def admin_update_banner(
    banner_id: uuid.UUID,
    payload: BannerIn,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.CONTENT_MANAGE))],
) -> Message:
    banner = db.get(Banner, banner_id)
    if banner is None:
        raise NotFoundError("Banner not found.")
    for field, value in payload.model_dump().items():
        setattr(banner, field, value)
    audit(db, actor, action="content.update", entity_type="banner",
          entity_id=banner.id, summary=f"Updated banner '{banner.title}'")
    return Message(message="Banner saved.")


@router.delete("/banners/{banner_id}", response_model=Message)
def admin_delete_banner(
    banner_id: uuid.UUID,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.CONTENT_MANAGE))],
) -> Message:
    banner = db.get(Banner, banner_id)
    if banner is None:
        raise NotFoundError("Banner not found.")
    db.delete(banner)
    audit(db, actor, action="content.delete", entity_type="banner",
          entity_id=banner_id, summary="Deleted a banner")
    return Message(message="Banner deleted.")


@router.get("/faqs")
def admin_list_faqs(
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.CONTENT_MANAGE))],
) -> list[dict[str, Any]]:
    rows = db.scalars(select(Faq).order_by(Faq.category, Faq.sort_order)).all()
    return [
        {
            "id": str(row.id), "question": row.question, "answer_html": row.answer_html,
            "category": row.category, "is_published": row.is_published,
            "sort_order": row.sort_order, "helpful_count": row.helpful_count,
        }
        for row in rows
    ]


class FaqIn(BaseModel):
    question: str = Field(min_length=4, max_length=300)
    answer_html: str = Field(min_length=2)

    _clean_answer = field_validator("answer_html")(lambda cls, v: clean_html(v))
    category: str = "general"
    is_published: bool = True
    sort_order: int = 0


@router.post("/faqs", response_model=Message, status_code=status.HTTP_201_CREATED)
def admin_create_faq(
    payload: FaqIn,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.CONTENT_MANAGE))],
) -> Message:
    faq = Faq(**payload.model_dump())
    db.add(faq)
    db.flush()
    audit(db, actor, action="content.create", entity_type="faq",
          entity_id=faq.id, summary="Added an FAQ")
    return Message(message="FAQ added.")


@router.put("/faqs/{faq_id}", response_model=Message)
def admin_update_faq(
    faq_id: uuid.UUID,
    payload: FaqIn,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.CONTENT_MANAGE))],
) -> Message:
    faq = db.get(Faq, faq_id)
    if faq is None:
        raise NotFoundError("FAQ not found.")
    for field, value in payload.model_dump().items():
        setattr(faq, field, value)
    audit(db, actor, action="content.update", entity_type="faq",
          entity_id=faq.id, summary="Updated an FAQ")
    return Message(message="FAQ saved.")


@router.delete("/faqs/{faq_id}", response_model=Message)
def admin_delete_faq(
    faq_id: uuid.UUID,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.CONTENT_MANAGE))],
) -> Message:
    faq = db.get(Faq, faq_id)
    if faq is None:
        raise NotFoundError("FAQ not found.")
    db.delete(faq)
    return Message(message="FAQ deleted.")


# ─────────────────────────────────────────────────────────────────────────────
# Coupons
# ─────────────────────────────────────────────────────────────────────────────
class CouponIn(BaseModel):
    code: str = Field(min_length=3, max_length=40)
    description: str | None = None
    kind: DiscountKind
    value_bp: int | None = Field(None, ge=1, le=10_000)
    value_paisa: int | None = Field(None, ge=1)
    max_discount_paisa: int | None = None
    min_order_paisa: int = 0
    usage_limit: int | None = None
    usage_limit_per_user: int | None = None
    first_order_only: bool = False
    is_active: bool = True
    starts_at: datetime | None = None
    ends_at: datetime | None = None


@router.get("/coupons")
def admin_list_coupons(
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.PROMO_MANAGE))],
) -> list[dict[str, Any]]:
    rows = db.scalars(select(Coupon).order_by(Coupon.created_at.desc())).all()
    now = datetime.now(UTC)

    # How much each coupon has actually cost, which is the number that decides
    # whether a promotion was worth running.
    savings = dict(
        db.execute(
            select(CouponRedemption.coupon_id, func.sum(CouponRedemption.discount_paisa))
            .group_by(CouponRedemption.coupon_id)
        ).all()
    )

    out = []
    for row in rows:
        if not row.is_active:
            state = "disabled"
        elif row.ends_at and row.ends_at < now:
            state = "expired"
        elif row.starts_at and row.starts_at > now:
            state = "scheduled"
        elif row.usage_limit is not None and row.used_count >= row.usage_limit:
            state = "exhausted"
        else:
            state = "live"

        out.append({
            "id": str(row.id), "code": row.code, "description": row.description,
            "kind": row.kind.value, "value_bp": row.value_bp,
            "value_paisa": row.value_paisa,
            "value_display": (
                f"{row.value_bp / 100:g}%" if row.value_bp
                else format_pkr(row.value_paisa) if row.value_paisa
                else "Free delivery"
            ),
            "min_order_paisa": row.min_order_paisa,
            "min_order_display": format_pkr(row.min_order_paisa),
            "usage_limit": row.usage_limit, "used_count": row.used_count,
            "first_order_only": row.first_order_only,
            "is_active": row.is_active, "state": state,
            "starts_at": row.starts_at, "ends_at": row.ends_at,
            "total_saved": format_pkr(int(savings.get(row.id) or 0)),
        })
    return out


def _validate_coupon(payload: CouponIn) -> None:
    if payload.kind is DiscountKind.PERCENTAGE and not payload.value_bp:
        raise ValidationError("A percentage coupon needs a percentage.")
    if payload.kind is DiscountKind.FIXED_AMOUNT and not payload.value_paisa:
        raise ValidationError("A fixed amount coupon needs an amount.")
    if payload.starts_at and payload.ends_at and payload.ends_at <= payload.starts_at:
        raise ValidationError("The end date must be after the start date.")


@router.post("/coupons", response_model=Message, status_code=status.HTTP_201_CREATED)
def admin_create_coupon(
    payload: CouponIn,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.PROMO_MANAGE))],
) -> Message:
    _validate_coupon(payload)
    code = payload.code.strip().upper()
    if db.scalar(select(Coupon).where(Coupon.code == code)):
        raise ValidationError("That code is already in use.")

    coupon = Coupon(
        **payload.model_dump(exclude={"code"}),
        code=code,
        target=(
            DiscountTarget.SHIPPING
            if payload.kind is DiscountKind.FREE_SHIPPING
            else DiscountTarget.ORDER
        ),
    )
    db.add(coupon)
    db.flush()
    audit(db, actor, action="coupon.create", entity_type="coupon",
          entity_id=coupon.id, summary=f"Created coupon {code}")
    return Message(message=f"Coupon {code} created.")


@router.put("/coupons/{coupon_id}", response_model=Message)
def admin_update_coupon(
    coupon_id: uuid.UUID,
    payload: CouponIn,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.PROMO_MANAGE))],
) -> Message:
    _validate_coupon(payload)
    coupon = db.get(Coupon, coupon_id)
    if coupon is None:
        raise NotFoundError("Coupon not found.")

    for field, value in payload.model_dump(exclude={"code"}).items():
        setattr(coupon, field, value)
    audit(db, actor, action="coupon.update", entity_type="coupon",
          entity_id=coupon.id, summary=f"Updated coupon {coupon.code}")
    return Message(message="Coupon saved.")


@router.delete("/coupons/{coupon_id}", response_model=Message)
def admin_delete_coupon(
    coupon_id: uuid.UUID,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.PROMO_MANAGE))],
) -> Message:
    coupon = db.get(Coupon, coupon_id)
    if coupon is None:
        raise NotFoundError("Coupon not found.")

    # A coupon that has been used is part of order history. Disabling keeps the
    # redemption records intact; deleting would orphan them.
    if coupon.used_count:
        coupon.is_active = False
        audit(db, actor, action="coupon.disable", entity_type="coupon",
              entity_id=coupon.id, summary=f"Disabled coupon {coupon.code}")
        return Message(
            message=f"{coupon.code} has been used {coupon.used_count} times, so it "
                    "was disabled rather than deleted."
        )

    audit(db, actor, action="coupon.delete", entity_type="coupon",
          entity_id=coupon.id, summary=f"Deleted coupon {coupon.code}")
    db.delete(coupon)
    return Message(message="Coupon deleted.")


# ─────────────────────────────────────────────────────────────────────────────
# Gift cards
# ─────────────────────────────────────────────────────────────────────────────
class GiftCardIn(BaseModel):
    amount_paisa: int = Field(ge=50_000, le=50_000_000)
    recipient_email: str | None = None
    recipient_name: str | None = None
    message: str | None = None
    quantity: int = Field(1, ge=1, le=50)


@router.get("/gift-cards")
def admin_list_gift_cards(
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.GIFT_CARD_MANAGE))],
) -> list[dict[str, Any]]:
    rows = db.scalars(select(GiftCard).order_by(GiftCard.created_at.desc())).all()
    return [
        {
            "id": str(row.id), "code": row.code,
            "initial": format_pkr(row.initial_balance_paisa),
            "balance": format_pkr(row.balance_paisa),
            "balance_paisa": row.balance_paisa,
            "spent": format_pkr(row.initial_balance_paisa - row.balance_paisa),
            "status": row.status.value,
            "recipient_email": row.recipient_email,
            "recipient_name": row.recipient_name,
            "expires_at": row.expires_at, "created_at": row.created_at,
        }
        for row in rows
    ]


@router.post("/gift-cards", response_model=Message, status_code=status.HTTP_201_CREATED)
def admin_issue_gift_cards(
    payload: GiftCardIn,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.GIFT_CARD_MANAGE))],
) -> Message:
    import secrets
    from datetime import timedelta

    codes: list[str] = []
    for _ in range(payload.quantity):
        # Retry on the astronomically unlikely collision rather than crashing.
        for _attempt in range(10):
            code = "WCGIFT" + "".join(secrets.choice("23456789ABCDEFGHJKLMNPQRSTUVWXYZ")
                                      for _ in range(8))
            if not db.scalar(select(GiftCard).where(GiftCard.code == code)):
                break
        else:
            raise ValidationError("Could not allocate a unique code. Try again.")

        card = GiftCard(
            code=code,
            initial_balance_paisa=payload.amount_paisa,
            balance_paisa=payload.amount_paisa,
            status=GiftCardStatus.ACTIVE,
            recipient_email=payload.recipient_email,
            recipient_name=payload.recipient_name,
            message=payload.message,
            expires_at=datetime.now(UTC) + timedelta(days=365),
        )
        db.add(card)
        db.flush()
        db.add(GiftCardTransaction(
            gift_card_id=card.id, delta_paisa=payload.amount_paisa,
            balance_after_paisa=payload.amount_paisa, note="Issued by admin",
        ))
        codes.append(code)

        if payload.recipient_email:
            notifications.email(
                db, "gift_card_issued", payload.recipient_email,
                recipient_name=payload.recipient_name,
                context={
                    "code": code, "amount_paisa": payload.amount_paisa,
                    "message": payload.message, "sender_name": "Woodcroft",
                },
            )

    audit(db, actor, action="gift_card.issue", entity_type="gift_card",
          entity_id=None,
          summary=f"Issued {payload.quantity} gift card(s) worth "
                  f"{format_pkr(payload.amount_paisa)} each")

    return Message(
        message=f"Issued {len(codes)} gift card(s): {', '.join(codes[:5])}"
                + (" and more" if len(codes) > 5 else "")
    )


@router.post("/gift-cards/{card_id}/cancel", response_model=Message)
def admin_cancel_gift_card(
    card_id: uuid.UUID,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.GIFT_CARD_MANAGE))],
) -> Message:
    card = db.get(GiftCard, card_id)
    if card is None:
        raise NotFoundError("Gift card not found.")
    card.status = GiftCardStatus.CANCELLED
    audit(db, actor, action="gift_card.cancel", entity_type="gift_card",
          entity_id=card.id, summary=f"Cancelled gift card {card.code}")
    return Message(message=f"{card.code} cancelled.")


# ─────────────────────────────────────────────────────────────────────────────
# Returns
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/returns")
def admin_list_returns(
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.RETURN_MANAGE))],
    status_filter: Annotated[ReturnStatus | None, Query(alias="status")] = None,
) -> list[dict[str, Any]]:
    stmt = (
        select(ReturnRequest)
        .order_by(ReturnRequest.created_at.desc())
        .options(selectinload(ReturnRequest.items))
        .limit(100)
    )
    if status_filter:
        stmt = stmt.where(ReturnRequest.status == status_filter)

    rows = db.scalars(stmt).all()
    orders = {
        o.id: o
        for o in db.scalars(
            select(Order).where(
                Order.id.in_([r.order_id for r in rows] or [uuid.uuid4()])
            )
        ).all()
    }
    order_items = {
        i.id: i
        for i in db.scalars(
            select(OrderItem).where(
                OrderItem.id.in_(
                    [item.order_item_id for r in rows for item in r.items] or [uuid.uuid4()]
                )
            )
        ).all()
    }

    return [
        {
            "id": str(row.id),
            "return_number": row.return_number,
            "order_number": orders[row.order_id].order_number if row.order_id in orders else "",
            "customer": orders[row.order_id].shipping_name if row.order_id in orders else "",
            "status": row.status.value,
            "reason": row.reason.value.replace("_", " "),
            "customer_note": row.customer_note,
            "admin_note": row.admin_note,
            "created_at": row.created_at,
            "refundable": format_pkr(sum(i.refundable_paisa for i in row.items)),
            "refundable_paisa": sum(i.refundable_paisa for i in row.items),
            "items": [
                {
                    "name": order_items[i.order_item_id].product_name
                            if i.order_item_id in order_items else "",
                    "quantity": i.quantity,
                    "restock": i.restock,
                }
                for i in row.items
            ],
        }
        for row in rows
    ]


class ReturnDecision(BaseModel):
    status: ReturnStatus
    admin_note: str | None = None
    restock: bool = True
    refund: bool = False


@router.post("/returns/{return_id}/decide", response_model=Message)
def admin_decide_return(
    return_id: uuid.UUID,
    payload: ReturnDecision,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.RETURN_MANAGE))],
) -> Message:
    request = db.scalar(
        select(ReturnRequest)
        .where(ReturnRequest.id == return_id)
        .options(selectinload(ReturnRequest.items))
    )
    if request is None:
        raise NotFoundError("Return not found.")

    now = datetime.now(UTC)
    previous = request.status
    # Reject illegal or repeated moves. Re-entering REFUNDED is the double-payout
    # this guards against; the ledger check below is the second line of defence.
    assert_return_transition(previous, payload.status)
    request.status = payload.status
    request.admin_note = payload.admin_note

    if payload.status is ReturnStatus.APPROVED and not request.approved_at:
        request.approved_at = now
    if payload.status is ReturnStatus.RECEIVED:
        request.received_at = now
    if payload.status in (ReturnStatus.REFUNDED, ReturnStatus.REJECTED):
        request.resolved_at = now

    # Locked up front: the refund branch clamps against the order balance and
    # writes a relative counter, both of which need the current row.
    order = db.get(Order, request.order_id, with_for_update=True)

    # Stock only comes back when the goods physically arrive, and only if the
    # item is actually resellable. Restocking on approval would credit stock
    # that is still in a courier van.
    if payload.status is ReturnStatus.RECEIVED and payload.restock:
        for item in request.items:
            order_item = db.get(OrderItem, item.order_item_id)
            if order_item is None or order_item.variant_id is None:
                continue
            level = db.scalar(
                select(StockLevel)
                .where(StockLevel.variant_id == order_item.variant_id)
                .with_for_update()
            )
            if level is None:
                continue
            level.on_hand += item.quantity
            item.restock = True
            db.add(StockMovement(
                variant_id=order_item.variant_id,
                delta=item.quantity,
                balance_after=level.on_hand,
                reason=MovementReason.RETURN,
                order_id=request.order_id,
                actor_id=actor.id,
                note=f"Return {request.return_number}",
            ))
            order_item.quantity_returned += item.quantity

    if payload.status is ReturnStatus.REFUNDED and order is not None and payload.refund:
        from app.models.order import Refund

        # Idempotent: if a refund already exists for this return, do not pay out
        # again, however many times the button is pressed.
        already = db.scalar(
            select(func.count())
            .select_from(Refund)
            .where(Refund.return_request_id == request.id)
        )
        amount = sum(i.refundable_paisa for i in request.items)
        amount = min(amount, order.total_paisa - order.refunded_paisa)
        if not already and amount > 0:
            order.refunded_paisa = Order.refunded_paisa + amount
            db.flush()
            db.refresh(order, ["refunded_paisa"])
            if order.refunded_paisa >= order.total_paisa:
                order.status = OrderStatus.REFUNDED
            db.add(Refund(
                order_id=order.id,
                return_request_id=request.id,
                amount_paisa=amount,
                reason=f"Return {request.return_number}",
                method="store_credit",
                processed_by_id=actor.id,
                processed_at=now,
            ))
            record_payment_refund(db, order, amount)
            if order.user_id:
                customer = db.get(User, order.user_id, with_for_update=True)
                if customer:
                    customer.store_credit_paisa = User.store_credit_paisa + amount

    recipient = None
    if order is not None:
        recipient = order.user.email if order.user else order.guest_email
    if recipient:
        notifications.email(
            db, "return_update", recipient, user=order.user if order else None,
            order_id=request.order_id,
            context={
                "return_number": request.return_number,
                "status": payload.status.value.replace("_", " "),
                "note": payload.admin_note,
            },
        )

    audit(db, actor, action="return.decide", entity_type="return_request",
          entity_id=request.id,
          summary=f"{request.return_number}: {previous.value} to {payload.status.value}")

    return Message(message=f"Return marked {payload.status.value}.")


# ─────────────────────────────────────────────────────────────────────────────
# Support tickets
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/tickets")
def admin_list_tickets(
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.TICKET_VIEW))],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
) -> list[dict[str, Any]]:
    stmt = (
        select(SupportTicket)
        .order_by(SupportTicket.created_at.desc())
        .options(selectinload(SupportTicket.messages))
        .limit(100)
    )
    if status_filter:
        stmt = stmt.where(SupportTicket.status == status_filter)

    return [
        {
            "id": str(row.id), "ticket_number": row.ticket_number,
            "subject": row.subject, "category": row.category,
            "status": row.status, "priority": row.priority,
            "contact_name": row.contact_name, "contact_email": row.contact_email,
            "created_at": row.created_at,
            "message_count": len(row.messages),
            "last_message": row.messages[-1].body[:120] if row.messages else "",
        }
        for row in db.scalars(stmt).all()
    ]


@router.get("/tickets/{ticket_id}")
def admin_get_ticket(
    ticket_id: uuid.UUID,
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.TICKET_VIEW))],
) -> dict[str, Any]:
    ticket = db.scalar(
        select(SupportTicket)
        .where(SupportTicket.id == ticket_id)
        .options(selectinload(SupportTicket.messages))
    )
    if ticket is None:
        raise NotFoundError("Ticket not found.")

    order = db.get(Order, ticket.order_id) if ticket.order_id else None
    return {
        "id": str(ticket.id), "ticket_number": ticket.ticket_number,
        "subject": ticket.subject, "status": ticket.status,
        "priority": ticket.priority, "category": ticket.category,
        "contact_name": ticket.contact_name, "contact_email": ticket.contact_email,
        "order_number": order.order_number if order else None,
        "messages": [
            {
                "id": str(m.id), "body": m.body, "is_staff": m.is_staff,
                "is_internal": m.is_internal, "at": m.created_at,
            }
            for m in sorted(ticket.messages, key=lambda m: m.created_at)
        ],
    }


class TicketReply(BaseModel):
    body: str = Field(min_length=2, max_length=4000)
    is_internal: bool = False
    status: str | None = None


@router.post("/tickets/{ticket_id}/reply", response_model=Message)
def admin_reply_ticket(
    ticket_id: uuid.UUID,
    payload: TicketReply,
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.TICKET_REPLY))],
) -> Message:
    ticket = db.get(SupportTicket, ticket_id)
    if ticket is None:
        raise NotFoundError("Ticket not found.")

    db.add(SupportMessage(
        ticket_id=ticket.id, author_id=actor.id, is_staff=True,
        body=payload.body, is_internal=payload.is_internal,
    ))
    ticket.last_reply_at = datetime.now(UTC)
    if payload.status:
        ticket.status = payload.status
        if payload.status == "resolved":
            ticket.resolved_at = datetime.now(UTC)
    elif not payload.is_internal:
        ticket.status = "pending_customer"

    # An internal note is for staff only and must never be emailed out.
    if not payload.is_internal:
        notifications.email(
            db, "support_reply", ticket.contact_email,
            recipient_name=ticket.contact_name,
            context={
                "subject": ticket.subject, "body": payload.body,
                "ticket_number": ticket.ticket_number,
            },
        )

    audit(db, actor, action="ticket.reply", entity_type="support_ticket",
          entity_id=ticket.id, summary=f"Replied to {ticket.ticket_number}")

    return Message(
        message="Internal note added." if payload.is_internal else "Reply sent."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Bulk CSV import and export
# ─────────────────────────────────────────────────────────────────────────────
CSV_COLUMNS = [
    "sku", "product_name", "category_slug", "variant_name", "wood_species",
    "price_pkr", "compare_at_pkr", "stock", "status", "subtitle", "description",
]


@router.get("/products/export")
def export_products(
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.PRODUCT_VIEW))],
) -> Response:
    """One row per variant, which is also the shape the importer accepts."""
    rows = db.execute(
        select(ProductVariant, Product, Category, StockLevel)
        .join(Product, Product.id == ProductVariant.product_id)
        .join(Category, Category.id == Product.category_id)
        .outerjoin(StockLevel, StockLevel.variant_id == ProductVariant.id)
        .order_by(Product.name, ProductVariant.sort_order)
    ).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for variant, product, category, stock in rows:
        compare = variant.compare_at_price_paisa or product.compare_at_price_paisa or 0
        writer.writerow([
            variant.sku,
            _csv_cell(product.name),
            category.slug,
            _csv_cell(variant.name or ""),
            product.wood_species.value if product.wood_species else "",
            paisa_to_rupees(variant.price_paisa or product.base_price_paisa),
            paisa_to_rupees(compare) if compare else "",
            stock.on_hand if stock else 0,
            product.status.value,
            _csv_cell(product.subtitle or ""),
            _csv_cell(product.description or ""),
        ])

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="woodcroft-products.csv"'},
    )


@router.post("/products/import")
async def import_products(
    db: DbSession,
    actor: Annotated[User, Depends(require_permission(Permission.PRODUCT_EDIT))],
    file: UploadFile = File(...),
    dry_run: bool = Query(True, description="Validate without writing"),
) -> dict[str, Any]:
    """Update existing variants from a CSV, keyed on SKU.

    Defaults to a dry run. A bulk price change applied to the wrong file is
    expensive and hard to undo, so you have to ask for the write explicitly.

    Rows are validated individually and a bad row is reported rather than
    aborting the whole file, because one typo in row 400 should not throw away
    399 good updates.
    """
    raw = await file.read()
    try:
        text_body = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Excel on Windows commonly saves CSV as cp1252.
        text_body = raw.decode("cp1252", errors="replace")

    reader = csv.DictReader(io.StringIO(text_body))
    if not reader.fieldnames or "sku" not in reader.fieldnames:
        raise ValidationError(
            "The file needs a 'sku' column. Export the current catalogue to "
            "see the expected format."
        )

    updated: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    unchanged = 0

    for line_number, row in enumerate(reader, start=2):
        sku = (row.get("sku") or "").strip()
        if not sku:
            errors.append({"row": line_number, "sku": "", "error": "Missing SKU"})
            continue

        variant = db.scalar(select(ProductVariant).where(ProductVariant.sku == sku))
        if variant is None:
            errors.append({"row": line_number, "sku": sku, "error": "No variant with that SKU"})
            continue

        product = db.get(Product, variant.product_id)
        if product is None:
            errors.append({"row": line_number, "sku": sku, "error": "Variant has no product"})
            continue

        changes: dict[str, Any] = {}

        price_raw = (row.get("price_pkr") or "").strip()
        if price_raw:
            try:
                # Decimal-based, half-up conversion. float() drops the last
                # paisa on values like 12.345 and rounds to even, both wrong for
                # money; rupees_to_paisa exists precisely to avoid that.
                paisa = rupees_to_paisa(price_raw)
            except (InvalidOperation, ValueError):
                errors.append({"row": line_number, "sku": sku,
                               "error": f"'{price_raw}' is not a number"})
                continue
            if paisa <= 0:
                errors.append({"row": line_number, "sku": sku,
                               "error": "Price must be above zero"})
                continue
            current = variant.price_paisa or product.base_price_paisa
            if paisa != current:
                changes["price"] = {
                    "from": str(paisa_to_rupees(current)),
                    "to": str(paisa_to_rupees(paisa)),
                }
                if not dry_run:
                    variant.price_paisa = paisa

        stock_raw = (row.get("stock") or "").strip()
        if stock_raw:
            try:
                quantity = int(float(stock_raw))
            except ValueError:
                errors.append({"row": line_number, "sku": sku,
                               "error": f"'{stock_raw}' is not a whole number"})
                continue
            if quantity < 0:
                errors.append({"row": line_number, "sku": sku,
                               "error": "Stock cannot be negative"})
                continue

            level = db.scalar(
                select(StockLevel).where(StockLevel.variant_id == variant.id)
            )
            if level is not None and level.on_hand != quantity:
                if quantity < level.reserved:
                    errors.append({
                        "row": line_number, "sku": sku,
                        "error": f"{level.reserved} units are reserved by open "
                                 f"checkouts, so stock cannot go to {quantity}",
                    })
                    continue
                changes["stock"] = {"from": level.on_hand, "to": quantity}
                if not dry_run:
                    delta = quantity - level.on_hand
                    level.on_hand = quantity
                    db.add(StockMovement(
                        variant_id=variant.id, delta=delta, balance_after=quantity,
                        reason=MovementReason.CORRECTION, actor_id=actor.id,
                        note=f"CSV import from {file.filename}",
                    ))

        status_raw = (row.get("status") or "").strip().lower()
        if status_raw and status_raw in {s.value for s in ProductStatus}:
            if product.status.value != status_raw:
                changes["status"] = {"from": product.status.value, "to": status_raw}
                if not dry_run:
                    product.status = ProductStatus(status_raw)

        if changes:
            updated.append({"row": line_number, "sku": sku,
                            "product": product.name, "changes": changes})
        else:
            unchanged += 1

    if not dry_run and updated:
        audit(db, actor, action="product.bulk_import", entity_type="product",
              entity_id=None,
              summary=f"Imported {file.filename}: {len(updated)} variants updated",
              changes={"updated": len(updated), "errors": len(errors)})

    return {
        "dry_run": dry_run,
        "updated": updated[:200],
        "updated_count": len(updated),
        "unchanged": unchanged,
        "errors": errors[:200],
        "error_count": len(errors),
        "message": (
            f"Dry run: {len(updated)} would change, {unchanged} unchanged, "
            f"{len(errors)} problems."
            if dry_run
            else f"Applied {len(updated)} updates, {unchanged} unchanged, "
                 f"{len(errors)} skipped."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Newsletter
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/subscribers")
def admin_list_subscribers(
    db: DbSession,
    _: Annotated[User, Depends(require_permission(Permission.CAMPAIGN_MANAGE))],
) -> dict[str, Any]:
    rows = db.scalars(
        select(NewsletterSubscriber)
        .order_by(NewsletterSubscriber.created_at.desc())
        .limit(200)
    ).all()
    confirmed = sum(
        1 for r in rows if r.confirmed_at and not r.unsubscribed_at
    )
    return {
        "total": len(rows),
        "confirmed": confirmed,
        "items": [
            {
                "email": r.email, "name": r.name, "source": r.source,
                "confirmed": r.confirmed_at is not None,
                "unsubscribed": r.unsubscribed_at is not None,
                "at": r.created_at,
            }
            for r in rows
        ],
    }
