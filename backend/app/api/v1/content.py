"""Storefront content: blog, static pages, FAQ, banners, testimonials, contact.

Also carries the customer account endpoints that do not belong to auth:
addresses, wishlist, loyalty and referrals.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.deps import CurrentShopper, CurrentUser, DbSession, OptionalUser
from app.core.errors import NotFoundError, ValidationError
from app.models.cart import WishlistItem
from app.models.catalog import Product, ProductTag
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
from app.models.enums import PakistanProvince
from app.models.identity import Address
from app.models.promotion import LoyaltyAccount, LoyaltyTransaction, Referral
from app.models.sequences import ticket_number_seq
from app.schemas.catalog import ProductCardOut, media_url
from app.schemas.common import Message, Money, Schema
from app.services import notifications
from app.services.auth import normalise_phone

router = APIRouter(tags=["content"])


# ── Schemas ──────────────────────────────────────────────────────────────────
class BlogPostOut(Schema):
    id: uuid.UUID
    title: str
    slug: str
    excerpt: str | None
    category: str | None
    author_name: str
    cover_image_url: str | None
    published_at: datetime | None
    reading_minutes: int | None
    body_html: str | None = None


class StaticPageOut(Schema):
    title: str
    slug: str
    body_html: str
    meta_title: str | None
    meta_description: str | None


class FaqOut(Schema):
    id: uuid.UUID
    question: str
    answer_html: str
    category: str


class BannerOut(Schema):
    id: uuid.UUID
    title: str
    subtitle: str | None
    placement: str
    image_url: str | None
    link_url: str | None
    cta_label: str | None
    overlay: str


class TestimonialOut(Schema):
    id: uuid.UUID
    author_name: str
    author_city: str | None
    quote: str
    is_press: bool
    publication: str | None


class AddressIn(BaseModel):
    label: str | None = None
    full_name: str = Field(min_length=2, max_length=120)
    phone: str
    line1: str = Field(min_length=4, max_length=200)
    line2: str | None = None
    area: str | None = None
    landmark: str | None = None
    city: str = Field(min_length=2, max_length=80)
    province: PakistanProvince
    postal_code: str | None = None
    is_default_shipping: bool = False
    is_default_billing: bool = False

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str) -> str:
        return normalise_phone(value) or value


class AddressOut(Schema):
    id: uuid.UUID
    label: str | None
    full_name: str
    phone: str
    line1: str
    line2: str | None
    area: str | None
    landmark: str | None
    city: str
    province: PakistanProvince
    province_label: str
    postal_code: str | None
    is_default_shipping: bool
    is_default_billing: bool


class LoyaltyOut(Schema):
    points_balance: int
    lifetime_points_earned: int
    tier: str
    point_value: Money
    redeemable: Money
    transactions: list[dict]


class ReferralOut(Schema):
    code: str | None
    invited: int
    qualified: int
    total_earned: Money
    share_url: str


class ContactIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    subject: str = Field(min_length=3, max_length=300)
    message: str = Field(min_length=10, max_length=4000)
    order_number: str | None = None


class NewsletterIn(BaseModel):
    email: EmailStr
    name: str | None = None
    source: str = "footer"


# ── Blog ─────────────────────────────────────────────────────────────────────
@router.get("/blog", response_model=list[BlogPostOut])
def list_posts(
    db: DbSession,
    category: str | None = None,
    limit: int = Query(20, le=50),
) -> list[BlogPostOut]:
    stmt = (
        select(BlogPost)
        .where(BlogPost.is_published.is_(True))
        .order_by(BlogPost.published_at.desc())
        .limit(limit)
    )
    if category:
        stmt = stmt.where(BlogPost.category == category)

    return [
        BlogPostOut(
            id=post.id,
            title=post.title,
            slug=post.slug,
            excerpt=post.excerpt,
            category=post.category,
            author_name=post.author_name,
            cover_image_url=media_url(post.cover_image_path, 1600),
            published_at=post.published_at,
            reading_minutes=post.reading_minutes,
        )
        for post in db.scalars(stmt).all()
    ]


@router.get("/blog/{slug}", response_model=BlogPostOut)
def get_post(slug: str, db: DbSession) -> BlogPostOut:
    post = db.scalar(
        select(BlogPost).where(BlogPost.slug == slug, BlogPost.is_published.is_(True))
    )
    if post is None:
        raise NotFoundError("We could not find that article.")

    post.view_count = (post.view_count or 0) + 1
    return BlogPostOut(
        id=post.id,
        title=post.title,
        slug=post.slug,
        excerpt=post.excerpt,
        category=post.category,
        author_name=post.author_name,
        cover_image_url=media_url(post.cover_image_path, 1600),
        published_at=post.published_at,
        reading_minutes=post.reading_minutes,
        body_html=post.body_html,
    )


# ── Static pages, FAQ, banners, testimonials ─────────────────────────────────
@router.get("/pages/{slug}", response_model=StaticPageOut)
def get_page(slug: str, db: DbSession) -> StaticPageOut:
    page = db.scalar(
        select(StaticPage).where(StaticPage.slug == slug, StaticPage.is_published.is_(True))
    )
    if page is None:
        raise NotFoundError("We could not find that page.")
    return StaticPageOut.model_validate(page)


@router.get("/pages", response_model=list[dict])
def list_pages(db: DbSession) -> list[dict]:
    rows = db.scalars(
        select(StaticPage)
        .where(StaticPage.is_published.is_(True), StaticPage.show_in_footer.is_(True))
        .order_by(StaticPage.sort_order)
    ).all()
    return [{"title": p.title, "slug": p.slug} for p in rows]


@router.get("/faq", response_model=list[FaqOut])
def list_faqs(db: DbSession) -> list[FaqOut]:
    rows = db.scalars(
        select(Faq).where(Faq.is_published.is_(True)).order_by(Faq.category, Faq.sort_order)
    ).all()
    return [FaqOut.model_validate(row) for row in rows]


@router.get("/banners", response_model=list[BannerOut])
def list_banners(db: DbSession, placement: str | None = None) -> list[BannerOut]:
    now = datetime.now(UTC)
    stmt = select(Banner).where(Banner.is_active.is_(True)).order_by(Banner.sort_order)
    if placement:
        stmt = stmt.where(Banner.placement == placement)

    return [
        BannerOut(
            id=banner.id,
            title=banner.title,
            subtitle=banner.subtitle,
            placement=banner.placement,
            image_url=media_url(banner.image_path, 1600),
            link_url=banner.link_url,
            cta_label=banner.cta_label,
            overlay=banner.overlay,
        )
        for banner in db.scalars(stmt).all()
        if (banner.starts_at is None or banner.starts_at <= now)
        and (banner.ends_at is None or banner.ends_at >= now)
    ]


@router.get("/testimonials", response_model=list[TestimonialOut])
def list_testimonials(db: DbSession) -> list[TestimonialOut]:
    rows = db.scalars(
        select(Testimonial)
        .where(Testimonial.is_published.is_(True))
        .order_by(Testimonial.sort_order)
    ).all()
    return [TestimonialOut.model_validate(row) for row in rows]


# ── Contact and newsletter ───────────────────────────────────────────────────
@router.post("/contact", response_model=Message, status_code=status.HTTP_201_CREATED)
def contact(payload: ContactIn, db: DbSession, user: OptionalUser) -> Message:
    seq = db.scalar(select(ticket_number_seq.next_value()))
    ticket = SupportTicket(
        ticket_number=f"WC-TKT-{seq + 999:06d}",
        user_id=user.id if user else None,
        contact_email=payload.email,
        contact_name=payload.name,
        subject=payload.subject,
        category="general",
    )
    db.add(ticket)
    db.flush()
    db.add(SupportMessage(
        ticket_id=ticket.id,
        author_id=user.id if user else None,
        is_staff=False,
        body=payload.message,
    ))
    return Message(
        message=f"Thank you. Your reference is {ticket.ticket_number} and we will reply by email."
    )


@router.post("/newsletter", response_model=Message)
def subscribe(payload: NewsletterIn, db: DbSession) -> Message:
    existing = db.scalar(
        select(NewsletterSubscriber).where(NewsletterSubscriber.email == payload.email)
    )
    if existing is not None:
        if existing.unsubscribed_at is not None:
            existing.unsubscribed_at = None
            return Message(message="Welcome back. You are subscribed again.")
        return Message(message="You are already on the list.")

    db.add(NewsletterSubscriber(
        email=payload.email,
        name=payload.name,
        source=payload.source,
        confirmed_at=datetime.now(UTC),
        welcome_coupon_code="WELCOME10",
    ))
    notifications.email(
        db, "welcome", payload.email,
        recipient_name=payload.name,
        context={"coupon_code": "WELCOME10", "discount_percent": 10,
                 "shop_url": f"{settings.PUBLIC_URL}/shop"},
    )
    return Message(message="Thank you. Check your email for your 10% code.")


# ── Addresses ────────────────────────────────────────────────────────────────
def _address_out(address: Address) -> AddressOut:
    return AddressOut(
        id=address.id,
        label=address.label,
        full_name=address.full_name,
        phone=address.phone,
        line1=address.line1,
        line2=address.line2,
        area=address.area,
        landmark=address.landmark,
        city=address.city,
        province=address.province,
        province_label=address.province.label,
        postal_code=address.postal_code,
        is_default_shipping=address.is_default_shipping,
        is_default_billing=address.is_default_billing,
    )


@router.get("/addresses", response_model=list[AddressOut])
def list_addresses(db: DbSession, user: CurrentUser) -> list[AddressOut]:
    rows = db.scalars(
        select(Address)
        .where(Address.user_id == user.id)
        .order_by(Address.is_default_shipping.desc(), Address.created_at)
    ).all()
    return [_address_out(row) for row in rows]


def _clear_defaults(db, user_id: uuid.UUID, shipping: bool, billing: bool) -> None:
    """Only one default of each kind is allowed, enforced by a partial index.

    Clearing the old one first turns a constraint violation into a normal
    update, which is what the customer expects when they tick the box.
    """
    rows = db.scalars(select(Address).where(Address.user_id == user_id)).all()
    for row in rows:
        if shipping:
            row.is_default_shipping = False
        if billing:
            row.is_default_billing = False
    db.flush()


@router.post("/addresses", response_model=AddressOut, status_code=status.HTTP_201_CREATED)
def create_address(payload: AddressIn, db: DbSession, user: CurrentUser) -> AddressOut:
    existing = db.scalar(
        select(func.count()).select_from(Address).where(Address.user_id == user.id)
    ) or 0

    # The first address someone saves is their default, whatever they ticked.
    make_default_shipping = payload.is_default_shipping or existing == 0
    make_default_billing = payload.is_default_billing or existing == 0

    if make_default_shipping or make_default_billing:
        _clear_defaults(db, user.id, make_default_shipping, make_default_billing)

    address = Address(
        user_id=user.id,
        **payload.model_dump(exclude={"is_default_shipping", "is_default_billing"}),
        is_default_shipping=make_default_shipping,
        is_default_billing=make_default_billing,
    )
    db.add(address)
    db.flush()
    return _address_out(address)


@router.put("/addresses/{address_id}", response_model=AddressOut)
def update_address(
    address_id: uuid.UUID, payload: AddressIn, db: DbSession, user: CurrentUser
) -> AddressOut:
    address = db.scalar(
        select(Address).where(Address.id == address_id, Address.user_id == user.id)
    )
    if address is None:
        raise NotFoundError("We could not find that address.")

    if payload.is_default_shipping or payload.is_default_billing:
        _clear_defaults(db, user.id, payload.is_default_shipping, payload.is_default_billing)

    for field, value in payload.model_dump().items():
        setattr(address, field, value)
    db.flush()
    return _address_out(address)


@router.delete("/addresses/{address_id}", response_model=Message)
def delete_address(address_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Message:
    address = db.scalar(
        select(Address).where(Address.id == address_id, Address.user_id == user.id)
    )
    if address is None:
        raise NotFoundError("We could not find that address.")
    db.delete(address)
    return Message(message="Address removed.")


# ── Wishlist ─────────────────────────────────────────────────────────────────
@router.get("/wishlist", response_model=list[ProductCardOut])
def get_wishlist(db: DbSession, shopper: CurrentShopper):
    from app.api.v1.catalog import _card
    from app.services.catalog import _with_cards, live_products

    if not shopper.exists:
        return []

    condition = (
        WishlistItem.user_id == shopper.user_id
        if shopper.user_id
        else WishlistItem.guest_session_id == shopper.guest_session_id
    )
    product_ids = db.scalars(
        select(WishlistItem.product_id)
        .where(condition)
        .order_by(WishlistItem.created_at.desc())
    ).all()
    if not product_ids:
        return []

    products = db.scalars(
        _with_cards(live_products()).where(Product.id.in_(product_ids))
    ).all()
    return [_card(product) for product in products]


@router.post("/wishlist/{product_id}", response_model=Message)
def add_to_wishlist(product_id: uuid.UUID, db: DbSession, shopper: CurrentShopper) -> Message:
    if not shopper.exists:
        raise ValidationError("Sign in or start a session to save items.")

    existing = db.scalar(
        select(WishlistItem).where(
            WishlistItem.product_id == product_id,
            WishlistItem.user_id == shopper.user_id,
            WishlistItem.guest_session_id == shopper.guest_session_id,
        )
    )
    if existing is None:
        db.add(WishlistItem(
            product_id=product_id,
            user_id=shopper.user_id,
            guest_session_id=shopper.guest_session_id,
        ))
    return Message(message="Saved to your wishlist.")


@router.delete("/wishlist/{product_id}", response_model=Message)
def remove_from_wishlist(
    product_id: uuid.UUID, db: DbSession, shopper: CurrentShopper
) -> Message:
    condition = (
        WishlistItem.user_id == shopper.user_id
        if shopper.user_id
        else WishlistItem.guest_session_id == shopper.guest_session_id
    )
    item = db.scalar(
        select(WishlistItem).where(WishlistItem.product_id == product_id, condition)
    )
    if item is not None:
        db.delete(item)
    return Message(message="Removed from your wishlist.")


# ── Loyalty and referrals ────────────────────────────────────────────────────
@router.get("/loyalty", response_model=LoyaltyOut)
def loyalty(db: DbSession, user: CurrentUser) -> LoyaltyOut:
    account = db.scalar(select(LoyaltyAccount).where(LoyaltyAccount.user_id == user.id))
    if account is None:
        account = LoyaltyAccount(user_id=user.id)
        db.add(account)
        db.flush()

    transactions = db.scalars(
        select(LoyaltyTransaction)
        .where(LoyaltyTransaction.account_id == account.id)
        .order_by(LoyaltyTransaction.created_at.desc())
        .limit(20)
    ).all()

    point_value = 100  # one point is worth Rs 1
    return LoyaltyOut(
        points_balance=account.points_balance,
        lifetime_points_earned=account.lifetime_points_earned,
        tier=account.tier,
        point_value=Money.of(point_value),
        redeemable=Money.of(account.points_balance * point_value),
        transactions=[
            {
                "kind": t.kind.value,
                "delta_points": t.delta_points,
                "balance_after": t.balance_after,
                "note": t.note,
                "at": t.created_at,
            }
            for t in transactions
        ],
    )


@router.get("/referrals", response_model=ReferralOut)
def referrals(db: DbSession, user: CurrentUser) -> ReferralOut:
    rows = db.scalars(select(Referral).where(Referral.referrer_id == user.id)).all()
    qualified = [r for r in rows if r.qualified_at is not None]
    return ReferralOut(
        code=user.referral_code,
        invited=len(rows),
        qualified=len(qualified),
        total_earned=Money.of(sum(r.referrer_reward_paisa for r in qualified)),
        share_url=f"{settings.PUBLIC_URL}/register?ref={user.referral_code or ''}",
    )
