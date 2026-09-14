"""Storefront catalog endpoints: categories, listing, search, product detail."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.core.deps import CurrentShopper, DbSession
from app.core.errors import NotFoundError
from app.models.catalog import (
    Category,
    Product,
    ProductVariant,
    RecentlyViewed,
)
from app.models.enums import WoodSpecies
from app.models.review import Review, ReviewStatus
from app.schemas.catalog import (
    CategoryOut,
    Facets,
    ImageOut,
    OptionTypeOut,
    OptionValueOut,
    PersonalizationOptionOut,
    ProductCardOut,
    ProductDetailOut,
    ProductListOut,
    RatingBreakdown,
    SearchSuggestion,
    StockOut,
    TagOut,
    VariantOut,
    media_url,
)
from app.schemas.common import Money
from app.services import catalog as svc

router = APIRouter(tags=["catalog"])


# ── Serialisation helpers ────────────────────────────────────────────────────
def _discount_percent(price: int, compare: int | None) -> int | None:
    if not compare or compare <= price:
        return None
    return round((compare - price) / compare * 100)


def _card(product: Product, *, in_stock: bool | None = None) -> ProductCardOut:
    primary = next(
        (i for i in product.images if i.is_primary),
        product.images[0] if product.images else None,
    )
    return ProductCardOut(
        id=product.id,
        name=product.name,
        slug=product.slug,
        subtitle=product.subtitle,
        category_name=product.category.name if product.category else None,
        price=Money.of(product.base_price_paisa),
        compare_at_price=(
            Money.of(product.compare_at_price_paisa)
            if product.compare_at_price_paisa
            else None
        ),
        discount_percent=_discount_percent(
            product.base_price_paisa, product.compare_at_price_paisa
        ),
        primary_image=ImageOut.from_model(primary) if primary else None,
        rating_average=product.rating_average,
        rating_count=product.rating_count,
        wood_species=product.wood_species,
        wood_species_label=product.wood_species.label if product.wood_species else None,
        tags=[
            TagOut(name=pt.tag.name, slug=pt.tag.slug, accent=pt.tag.accent)
            for pt in product.tags
        ],
        is_in_stock=in_stock if in_stock is not None else True,
        is_new_arrival=product.is_new_arrival,
        is_bestseller=product.is_bestseller,
    )


def _stock_out(variant: ProductVariant, level) -> StockOut:
    available = level.available if level else 0
    low = bool(level and level.is_low and available > 0)
    return StockOut(
        available=available,
        is_in_stock=available > 0 or variant.is_preorder,
        is_low=low,
        remaining_label=f"Only {available} left" if low else None,
        is_preorder=variant.is_preorder,
        preorder_available_at=variant.preorder_available_at,
    )


# ── Categories ───────────────────────────────────────────────────────────────
@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: DbSession) -> list[CategoryOut]:
    """The whole active tree, nested, with product counts."""
    flat = svc.get_category_tree(db)

    nodes: dict[uuid.UUID, CategoryOut] = {}
    for category in flat:
        nodes[category.id] = CategoryOut(
            id=category.id,
            name=category.name,
            slug=category.slug,
            path=category.path,
            depth=category.depth,
            description=category.description,
            image_url=media_url(category.image_path, 800),
            product_count=getattr(category, "_product_count", 0),
            children=[],
        )

    roots: list[CategoryOut] = []
    for category in flat:
        node = nodes[category.id]
        parent = nodes.get(category.parent_id) if category.parent_id else None
        if parent is not None:
            parent.children.append(node)
            # Roll child counts up, so "Dining" shows everything beneath it.
            parent.product_count += node.product_count
        else:
            roots.append(node)
    return roots


@router.get("/categories/{slug}", response_model=CategoryOut)
def get_category(slug: str, db: DbSession) -> CategoryOut:
    category = db.scalar(select(Category).where(Category.slug == slug))
    if category is None or not category.is_active:
        raise NotFoundError("We could not find that collection.")
    return CategoryOut(
        id=category.id,
        name=category.name,
        slug=category.slug,
        path=category.path,
        depth=category.depth,
        description=category.description,
        image_url=media_url(category.image_path, 1600),
    )


# ── Listing and search ───────────────────────────────────────────────────────
@router.get("/products", response_model=ProductListOut)
def list_products(
    db: DbSession,
    q: str | None = None,
    category: str | None = None,
    wood: Annotated[list[str] | None, Query()] = None,
    tag: Annotated[list[str] | None, Query()] = None,
    min_price: int | None = Query(None, description="In paisa"),
    max_price: int | None = Query(None, description="In paisa"),
    min_rating: int | None = Query(None, ge=1, le=5),
    in_stock: bool = False,
    on_sale: bool = False,
    featured: bool = False,
    new_arrivals: bool = False,
    bestsellers: bool = False,
    sort: Literal[
        "relevance", "newest", "price_asc", "price_desc", "rating", "bestselling"
    ] = "newest",
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=60),
) -> ProductListOut:
    category_obj = None
    if category:
        category_obj = db.scalar(select(Category).where(Category.slug == category))
        if category_obj is None:
            raise NotFoundError("We could not find that collection.")

    result = svc.search_products(
        db,
        query=q,
        category=category_obj,
        wood_species=wood,
        tags=tag,
        min_price_paisa=min_price,
        max_price_paisa=max_price,
        min_rating=min_rating,
        in_stock_only=in_stock,
        on_sale_only=on_sale,
        featured_only=featured,
        new_arrivals_only=new_arrivals,
        bestsellers_only=bestsellers,
        sort=sort,
        page=page,
        per_page=per_page,
    )

    products = result["items"]
    stock = svc.stock_for_variants(
        db, [v.id for p in products for v in p.variants]
    )
    in_stock_map = {
        p.id: any(
            (stock.get(v.id).available if stock.get(v.id) else 0) > 0 or v.is_preorder
            for v in p.variants
        )
        for p in products
    }

    if q:
        _log_search(db, q, result["total"])

    return ProductListOut(
        items=[_card(p, in_stock=in_stock_map.get(p.id, False)) for p in products],
        total=result["total"],
        page=result["page"],
        per_page=result["per_page"],
        pages=result["pages"],
        facets=Facets(**result["facets"]),
        did_you_mean=result["did_you_mean"],
    )


def _log_search(db, query: str, result_count: int) -> None:
    """Record the query. Zero-result searches drive merchandising decisions."""
    from app.models.ops import SearchQueryLog

    db.add(SearchQueryLog(query=query.strip()[:200], result_count=result_count))


@router.get("/search/suggest", response_model=list[SearchSuggestion])
def suggest(db: DbSession, q: str = Query(min_length=1)) -> list[SearchSuggestion]:
    hits = svc.autocomplete(db, q)
    out: list[SearchSuggestion] = []

    for category in hits["categories"]:
        out.append(
            SearchSuggestion(kind="category", label=category.name, slug=category.slug)
        )
    for product in hits["products"]:
        primary = next(
            (i for i in product.images if i.is_primary),
            product.images[0] if product.images else None,
        )
        out.append(
            SearchSuggestion(
                kind="product",
                label=product.name,
                slug=product.slug,
                image_url=media_url(primary.base_path, 400) if primary else None,
            )
        )
    return out


@router.get("/search/trending", response_model=list[str])
def trending_searches(db: DbSession, limit: int = Query(8, le=20)) -> list[str]:
    from app.models.ops import SearchQueryLog

    rows = db.execute(
        select(SearchQueryLog.query, func.count().label("n"))
        .where(SearchQueryLog.result_count > 0)
        .group_by(SearchQueryLog.query)
        .order_by(func.count().desc())
        .limit(limit)
    ).all()
    return [r[0] for r in rows]


# ── Product detail ───────────────────────────────────────────────────────────
@router.get("/products/{slug}", response_model=ProductDetailOut)
def get_product(slug: str, db: DbSession, shopper: CurrentShopper) -> ProductDetailOut:
    product = svc.get_product_by_slug(db, slug)
    if product is None:
        raise NotFoundError("We could not find that piece.")

    stock = svc.stock_for_variants(db, [v.id for v in product.variants])

    # Which option values still lead to something buyable, so the picker can
    # grey out a finish that is entirely sold out.
    available_value_ids: set[uuid.UUID] = set()
    for variant in product.variants:
        level = stock.get(variant.id)
        if variant.is_active and ((level and level.available > 0) or variant.is_preorder):
            available_value_ids.update(ov.option_value_id for ov in variant.option_values)

    card = _card(
        product,
        in_stock=any(
            (stock.get(v.id).available if stock.get(v.id) else 0) > 0 or v.is_preorder
            for v in product.variants
        ),
    )

    _record_view(db, product, shopper)

    dimensions = None
    if product.length_mm or product.width_mm or product.height_mm:
        dimensions = {
            "length_mm": product.length_mm,
            "width_mm": product.width_mm,
            "height_mm": product.height_mm,
            "length_cm": round(product.length_mm / 10, 1) if product.length_mm else None,
            "width_cm": round(product.width_mm / 10, 1) if product.width_mm else None,
            "height_cm": round(product.height_mm / 10, 1) if product.height_mm else None,
            "length_in": round(product.length_mm / 25.4, 1) if product.length_mm else None,
            "width_in": round(product.width_mm / 25.4, 1) if product.width_mm else None,
            "height_in": round(product.height_mm / 25.4, 1) if product.height_mm else None,
        }

    return ProductDetailOut(
        **card.model_dump(),
        description=product.description,
        story=product.story,
        care_instructions=product.care_instructions,
        specifications=product.specifications or {},
        dimensions=dimensions,
        weight_g=product.weight_g,
        images=[ImageOut.from_model(i) for i in product.images],
        option_types=[
            OptionTypeOut(
                id=ot.id,
                name=ot.name,
                values=[
                    OptionValueOut(
                        id=ov.id,
                        value=ov.value,
                        swatch=ov.swatch,
                        available=ov.id in available_value_ids,
                    )
                    for ov in ot.values
                ],
            )
            for ot in product.option_types
        ],
        variants=[
            VariantOut(
                id=v.id,
                sku=v.sku,
                name=v.name,
                price=Money.of(v.effective_price_paisa(product)),
                compare_at_price=(
                    Money.of(v.compare_at_price_paisa or product.compare_at_price_paisa)
                    if (v.compare_at_price_paisa or product.compare_at_price_paisa)
                    else None
                ),
                option_value_ids=[ov.option_value_id for ov in v.option_values],
                stock=_stock_out(v, stock.get(v.id)),
                is_active=v.is_active,
            )
            for v in product.variants
        ],
        personalization_options=[
            PersonalizationOptionOut(
                id=po.id,
                key=po.key,
                label=po.label,
                help_text=po.help_text,
                input_type=po.input_type,
                is_required=po.is_required,
                surcharge=Money.of(po.surcharge_paisa),
                surcharge_per_char=Money.of(po.surcharge_per_char_paisa),
                max_length=po.max_length,
                constraints=po.constraints or {},
            )
            for po in product.personalization_options
        ],
        assets=[
            {
                "id": a.id,
                "title": a.title,
                "kind": a.kind,
                "url": f"/media/{a.file_path}",
                "file_size_bytes": a.file_size_bytes,
            }
            for a in product.assets
        ],
        meta_title=product.meta_title,
        meta_description=product.meta_description,
        category_path=product.category.path if product.category else "",
    )


def _record_view(db, product: Product, shopper) -> None:
    """Upsert the recently-viewed row for whoever is browsing."""
    if not shopper.exists:
        return

    from datetime import UTC, datetime

    from sqlalchemy.dialects.postgresql import insert

    values = {
        "product_id": product.id,
        "user_id": shopper.user_id,
        "guest_session_id": shopper.guest_session_id,
        "viewed_at": datetime.now(UTC),
    }
    constraint = (
        "uq_recently_viewed_user" if shopper.user_id else "uq_recently_viewed_guest"
    )
    db.execute(
        insert(RecentlyViewed)
        .values(**values)
        .on_conflict_do_update(
            constraint=constraint, set_={"viewed_at": values["viewed_at"]}
        )
    )


@router.get("/products/{slug}/related", response_model=list[ProductCardOut])
def related(slug: str, db: DbSession) -> list[ProductCardOut]:
    product = svc.get_product_by_slug(db, slug)
    if product is None:
        raise NotFoundError("We could not find that piece.")
    return [_card(p) for p in svc.related_products(db, product)]


@router.get("/products/{slug}/bought-together", response_model=list[ProductCardOut])
def bought_together(slug: str, db: DbSession) -> list[ProductCardOut]:
    product = svc.get_product_by_slug(db, slug)
    if product is None:
        raise NotFoundError("We could not find that piece.")
    return [_card(p) for p in svc.frequently_bought_together(db, product)]


@router.get("/products/{slug}/rating", response_model=RatingBreakdown)
def rating_breakdown(slug: str, db: DbSession) -> RatingBreakdown:
    product = db.scalar(select(Product).where(Product.slug == slug))
    if product is None:
        raise NotFoundError("We could not find that piece.")

    rows = db.execute(
        select(Review.rating, func.count())
        .where(Review.product_id == product.id, Review.status == ReviewStatus.APPROVED)
        .group_by(Review.rating)
    ).all()
    counts = {str(star): 0 for star in range(1, 6)}
    for star, n in rows:
        counts[str(star)] = n

    return RatingBreakdown(
        average=product.rating_average, total=product.rating_count, counts=counts
    )


@router.get("/recently-viewed", response_model=list[ProductCardOut])
def recently_viewed(
    db: DbSession, shopper: CurrentShopper, limit: int = Query(8, le=20)
) -> list[ProductCardOut]:
    if not shopper.exists:
        return []

    condition = (
        RecentlyViewed.user_id == shopper.user_id
        if shopper.user_id
        else RecentlyViewed.guest_session_id == shopper.guest_session_id
    )
    product_ids = db.scalars(
        select(RecentlyViewed.product_id)
        .where(condition)
        .order_by(RecentlyViewed.viewed_at.desc())
        .limit(limit)
    ).all()
    if not product_ids:
        return []

    products = db.scalars(
        svc._with_cards(svc.live_products()).where(Product.id.in_(product_ids))
    ).all()
    order = {pid: i for i, pid in enumerate(product_ids)}
    return [_card(p) for p in sorted(products, key=lambda p: order.get(p.id, 99))]


@router.get("/compare", response_model=list[ProductDetailOut])
def compare(
    db: DbSession,
    shopper: CurrentShopper,
    slugs: Annotated[list[str], Query(min_length=2, max_length=4)],
) -> list[ProductDetailOut]:
    """Side by side comparison of two to four pieces."""
    return [get_product(slug, db, shopper) for slug in slugs]


@router.get("/wood-species", response_model=list[dict])
def wood_species() -> list[dict]:
    """The species list, with the palette the frontend uses for swatches."""
    return [
        {
            "value": s.value,
            "label": s.label,
            "base": s.grain_palette[0],
            "grain": s.grain_palette[1],
            "highlight": s.grain_palette[2],
        }
        for s in WoodSpecies
    ]
