"""Customer-facing reviews, product Q&A, and return requests.

These are the paths a shopper needs but that the admin side alone did not
provide: the models, the seed data and the moderation tools all existed, but a
real customer had no way to write a review, ask a question, or start a return.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.deps import CurrentShopper, CurrentUser, DbSession, OptionalUser
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.core.money import format_pkr
from app.models.catalog import Product, ProductAnswer, ProductQuestion
from app.models.enums import OrderStatus, ReviewStatus
from app.models.order import Order, OrderItem, ReturnItem, ReturnRequest
from app.models.review import Review, ReviewVote
from app.schemas.common import Message, Schema
from app.services import notifications

router = APIRouter(tags=["engagement"])


# ─────────────────────────────────────────────────────────────────────────────
# Reviews
# ─────────────────────────────────────────────────────────────────────────────
class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    title: str | None = Field(None, max_length=200)
    body: str = Field(min_length=10, max_length=4000)


class ReviewOut(Schema):
    id: uuid.UUID
    author_name: str
    rating: int
    title: str | None
    body: str
    created_at: datetime
    is_verified_purchase: bool
    helpful_count: int
    not_helpful_count: int
    reply: dict | None = None


@router.get("/products/{slug}/reviews", response_model=list[ReviewOut])
def list_reviews(
    slug: str,
    db: DbSession,
    sort: str = Query("recent", pattern="^(recent|helpful|rating_high|rating_low)$"),
    rating: int | None = Query(None, ge=1, le=5),
) -> list[ReviewOut]:
    """Published reviews for a product. This is what the PDP was missing."""
    product = db.scalar(select(Product).where(Product.slug == slug))
    if product is None:
        raise NotFoundError("We could not find that piece.")

    stmt = (
        select(Review)
        .where(Review.product_id == product.id, Review.status == ReviewStatus.APPROVED)
        .options(selectinload(Review.replies))
    )
    if rating is not None:
        stmt = stmt.where(Review.rating == rating)

    order = {
        "recent": Review.created_at.desc(),
        "helpful": Review.helpful_count.desc(),
        "rating_high": Review.rating.desc(),
        "rating_low": Review.rating.asc(),
    }[sort]
    stmt = stmt.order_by(order).limit(100)

    out = []
    for review in db.scalars(stmt).all():
        reply = next((r for r in review.replies if r.is_published), None)
        out.append(
            ReviewOut(
                id=review.id,
                author_name=review.author_name,
                rating=review.rating,
                title=review.title,
                body=review.body,
                created_at=review.created_at,
                is_verified_purchase=review.order_item_id is not None,
                helpful_count=review.helpful_count,
                not_helpful_count=review.not_helpful_count,
                reply=(
                    {"display_name": reply.display_name, "body": reply.body,
                     "created_at": reply.created_at.isoformat()}
                    if reply else None
                ),
            )
        )
    return out


@router.get("/products/{slug}/can-review", response_model=dict)
def can_review(slug: str, db: DbSession, user: CurrentUser) -> dict:
    """Tell the UI whether to show the write-review form, and why not if not."""
    product = db.scalar(select(Product).where(Product.slug == slug))
    if product is None:
        raise NotFoundError("We could not find that piece.")

    existing = db.scalar(
        select(Review).where(
            Review.product_id == product.id, Review.user_id == user.id
        )
    )
    if existing is not None:
        return {"can_review": False, "reason": "already_reviewed",
                "verified": existing.order_item_id is not None}

    order_item = _purchased_line(db, user.id, product.id)
    return {
        "can_review": True,
        "verified": order_item is not None,
        "reason": None,
    }


def _purchased_line(db, user_id: uuid.UUID, product_id: uuid.UUID) -> OrderItem | None:
    """The most recent delivered order line for this user and product.

    Its presence is what makes a review a verified purchase. It is derived, not
    asserted by the client, so the badge cannot be faked.
    """
    return db.scalar(
        select(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.user_id == user_id,
            OrderItem.product_id == product_id,
            Order.status == OrderStatus.DELIVERED,
        )
        .order_by(OrderItem.created_at.desc())
        .limit(1)
    )


@router.post("/products/{slug}/reviews", response_model=Message,
             status_code=status.HTTP_201_CREATED)
def create_review(slug: str, payload: ReviewIn, db: DbSession, user: CurrentUser) -> Message:
    product = db.scalar(select(Product).where(Product.slug == slug))
    if product is None:
        raise NotFoundError("We could not find that piece.")

    # One review per customer per product. The DB has a unique constraint too,
    # but checking here gives a clean message instead of a 409 from Postgres.
    if db.scalar(
        select(Review.id).where(
            Review.product_id == product.id, Review.user_id == user.id
        )
    ):
        raise ConflictError("You have already reviewed this piece.")

    order_item = _purchased_line(db, user.id, product.id)

    db.add(Review(
        product_id=product.id,
        user_id=user.id,
        order_item_id=order_item.id if order_item else None,
        author_name=user.full_name,
        rating=payload.rating,
        title=payload.title,
        body=payload.body,
        # Reviews are held for moderation. The rating aggregate is only touched
        # when a review is approved, so an unapproved review cannot move a
        # product's public score.
        status=ReviewStatus.PENDING,
    ))
    db.flush()
    return Message(
        message="Thank you. Your review will appear once it has been checked."
    )


@router.post("/reviews/{review_id}/helpful", response_model=dict)
def vote_review(
    review_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    helpful: bool = Query(True),
) -> dict:
    """One helpful/not-helpful vote per user, changeable, enforced by a unique
    constraint on (review_id, user_id)."""
    review = db.get(Review, review_id)
    if review is None or review.status is not ReviewStatus.APPROVED:
        raise NotFoundError("Review not found.")

    existing = db.scalar(
        select(ReviewVote).where(
            ReviewVote.review_id == review_id, ReviewVote.user_id == user.id
        )
    )
    if existing is None:
        db.add(ReviewVote(review_id=review_id, user_id=user.id, is_helpful=helpful))
        if helpful:
            review.helpful_count += 1
        else:
            review.not_helpful_count += 1
    elif existing.is_helpful != helpful:
        # Switching the vote moves the count from one bucket to the other.
        existing.is_helpful = helpful
        if helpful:
            review.helpful_count += 1
            review.not_helpful_count = max(0, review.not_helpful_count - 1)
        else:
            review.not_helpful_count += 1
            review.helpful_count = max(0, review.helpful_count - 1)

    return {"helpful_count": review.helpful_count,
            "not_helpful_count": review.not_helpful_count}


# ─────────────────────────────────────────────────────────────────────────────
# Product Q&A
# ─────────────────────────────────────────────────────────────────────────────
class QuestionIn(BaseModel):
    body: str = Field(min_length=5, max_length=1000)


@router.get("/products/{slug}/questions", response_model=list[dict])
def list_questions(slug: str, db: DbSession) -> list[dict]:
    product = db.scalar(select(Product).where(Product.slug == slug))
    if product is None:
        raise NotFoundError("We could not find that piece.")

    questions = db.scalars(
        select(ProductQuestion)
        .where(
            ProductQuestion.product_id == product.id,
            ProductQuestion.is_published.is_(True),
        )
        .options(selectinload(ProductQuestion.answers))
        .order_by(ProductQuestion.helpful_count.desc(), ProductQuestion.created_at.desc())
        .limit(50)
    ).all()

    return [
        {
            "id": str(q.id),
            "body": q.body,
            "asker_name": q.asker_name or "A customer",
            "created_at": q.created_at.isoformat(),
            "helpful_count": q.helpful_count,
            "answers": [
                {
                    "body": a.body,
                    "is_official": a.is_official,
                    "created_at": a.created_at.isoformat(),
                }
                for a in sorted(q.answers, key=lambda a: a.created_at)
                if a.is_published
            ],
        }
        for q in questions
    ]


@router.post("/products/{slug}/questions", response_model=Message,
             status_code=status.HTTP_201_CREATED)
def ask_question(
    slug: str, payload: QuestionIn, db: DbSession, user: OptionalUser
) -> Message:
    product = db.scalar(select(Product).where(Product.slug == slug))
    if product is None:
        raise NotFoundError("We could not find that piece.")

    db.add(ProductQuestion(
        product_id=product.id,
        user_id=user.id if user else None,
        asker_name=user.full_name if user else None,
        body=payload.body,
        # Held until an admin publishes it, so the Q&A block cannot be used as
        # an open comment box.
        is_published=False,
    ))
    db.flush()
    return Message(
        message="Thank you. We will answer and publish your question shortly."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Returns
# ─────────────────────────────────────────────────────────────────────────────
class ReturnLineIn(BaseModel):
    order_item_id: uuid.UUID
    quantity: int = Field(ge=1)


class ReturnIn(BaseModel):
    reason: str = Field(pattern="^(damaged|defective|wrong_item|not_as_described|"
                                "changed_mind|size_issue|other)$")
    customer_note: str | None = Field(None, max_length=1000)
    items: list[ReturnLineIn] = Field(min_length=1)


@router.get("/orders/{order_number}/returnable", response_model=dict)
def returnable_items(order_number: str, db: DbSession, user: CurrentUser) -> dict:
    """What, if anything, on this order can still be returned.

    Returns are allowed only on a delivered order, within the window, and only
    for the quantity not already returned. The UI uses this to decide whether
    to offer the return form at all.
    """
    order = db.scalar(
        select(Order)
        .where(Order.order_number == order_number, Order.user_id == user.id)
        .options(selectinload(Order.items))
    )
    if order is None:
        raise NotFoundError("We could not find that order.")

    window_days = _setting_int(db, "return_window_days", 14)
    within_window = (
        order.delivered_at is not None
        and order.delivered_at > datetime.now(UTC) - timedelta(days=window_days)
    )
    eligible = order.status is OrderStatus.DELIVERED and within_window

    return {
        "eligible": eligible,
        "reason": (
            None if eligible
            else "not_delivered" if order.status is not OrderStatus.DELIVERED
            else "window_closed"
        ),
        "window_days": window_days,
        "items": [
            {
                "order_item_id": str(item.id),
                "product_name": item.product_name,
                "variant_name": item.variant_name,
                "quantity": item.quantity,
                "returnable": item.quantity - item.quantity_returned,
                "line_total": format_pkr(item.line_total_paisa),
            }
            for item in order.items
            if item.quantity - item.quantity_returned > 0
        ],
    }


def _setting_int(db, key: str, fallback: int) -> int:
    from app.models.ops import StoreSetting

    row = db.scalar(select(StoreSetting).where(StoreSetting.key == key))
    return row.value_int if row and row.value_int is not None else fallback


@router.post("/orders/{order_number}/returns", response_model=Message,
             status_code=status.HTTP_201_CREATED)
def request_return(
    order_number: str, payload: ReturnIn, db: DbSession, user: CurrentUser
) -> Message:
    order = db.scalar(
        select(Order)
        .where(Order.order_number == order_number, Order.user_id == user.id)
        .options(selectinload(Order.items))
    )
    if order is None:
        raise NotFoundError("We could not find that order.")

    if order.status is not OrderStatus.DELIVERED:
        raise ConflictError(
            "Returns can only be started once an order has been delivered."
        )

    window_days = _setting_int(db, "return_window_days", 14)
    if order.delivered_at is None or order.delivered_at < datetime.now(
        UTC
    ) - timedelta(days=window_days):
        raise ConflictError(
            f"The {window_days}-day return window for this order has closed."
        )

    items_by_id = {item.id: item for item in order.items}

    # Validate every requested line against what is genuinely still returnable,
    # so a crafted request cannot return more than was bought or ordered.
    validated: list[tuple[OrderItem, int]] = []
    for line in payload.items:
        item = items_by_id.get(line.order_item_id)
        if item is None:
            raise ValidationError("One of the items is not on this order.")
        remaining = item.quantity - item.quantity_returned
        if line.quantity > remaining:
            raise ValidationError(
                f"Only {remaining} of {item.product_name} can still be returned."
            )
        validated.append((item, line.quantity))

    count = db.scalar(select(func.count()).select_from(ReturnRequest)) or 0
    request = ReturnRequest(
        return_number=f"WC-RET-{count + 1:06d}",
        order_id=order.id,
        user_id=user.id,
        reason=payload.reason,
        customer_note=payload.customer_note,
    )
    db.add(request)
    db.flush()

    for item, quantity in validated:
        per_unit = item.line_total_paisa // max(1, item.quantity)
        db.add(ReturnItem(
            return_request_id=request.id,
            order_item_id=item.id,
            quantity=quantity,
            refundable_paisa=per_unit * quantity,
        ))

    recipient = user.email
    notifications.email(
        db, "return_update", recipient, user=user, order_id=order.id,
        context={
            "return_number": request.return_number,
            "status": "requested",
            "note": "We have received your return request and will review it shortly.",
        },
    )

    return Message(
        message=f"Return {request.return_number} started. We will email you with "
                "the next steps."
    )


@router.get("/returns", response_model=list[dict])
def my_returns(db: DbSession, user: CurrentUser) -> list[dict]:
    rows = db.scalars(
        select(ReturnRequest)
        .where(ReturnRequest.user_id == user.id)
        .options(selectinload(ReturnRequest.items))
        .order_by(ReturnRequest.created_at.desc())
    ).all()

    orders = {
        o.id: o.order_number
        for o in db.scalars(
            select(Order).where(Order.id.in_([r.order_id for r in rows] or [uuid.uuid4()]))
        ).all()
    }

    return [
        {
            "return_number": r.return_number,
            "order_number": orders.get(r.order_id, ""),
            "status": r.status.value,
            "reason": r.reason.value.replace("_", " "),
            "created_at": r.created_at.isoformat(),
            "refundable": format_pkr(sum(i.refundable_paisa for i in r.items)),
        }
        for r in rows
    ]
