"""Catalog reads: listing, filtering, search, facets, product detail.

Search runs entirely on Postgres. ``product.search_vector`` is a generated,
weighted tsvector with a GIN index, and ``pg_trgm`` on the name handles
autocomplete and "did you mean". For a catalogue of this size that is faster
than an external engine would be, and there is nothing extra to run or keep in
sync.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import Select, and_, func, or_, select, text
from sqlalchemy.orm import Session, selectinload

from app.models.catalog import (
    Category,
    Product,
    ProductImage,
    ProductTag,
    ProductVariant,
    Tag,
)
from app.models.enums import ProductStatus, WoodSpecies
from app.models.inventory import StockLevel

SortKey = Literal[
    "relevance", "newest", "price_asc", "price_desc", "rating", "bestselling"
]

#: Below this a suggestion is more confusing than helpful.
#: Note this is word_similarity, not similarity: plain similarity compares
#: whole strings, so a short query against a long product name scores near
#: zero and nothing is ever suggested.
DID_YOU_MEAN_THRESHOLD = 0.35
AUTOCOMPLETE_THRESHOLD = 0.3


def live_products() -> Select:
    """Base query for anything a shopper is allowed to see."""
    return select(Product).where(
        Product.status == ProductStatus.ACTIVE,
        Product.deleted_at.is_(None),
    )


def _with_cards(stmt: Select) -> Select:
    """Eager-load exactly what a product card renders, and nothing more."""
    return stmt.options(
        selectinload(Product.images),
        selectinload(Product.tags).selectinload(ProductTag.tag),
        selectinload(Product.variants),
        selectinload(Product.category),
    )


def get_category_tree(db: Session, *, include_counts: bool = True) -> list[Category]:
    """Whole tree in one query, assembled in Python.

    A recursive CTE would also work, but the tree is tens of rows and is read
    on every page, so fetching it flat and linking it up is both simpler and
    fewer round trips.
    """
    categories = db.scalars(
        select(Category)
        .where(Category.is_active.is_(True))
        .order_by(Category.depth, Category.sort_order, Category.name)
    ).all()

    counts: dict[uuid.UUID, int] = {}
    if include_counts:
        rows = db.execute(
            select(Product.category_id, func.count(Product.id))
            .where(Product.status == ProductStatus.ACTIVE, Product.deleted_at.is_(None))
            .group_by(Product.category_id)
        ).all()
        counts = {cid: n for cid, n in rows}

    for category in categories:
        category._product_count = counts.get(category.id, 0)  # type: ignore[attr-defined]

    return list(categories)


def descendant_category_ids(db: Session, category: Category) -> list[uuid.UUID]:
    """A category and everything beneath it, via the materialised path."""
    rows = db.scalars(
        select(Category.id).where(
            or_(Category.id == category.id, Category.path.like(f"{category.path}/%"))
        )
    ).all()
    return list(rows)


def _apply_sort(stmt: Select, sort: SortKey, query: str | None) -> Select:
    if sort == "price_asc":
        return stmt.order_by(Product.base_price_paisa.asc(), Product.name)
    if sort == "price_desc":
        return stmt.order_by(Product.base_price_paisa.desc(), Product.name)
    if sort == "rating":
        return stmt.order_by(
            Product.rating_average.desc(), Product.rating_count.desc()
        )
    if sort == "bestselling":
        return stmt.order_by(Product.sales_count.desc(), Product.rating_average.desc())
    if sort == "relevance" and query:
        rank = func.ts_rank(
            Product.search_vector, func.websearch_to_tsquery("english", query)
        )
        return stmt.order_by(rank.desc(), Product.rating_average.desc())
    # UUIDv7 ids sort by creation time, so this is a true "newest first"
    # without needing to touch created_at.
    return stmt.order_by(Product.id.desc())


def search_products(
    db: Session,
    *,
    query: str | None = None,
    category: Category | None = None,
    wood_species: list[str] | None = None,
    tags: list[str] | None = None,
    min_price_paisa: int | None = None,
    max_price_paisa: int | None = None,
    min_rating: int | None = None,
    in_stock_only: bool = False,
    on_sale_only: bool = False,
    featured_only: bool = False,
    new_arrivals_only: bool = False,
    bestsellers_only: bool = False,
    sort: SortKey = "newest",
    page: int = 1,
    per_page: int = 24,
) -> dict[str, Any]:
    """Filtered, sorted, faceted product search."""
    conditions = [
        Product.status == ProductStatus.ACTIVE,
        Product.deleted_at.is_(None),
    ]

    if query:
        conditions.append(
            Product.search_vector.op("@@")(
                func.websearch_to_tsquery("english", query)
            )
        )
    if category is not None:
        conditions.append(Product.category_id.in_(descendant_category_ids(db, category)))
    if wood_species:
        conditions.append(Product.wood_species.in_(wood_species))
    if min_price_paisa is not None:
        conditions.append(Product.base_price_paisa >= min_price_paisa)
    if max_price_paisa is not None:
        conditions.append(Product.base_price_paisa <= max_price_paisa)
    if min_rating is not None:
        conditions.append(Product.rating_average >= min_rating)
    if on_sale_only:
        conditions.append(Product.compare_at_price_paisa.is_not(None))
    if featured_only:
        conditions.append(Product.is_featured.is_(True))
    if new_arrivals_only:
        conditions.append(Product.is_new_arrival.is_(True))
    if bestsellers_only:
        conditions.append(Product.is_bestseller.is_(True))

    if tags:
        conditions.append(
            Product.id.in_(
                select(ProductTag.product_id)
                .join(Tag, Tag.id == ProductTag.tag_id)
                .where(Tag.slug.in_(tags))
            )
        )

    if in_stock_only:
        conditions.append(
            Product.id.in_(
                select(ProductVariant.product_id)
                .join(StockLevel, StockLevel.variant_id == ProductVariant.id)
                .where(StockLevel.available > 0, ProductVariant.is_active.is_(True))
            )
        )

    where = and_(*conditions)

    total = db.scalar(select(func.count()).select_from(Product).where(where)) or 0

    stmt = _apply_sort(_with_cards(select(Product).where(where)), sort, query)
    items = db.scalars(stmt.offset((page - 1) * per_page).limit(per_page)).all()

    result: dict[str, Any] = {
        "items": list(items),
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
        "facets": _facets(db, where),
        "did_you_mean": None,
    }

    if total == 0 and query:
        result["did_you_mean"] = suggest_correction(db, query)

    return result


def _facets(db: Session, where) -> dict[str, Any]:
    """Filter counts over the current result set.

    Computed against the same WHERE the results used, so the numbers always
    agree with what is on screen.
    """
    species_rows = db.execute(
        select(Product.wood_species, func.count(Product.id))
        .where(where, Product.wood_species.is_not(None))
        .group_by(Product.wood_species)
        .order_by(func.count(Product.id).desc())
    ).all()

    category_rows = db.execute(
        select(Category.slug, Category.name, func.count(Product.id))
        .join(Product, Product.category_id == Category.id)
        .where(where)
        .group_by(Category.slug, Category.name)
        .order_by(func.count(Product.id).desc())
    ).all()

    tag_rows = db.execute(
        select(Tag.slug, Tag.name, func.count(ProductTag.product_id))
        .join(ProductTag, ProductTag.tag_id == Tag.id)
        .join(Product, Product.id == ProductTag.product_id)
        .where(where)
        .group_by(Tag.slug, Tag.name)
        .order_by(func.count(ProductTag.product_id).desc())
    ).all()

    price_row = db.execute(
        select(
            func.min(Product.base_price_paisa), func.max(Product.base_price_paisa)
        ).where(where)
    ).one()

    return {
        "wood_species": [
            {
                "value": s.value if hasattr(s, "value") else str(s),
                "label": WoodSpecies(s).label if s else "",
                "count": n,
            }
            for s, n in species_rows
        ],
        "categories": [
            {"value": slug, "label": name, "count": n}
            for slug, name, n in category_rows
        ],
        "tags": [
            {"value": slug, "label": name, "count": n} for slug, name, n in tag_rows
        ],
        "price_min_paisa": price_row[0] or 0,
        "price_max_paisa": price_row[1] or 0,
    }


def suggest_correction(db: Session, query: str) -> str | None:
    """Closest product name by trigram similarity, for "did you mean"."""
    row = db.execute(
        select(
            Product.name,
            func.word_similarity(query, Product.name).label("score"),
        )
        .where(
            Product.status == ProductStatus.ACTIVE,
            Product.deleted_at.is_(None),
            func.word_similarity(query, Product.name) > DID_YOU_MEAN_THRESHOLD,
        )
        .order_by(text("score DESC"))
        .limit(1)
    ).first()
    return row[0] if row else None


def autocomplete(db: Session, query: str, limit: int = 8) -> dict[str, list]:
    """Type-ahead across products and categories.

    Prefix matches rank above fuzzy ones, so typing "she" puts Sheesham first
    rather than something that merely shares letters.
    """
    if len(query.strip()) < 2:
        return {"products": [], "categories": []}

    # Contains, not starts-with: nobody types the first word of
    # "Lahore Six-Seat Dining Table" when they are looking for a dining table.
    contains = f"%{query.lower()}%"
    starts = f"{query.lower()}%"

    products = db.scalars(
        _with_cards(live_products())
        .where(
            or_(
                func.lower(Product.name).like(contains),
                func.word_similarity(query, Product.name) > AUTOCOMPLETE_THRESHOLD,
            )
        )
        .order_by(
            # A name that starts with the query ranks above one that merely
            # contains it, which ranks above a fuzzy match.
            func.lower(Product.name).like(starts).desc(),
            func.lower(Product.name).like(contains).desc(),
            func.word_similarity(query, Product.name).desc(),
        )
        .limit(limit)
    ).all()

    categories = db.scalars(
        select(Category)
        .where(Category.is_active.is_(True), func.lower(Category.name).like(f"%{query.lower()}%"))
        .limit(4)
    ).all()

    return {"products": list(products), "categories": list(categories)}


def get_product_by_slug(db: Session, slug: str) -> Product | None:
    return db.scalar(
        _with_cards(live_products())
        .where(Product.slug == slug)
        .options(
            selectinload(Product.option_types),
            selectinload(Product.personalization_options),
            selectinload(Product.assets),
        )
    )


def stock_for_variants(
    db: Session, variant_ids: list[uuid.UUID]
) -> dict[uuid.UUID, StockLevel]:
    if not variant_ids:
        return {}
    rows = db.scalars(
        select(StockLevel).where(StockLevel.variant_id.in_(variant_ids))
    ).all()
    return {row.variant_id: row for row in rows}


def related_products(db: Session, product: Product, limit: int = 8) -> list[Product]:
    """Same category first, then the same wood elsewhere.

    Two cheap queries beat one clever one here, and the ordering is easy to
    reason about when a merchandiser asks why something appeared.
    """
    same_category = db.scalars(
        _with_cards(live_products())
        .where(
            Product.category_id == product.category_id,
            Product.id != product.id,
        )
        .order_by(Product.rating_average.desc(), Product.sales_count.desc())
        .limit(limit)
    ).all()

    results = list(same_category)
    if len(results) >= limit or product.wood_species is None:
        return results[:limit]

    seen = {p.id for p in results} | {product.id}
    same_wood = db.scalars(
        _with_cards(live_products())
        .where(
            Product.wood_species == product.wood_species,
            Product.id.not_in(seen),
        )
        .order_by(Product.sales_count.desc())
        .limit(limit - len(results))
    ).all()
    return results + list(same_wood)


def frequently_bought_together(
    db: Session, product: Product, limit: int = 3
) -> list[Product]:
    """Products that really have appeared in the same orders.

    Falls back to nothing rather than guessing: a fabricated bundle suggestion
    is worse than none.
    """
    from app.models.order import OrderItem

    orders_with_product = (
        select(OrderItem.order_id).where(OrderItem.product_id == product.id).subquery()
    )

    rows = db.execute(
        select(OrderItem.product_id, func.count().label("n"))
        .where(
            OrderItem.order_id.in_(select(orders_with_product.c.order_id)),
            OrderItem.product_id != product.id,
            OrderItem.product_id.is_not(None),
        )
        .group_by(OrderItem.product_id)
        .order_by(text("n DESC"))
        .limit(limit)
    ).all()

    ids = [r[0] for r in rows]
    if not ids:
        return []

    products = db.scalars(_with_cards(live_products()).where(Product.id.in_(ids))).all()
    order = {pid: i for i, pid in enumerate(ids)}
    return sorted(products, key=lambda p: order.get(p.id, 99))
