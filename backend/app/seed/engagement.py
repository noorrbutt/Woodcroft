"""Seed reviews, Q&A, content pages, carts and support tickets."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models.cart import AbandonedCart, Cart, CartItem, WishlistItem
from app.models.catalog import (
    BackInStockSubscription,
    ProductAnswer,
    ProductQuestion,
)
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
from app.models.enums import OrderStatus, ReviewStatus
from app.models.inventory import StockLevel
from app.models.order import Order, OrderItem
from app.models.ops import AuditLog, SearchQueryLog
from app.models.review import Review, ReviewReply, ReviewVote

REVIEW_TITLES = [
    "Exactly what we wanted", "Beautiful piece", "Worth the wait",
    "Solid and well made", "Better than expected", "Lovely grain",
    "Good but delivery was slow", "Happy with it", "Stunning in person",
    "A bit different to the photos",
]

REVIEW_BODIES_GOOD = [
    "The joinery is genuinely good. You can see it was made by someone who "
    "cared rather than assembled from flat pack. It has settled into the room "
    "beautifully.",
    "Arrived well packed and completely undamaged, which given the size I was "
    "worried about. The grain is even lovelier than the photographs suggest.",
    "We have had it three months now and it still looks new. Wiped down easily "
    "after a few spills. Would buy from Woodcroft again.",
    "Solid sheesham, properly heavy, no wobble at all. The finish is even and "
    "smooth everywhere, including the underside where nobody looks.",
    "Delivery to Karachi took a week but the team called ahead and carried it "
    "in. Very happy with the whole experience.",
]

REVIEW_BODIES_MIXED = [
    "The piece itself is lovely but it took nearly three weeks to arrive and I "
    "had to chase for an update. Worth it in the end.",
    "Slightly darker than it looked on screen. Not a problem for us but worth "
    "knowing if you are matching to existing furniture.",
    "Good quality for the price. One corner had a small mark which they "
    "offered to fix, so no complaints about the service.",
]

REVIEW_BODIES_POOR = [
    "Arrived with a chip on one leg. The return process was straightforward "
    "but I would rather it had been packed better.",
    "Smaller than I expected. The dimensions are on the page so that is on me, "
    "but do measure first.",
]

QUESTIONS = [
    "Does this come assembled or do I need to put it together?",
    "Is the timber solid all the way through or is it veneered?",
    "Can you deliver to Quetta and how long would it take?",
    "What is the weight? I am on a third floor with no lift.",
    "Is the finish food safe?",
    "Can I order this in a different size?",
    "Do you offer a warranty on the joinery?",
]

ANSWERS = [
    "It arrives mostly assembled. The legs bolt on and take about twenty "
    "minutes with the spanner we include.",
    "Solid timber throughout, no veneer and no board. You can see the grain "
    "run continue over the edges.",
    "Yes, we deliver nationwide. Quetta is usually five to seven working days.",
    "The weight is listed in the specifications above. Our delivery team will "
    "carry it up for you at no extra charge.",
    "Yes, we finish all our kitchen pieces with food safe mineral oil.",
    "We can. Send us the dimensions through the contact form and we will quote.",
    "Two years on the joinery. Finish wear from normal use is not covered.",
]


def seed_engagement(s) -> None:
    _reviews(s)
    _questions(s)
    _content(s)
    _carts_and_wishlists(s)
    _support(s)
    _outbox(s)
    _misc(s)
    s.db.flush()


def _reviews(s) -> None:
    """Reviews tied to real delivered order lines, so badges are truthful."""
    delivered_items = s.db.scalars(
        select(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.status == OrderStatus.DELIVERED, OrderItem.product_id.is_not(None))
    ).all()

    made = 0
    seen: set[tuple] = set()

    for item in delivered_items:
        if s.rng.random() > 0.42:
            continue
        order = s.db.get(Order, item.order_id)
        if order is None or order.user_id is None:
            continue
        key = (item.product_id, order.user_id)
        if key in seen:
            continue
        seen.add(key)

        rating = s.rng.choices([5, 4, 3, 2, 1], weights=[56, 26, 10, 5, 3])[0]
        if rating >= 4:
            body = s.rng.choice(REVIEW_BODIES_GOOD)
        elif rating == 3:
            body = s.rng.choice(REVIEW_BODIES_MIXED)
        else:
            body = s.rng.choice(REVIEW_BODIES_POOR)

        # Most published, some awaiting moderation, a few rejected. The
        # moderation queue needs real work in it to be worth looking at.
        status = s.rng.choices(
            [ReviewStatus.APPROVED, ReviewStatus.PENDING, ReviewStatus.REJECTED],
            weights=[82, 13, 5],
        )[0]

        user = s.db.get(type(s.users[0]), order.user_id)
        review = Review(
            product_id=item.product_id,
            user_id=order.user_id,
            order_item_id=item.id,  # this is what earns the verified badge
            author_name=user.full_name if user else "Customer",
            rating=rating,
            title=s.rng.choice(REVIEW_TITLES),
            body=body,
            status=status,
            moderated_at=(
                (order.delivered_at or order.placed_at) + timedelta(days=9)
                if status is not ReviewStatus.PENDING else None
            ),
            moderated_by_id=s.admin.id if s.admin and status is not ReviewStatus.PENDING else None,
            rejection_reason="Contains contact details" if status is ReviewStatus.REJECTED else None,
            helpful_count=s.rng.randint(0, 24),
            not_helpful_count=s.rng.randint(0, 4),
            created_at=(order.delivered_at or order.placed_at) + timedelta(days=s.rng.randint(3, 20)),
        )
        s.db.add(review)
        s.db.flush()
        made += 1

        if status is ReviewStatus.APPROVED and rating <= 3 and s.rng.random() < 0.7:
            s.db.add(ReviewReply(
                review_id=review.id,
                author_id=s.admin.id if s.admin else None,
                display_name="Woodcroft",
                body="Thank you for the honest feedback, and sorry it was not "
                     "right first time. We have passed this to the workshop and "
                     "someone will be in touch.",
            ))

        for voter in s.rng.sample(s.users, min(3, len(s.users))):
            if s.rng.random() < 0.3:
                s.db.add(ReviewVote(
                    review_id=review.id, user_id=voter.id,
                    is_helpful=s.rng.random() < 0.85,
                ))

    _recompute_ratings(s)
    s.log(f"{made} reviews across every moderation state")


def _recompute_ratings(s) -> None:
    """Refresh the denormalised aggregates the product cards read."""
    rows = s.db.execute(
        select(
            Review.product_id,
            func.avg(Review.rating),
            func.count(Review.id),
        )
        .where(Review.status == ReviewStatus.APPROVED)
        .group_by(Review.product_id)
    ).all()

    by_product = {pid: (avg, count) for pid, avg, count in rows}
    for product in s.products:
        average, count = by_product.get(product.id, (0, 0))
        product.rating_average = round(float(average or 0), 2)
        product.rating_count = count


def _questions(s) -> None:
    count = 0
    for product in s.rng.sample(s.products, min(40, len(s.products))):
        for _ in range(s.rng.randint(1, 2)):
            asker = s.rng.choice(s.users)
            question = ProductQuestion(
                product_id=product.id,
                user_id=asker.id,
                asker_name=asker.full_name,
                body=s.rng.choice(QUESTIONS),
                is_published=s.rng.random() < 0.85,
                helpful_count=s.rng.randint(0, 12),
            )
            s.db.add(question)
            s.db.flush()
            count += 1

            if s.rng.random() < 0.8:
                s.db.add(ProductAnswer(
                    question_id=question.id,
                    user_id=s.admin.id if s.admin else None,
                    body=s.rng.choice(ANSWERS),
                    is_official=True,
                    is_published=True,
                    helpful_count=s.rng.randint(0, 20),
                ))
    s.log(f"{count} customer questions")


def _content(s) -> None:
    posts = [
        ("How to care for a sheesham table", "care-sheesham-table", "Care",
         "Sheesham is hard-wearing but it is still a living material. Here is "
         "what actually matters and what you can safely ignore."),
        ("Why we still cut dovetails by hand", "why-hand-cut-dovetails", "Craft",
         "A machine can cut a joint in seconds. We take twenty minutes. This is "
         "the argument for doing it the slow way."),
        ("Choosing between sheesham, teak and mango", "choosing-your-timber", "Craft",
         "Three timbers, three very different pieces of furniture. A practical "
         "guide to picking the right one for the room."),
        ("Styling a small Lahore apartment", "small-apartment-styling", "Styling",
         "Five pieces that make a compact flat feel considered rather than "
         "crowded."),
        ("Where our timber comes from", "our-timber-sourcing", "Sustainability",
         "Every board we buy is traceable. Here is the chain, mill by mill."),
        ("Looking after outdoor teak", "outdoor-teak-care", "Care",
         "Teak silvers outdoors, and that is the wood protecting itself. What to "
         "do if you would rather keep the honey colour."),
    ]
    for index, (title, slug, category, excerpt) in enumerate(posts):
        s.get_or_create(
            BlogPost,
            {
                "title": title,
                "excerpt": excerpt,
                "body_html": (
                    f"<p>{excerpt}</p>"
                    "<p>Every piece we make starts as a rough board in the yard "
                    "behind the workshop. It is stacked, stickered and left to "
                    "settle for months before anyone touches it with a saw. "
                    "Rushing that stage is the single most common reason "
                    "furniture cracks a year later.</p>"
                    "<h2>What to look for</h2>"
                    "<p>Run your hand along the underside of any piece you are "
                    "considering. If the finish stops where the eye stops, the "
                    "maker was cutting corners.</p>"
                ),
                "category": category,
                "author_name": "Woodcroft Workshop",
                "is_published": True,
                "published_at": datetime.now(UTC) - timedelta(days=index * 21 + 5),
                "reading_minutes": s.rng.randint(3, 8),
                "view_count": s.rng.randint(120, 4200),
                "tags": [category.lower()],
            },
            slug=slug,
        )

    pages = [
        ("About Woodcroft", "about", False),
        ("Terms of Service", "terms", True),
        ("Privacy Policy", "privacy", True),
        ("Shipping Policy", "shipping", True),
        ("Return Policy", "returns", True),
        ("Sustainability", "sustainability", False),
        ("Accessibility", "accessibility", True),
    ]
    for order, (title, slug, is_system) in enumerate(pages):
        s.get_or_create(
            StaticPage,
            {
                "title": title,
                "body_html": (
                    f"<h1>{title}</h1>"
                    "<p>Woodcroft is a small workshop in Lahore making solid "
                    "timber furniture for people who intend to keep it. We have "
                    "been cutting joints the same way since 2009.</p>"
                    "<p>If anything here is unclear, write to "
                    "hello@woodcroft.pk and a person will reply.</p>"
                ),
                "is_published": True,
                "show_in_footer": True,
                "sort_order": order,
                "is_system": is_system,
                "meta_title": f"{title} | Woodcroft",
            },
            slug=slug,
        )

    banners = [
        ("Made to be kept", "hero", "Solid timber, cut and joined by hand in Lahore.",
         "/shop", "Explore the collection", "dark"),
        ("The Dining Flash Sale", "strip", "25% off selected dining pieces, ends soon.",
         "/collections/dining", "Shop the sale", "dark"),
        ("Bespoke pieces", "promo_block",
         "Tell us the dimensions. We will build to them.", "/collections/bespoke",
         "Start a commission", "light"),
    ]
    for order, (title, placement, subtitle, link, cta, overlay) in enumerate(banners):
        s.get_or_create(
            Banner,
            {
                "subtitle": subtitle, "link_url": link, "cta_label": cta,
                "overlay": overlay, "sort_order": order, "is_active": True,
            },
            title=title, placement=placement,
        )

    quotes = [
        ("The dining table has become the centre of our house. Four years on it "
         "still looks like the day it arrived.", "Fatima Sheikh", "Lahore", False, None),
        ("I have bought three pieces now. The consistency is what impresses me.",
         "Usman Raza", "Karachi", False, None),
        ("Woodcroft is quietly doing some of the best joinery work in the "
         "country.", "Design Review", None, True, "Design Review"),
        ("They measured my alcove twice before cutting anything. That tells you "
         "everything.", "Hira Malik", "Islamabad", False, None),
    ]
    for order, (quote, author, city, is_press, publication) in enumerate(quotes):
        s.get_or_create(
            Testimonial,
            {
                "quote": quote, "author_city": city, "is_press": is_press,
                "publication": publication, "sort_order": order,
            },
            author_name=author,
        )

    faqs = [
        ("How long does delivery take?", "Shipping",
         "Punjab and Islamabad are usually three to five working days. Sindh and "
         "KP five to seven. Balochistan and the north can take up to ten."),
        ("Do you deliver nationwide?", "Shipping",
         "Yes, everywhere in Pakistan. Cash on delivery is available in most "
         "regions, though not currently in Balochistan and the far north."),
        ("Is the furniture assembled?", "Products",
         "Mostly. Larger pieces have legs that bolt on, which takes about twenty "
         "minutes. We include the tools."),
        ("Can I return something?", "Returns",
         "Within fourteen days of delivery, provided it is unused and in its "
         "original condition. Bespoke pieces cannot be returned."),
        ("What payment methods do you accept?", "Payment",
         "Cash on delivery at the moment. JazzCash and Easypaisa are coming."),
        ("Do you make custom sizes?", "Products",
         "Yes. Our bespoke pieces are built to your dimensions, with a lead time "
         "of eight to ten weeks."),
        ("Is the wood sustainably sourced?", "Sustainability",
         "Every board is traceable to a mill. We publish the chain on our "
         "sustainability page."),
    ]
    for order, (question, category, answer) in enumerate(faqs):
        s.get_or_create(
            Faq,
            {
                "answer_html": f"<p>{answer}</p>",
                "category": category,
                "sort_order": order,
                "helpful_count": s.rng.randint(0, 60),
            },
            question=question,
        )

    for user in s.rng.sample(s.users, min(30, len(s.users))):
        s.get_or_create(
            NewsletterSubscriber,
            {
                "name": user.full_name,
                "user_id": user.id,
                "source": s.rng.choice(["footer", "popup", "checkout"]),
                "confirmed_at": (
                    datetime.now(UTC) if s.rng.random() < 0.8 else None
                ),
                "welcome_coupon_code": "WELCOME10",
            },
            email=user.email,
        )

    s.log("6 blog posts, 7 pages, 3 banners, 4 testimonials, 7 FAQs, 30 subscribers")


def _carts_and_wishlists(s) -> None:
    """Live carts, abandoned carts and wishlists.

    Abandoned carts exist so the recovery campaign and its report have real
    input rather than an empty table.
    """
    active = 0
    abandoned = 0

    for user in s.rng.sample(s.users, min(24, len(s.users))):
        if s.db.scalar(
            select(Cart).where(Cart.user_id == user.id, Cart.is_active.is_(True))
        ):
            continue

        is_abandoned = s.rng.random() < 0.55
        last_activity = datetime.now(UTC) - timedelta(
            hours=s.rng.randint(8, 240) if is_abandoned else s.rng.randint(0, 3)
        )
        cart = Cart(user_id=user.id, last_activity_at=last_activity)
        s.db.add(cart)
        s.db.flush()

        total = 0
        for variant in s.rng.sample(s.variants, s.rng.randint(1, 3)):
            product = next((p for p in s.products if p.id == variant.product_id), None)
            if product is None:
                continue
            unit = variant.price_paisa or product.base_price_paisa
            quantity = s.rng.randint(1, 2)
            total += unit * quantity
            s.db.add(CartItem(
                cart_id=cart.id,
                variant_id=variant.id,
                quantity=quantity,
                unit_price_paisa=unit,
                line_total_paisa=unit * quantity,
            ))

        if is_abandoned:
            abandoned += 1
            s.db.add(AbandonedCart(
                cart_id=cart.id,
                user_id=user.id,
                email=user.email,
                cart_value_paisa=total,
                item_count=s.rng.randint(1, 3),
                detected_at=last_activity + timedelta(hours=4),
                reminder_count=s.rng.randint(0, 2),
                recovered_at=(
                    datetime.now(UTC) if s.rng.random() < 0.15 else None
                ),
            ))
        else:
            active += 1

    wishlists = 0
    for user in s.rng.sample(s.users, min(35, len(s.users))):
        for product in s.rng.sample(s.products, s.rng.randint(1, 5)):
            existing = s.db.scalar(
                select(WishlistItem).where(
                    WishlistItem.user_id == user.id,
                    WishlistItem.product_id == product.id,
                )
            )
            if existing:
                continue
            s.db.add(WishlistItem(user_id=user.id, product_id=product.id))
            wishlists += 1

    # Waiting lists on the variants that are genuinely out of stock.
    out_of_stock = s.db.scalars(
        select(StockLevel).where(StockLevel.on_hand == 0).limit(12)
    ).all()
    for level in out_of_stock:
        for user in s.rng.sample(s.users, s.rng.randint(1, 4)):
            existing = s.db.scalar(
                select(BackInStockSubscription).where(
                    BackInStockSubscription.variant_id == level.variant_id,
                    BackInStockSubscription.email == user.email,
                )
            )
            if existing:
                continue
            s.db.add(BackInStockSubscription(
                variant_id=level.variant_id, user_id=user.id, email=user.email
            ))

    s.log(f"{active} live carts, {abandoned} abandoned, {wishlists} wishlist items")


def _support(s) -> None:
    subjects = [
        ("Where is my order?", "delivery"),
        ("Can I change the finish before it ships?", "order"),
        ("Chip on the table leg", "damage"),
        ("Do you have this in a larger size?", "product"),
        ("Invoice for my company records", "billing"),
    ]
    orders = s.db.scalars(select(Order).limit(40)).all()

    for index, (subject, category) in enumerate(subjects * 3):
        number = f"WC-TKT-{1000 + index}"
        if s.db.scalar(select(SupportTicket).where(SupportTicket.ticket_number == number)):
            continue
        user = s.rng.choice(s.users)
        order = s.rng.choice(orders) if orders and s.rng.random() < 0.6 else None

        ticket = SupportTicket(
            ticket_number=number,
            user_id=user.id,
            order_id=order.id if order else None,
            contact_email=user.email,
            contact_name=user.full_name,
            subject=subject,
            category=category,
            status=s.rng.choice(["open", "pending_customer", "resolved", "closed"]),
            priority=s.rng.choice(["low", "normal", "normal", "high"]),
        )
        s.db.add(ticket)
        s.db.flush()

        s.db.add(SupportMessage(
            ticket_id=ticket.id, author_id=user.id, is_staff=False,
            body="Hello, I wanted to check on this. Thank you.",
        ))
        if ticket.status != "open":
            s.db.add(SupportMessage(
                ticket_id=ticket.id,
                author_id=s.admin.id if s.admin else None,
                is_staff=True,
                body="Thanks for getting in touch. I have looked into this and "
                     "will update you shortly.",
            ))
    s.log("15 support tickets")


def _misc(s) -> None:
    terms = [
        "dining table", "sheesham", "coffee table", "walnut desk", "bookshelf",
        "chopping board", "bed frame", "mirror", "teak bench", "nightstand",
        "wardrobe", "dining chairs", "sideboard", "planter",
    ]
    for term in terms:
        for _ in range(s.rng.randint(2, 18)):
            s.db.add(SearchQueryLog(
                query=term,
                result_count=s.rng.randint(1, 20),
            ))

    # Zero-result searches. These are the most actionable merchandising signal
    # the store produces, so the report needs real examples.
    for term in ["rocking chair", "shoe rack", "bar cabinet", "piano stool"]:
        for _ in range(s.rng.randint(1, 6)):
            s.db.add(SearchQueryLog(query=term, result_count=0))

    if s.admin:
        actions = [
            ("product.update", "product", "Changed price on Lahore Six-Seat Dining Table"),
            ("order.status_change", "order", "Marked order WC-2026-000104 as shipped"),
            ("review.approve", "review", "Approved a 5 star review"),
            ("coupon.create", "coupon", "Created coupon EID25"),
            ("settings.update", "store_setting", "Changed free shipping threshold"),
            ("inventory.adjust", "stock_level", "Corrected stock after a stocktake"),
        ]
        for action, entity, summary in actions:
            s.db.add(AuditLog(
                actor_id=s.admin.id,
                actor_email=s.admin.email,
                action=action,
                entity_type=entity,
                summary=summary,
                changes={"note": "Seeded example"},
                ip_address="203.0.113.10",
            ))

    s.log("search history, zero-result queries and audit log entries")


def _outbox(s) -> None:
    """Replay the notifications those seeded orders would have produced.

    Without this the Admin > Notifications screen is empty on a fresh install,
    which is exactly the screen that demonstrates the outbox exists at all.
    Messages are rendered through the real templates, so what you read here is
    byte for byte what a customer would have received.
    """
    from app.models.enums import OrderStatus
    from app.services import notifications

    orders = s.db.scalars(
        select(Order).order_by(Order.placed_at.desc()).limit(60)
    ).all()

    made = 0
    for order in orders:
        user = s.db.get(type(s.users[0]), order.user_id) if order.user_id else None
        recipient = user.email if user else order.guest_email
        if not recipient:
            continue

        notifications.email(
            s.db, "order_confirmation", recipient, user=user, order_id=order.id,
            recipient_name=order.shipping_name,
            context={
                "order_number": order.order_number,
                "order_url": f"http://localhost:5173/order/{order.order_number}",
                "items": [
                    {
                        "name": item.product_name,
                        "variant": item.variant_name,
                        "quantity": item.quantity,
                        "total_paisa": item.line_total_paisa,
                    }
                    for item in order.items
                ],
                "subtotal_paisa": order.subtotal_paisa,
                "discount_paisa": order.discount_paisa,
                "shipping_paisa": order.shipping_paisa,
                "cod_surcharge_paisa": order.cod_surcharge_paisa,
                "tax_paisa": order.tax_paisa,
                "total_paisa": order.total_paisa,
                "payment_method": "cod",
            },
        )
        made += 1

        if order.status in (OrderStatus.SHIPPED, OrderStatus.OUT_FOR_DELIVERY,
                            OrderStatus.DELIVERED):
            shipment = order.shipments[0] if order.shipments else None
            notifications.email(
                s.db, "order_shipped", recipient, user=user, order_id=order.id,
                recipient_name=order.shipping_name,
                context={
                    "order_number": order.order_number,
                    "order_url": f"http://localhost:5173/account/orders/{order.order_number}",
                    "courier": order.courier.label if order.courier else "TCS",
                    "tracking_number": shipment.tracking_number if shipment else None,
                },
            )
            notifications.sms(
                s.db, "order_shipped", order.shipping_phone, user=user,
                order_id=order.id,
                context={
                    "order_number": order.order_number,
                    "courier": order.courier.label if order.courier else "TCS",
                    "tracking_number": shipment.tracking_number if shipment else None,
                },
            )
            made += 2

        if order.status is OrderStatus.DELIVERED:
            notifications.email(
                s.db, "order_delivered", recipient, user=user, order_id=order.id,
                recipient_name=order.shipping_name,
                context={
                    "order_number": order.order_number,
                    "order_url": f"http://localhost:5173/account/orders/{order.order_number}",
                },
            )
            made += 1

        if order.status is OrderStatus.CANCELLED:
            notifications.email(
                s.db, "order_cancelled", recipient, user=user, order_id=order.id,
                recipient_name=order.shipping_name,
                context={
                    "order_number": order.order_number,
                    "reason": order.cancellation_reason,
                },
            )
            made += 1

    # A couple of marketing sends, so the suppression path is visible too.
    for user in s.rng.sample(s.users, min(12, len(s.users))):
        notifications.email(
            s.db, "abandoned_cart", user.email, user=user,
            context={
                "cart_url": "http://localhost:5173/cart",
                "item_count": s.rng.randint(1, 3),
                "cart_value_paisa": s.rng.randint(500_000, 8_000_000),
                "coupon_code": "WOOD15",
            },
        )
        made += 1

    s.log(f"{made} notification messages in the outbox")
