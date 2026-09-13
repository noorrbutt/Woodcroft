"""Catalog: categories, products, variants, options, media and Q&A.

Category tree
-------------
Modelled as ``parent_id`` plus a materialised ``path`` slug string rather than
the ``ltree`` extension. At this catalogue's scale (tens of categories, not
millions) a recursive CTE is already instant, the path doubles as the canonical
URL segment, and it avoids ltree's awkward ORM type mapping. A
``text_pattern_ops`` index makes descendant prefix queries fast.

Pricing
-------
A variant's ``price_paisa`` is nullable and falls back to its product's
``base_price_paisa``. That keeps single-variant products simple while letting a
6-seat dining table cost more than a 4-seat one. Nothing here computes totals -
that is exclusively ``app.services.pricing``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel
from app.models.enums import (
    PersonalizationInputType,
    ProductStatus,
    StockPolicy,
    WoodSpecies,
)


def _enum(py_enum: type, name: str) -> SAEnum:
    return SAEnum(py_enum, name=name, values_callable=lambda e: [m.value for m in e])


class Category(BaseModel):
    __tablename__ = "category"

    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("category.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), nullable=False, unique=True)
    #: Full slug path, e.g. "dining/tables". Maintained by the category service.
    path: Mapped[str] = mapped_column(String(600), nullable=False, unique=True)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    description: Mapped[str | None] = mapped_column(Text)
    image_path: Mapped[str | None] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    # SEO
    meta_title: Mapped[str | None] = mapped_column(String(200))
    meta_description: Mapped[str | None] = mapped_column(String(400))

    #: Overrides the store default tax rate for everything in this category.
    tax_rate_bp: Mapped[int | None] = mapped_column(Integer)

    parent: Mapped[Category | None] = relationship(
        back_populates="children", remote_side="Category.id"
    )
    children: Mapped[list[Category]] = relationship(
        back_populates="parent", order_by="Category.sort_order"
    )
    products: Mapped[list[Product]] = relationship(back_populates="category")

    __table_args__ = (
        CheckConstraint("depth >= 0 AND depth < 5", name="depth_within_range"),
        CheckConstraint(
            "tax_rate_bp IS NULL OR (tax_rate_bp >= 0 AND tax_rate_bp <= 10000)",
            name="tax_rate_bp_is_valid",
        ),
        CheckConstraint("id <> parent_id", name="category_not_own_parent"),
        Index(
            "ix_category_path_prefix",
            "path",
            postgresql_ops={"path": "text_pattern_ops"},
        ),
    )


class Tag(BaseModel):
    """Marketing tags: handmade, eco-friendly, limited-edition, bestseller."""

    __tablename__ = "tag"

    name: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(70), nullable=False, unique=True)
    #: Brass/forest/walnut accent used by the storefront badge.
    accent: Mapped[str | None] = mapped_column(String(20))


class ProductTag(BaseModel):
    __tablename__ = "product_tag"

    product_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product.id", ondelete="CASCADE"), nullable=False
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tag.id", ondelete="CASCADE"), nullable=False
    )

    tag: Mapped[Tag] = relationship(lazy="joined")

    __table_args__ = (UniqueConstraint("product_id", "tag_id", name="uq_product_tag"),)


class Product(BaseModel):
    __tablename__ = "product"

    category_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("category.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), nullable=False, unique=True)
    subtitle: Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    care_instructions: Mapped[str | None] = mapped_column(Text)
    #: Free-form craftsmanship copy shown in the PDP "story" block.
    story: Mapped[str | None] = mapped_column(Text)

    # ── Pricing (paisa) ──────────────────────────────────────────────────────
    base_price_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: Original price for strike-through display. Null when not on sale.
    compare_at_price_paisa: Mapped[int | None] = mapped_column(BigInteger)
    #: Internal cost, for the inventory-valuation report. Never exposed publicly.
    cost_price_paisa: Mapped[int | None] = mapped_column(BigInteger)
    tax_rate_bp: Mapped[int | None] = mapped_column(Integer)

    # ── Physical attributes ──────────────────────────────────────────────────
    wood_species: Mapped[WoodSpecies | None] = mapped_column(_enum(WoodSpecies, "wood_species"))
    #: Dimensions in millimetres so everything stays integral.
    length_mm: Mapped[int | None] = mapped_column(Integer)
    width_mm: Mapped[int | None] = mapped_column(Integer)
    height_mm: Mapped[int | None] = mapped_column(Integer)
    weight_g: Mapped[int | None] = mapped_column(Integer)
    #: Anything that does not deserve a column: finish notes, assembly time, etc.
    specifications: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    # ── Publishing ───────────────────────────────────────────────────────────
    status: Mapped[ProductStatus] = mapped_column(
        _enum(ProductStatus, "product_status"),
        nullable=False,
        server_default=ProductStatus.DRAFT.value,
        index=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Scheduled publish/unpublish, actioned by the background worker.
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unpublish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    stock_policy: Mapped[StockPolicy] = mapped_column(
        _enum(StockPolicy, "stock_policy"),
        nullable=False,
        server_default=StockPolicy.DENY.value,
    )

    # ── Merchandising flags ──────────────────────────────────────────────────
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_new_arrival: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_bestseller: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    # ── Denormalised review aggregates ───────────────────────────────────────
    # Maintained by the review service. Recomputing AVG() on every product card
    # render would dominate listing-page cost.
    rating_average: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, server_default=text("0")
    )
    rating_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    #: Units sold, for the best-seller sort. Incremented on order confirmation.
    sales_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    # ── SEO ──────────────────────────────────────────────────────────────────
    meta_title: Mapped[str | None] = mapped_column(String(200))
    meta_description: Mapped[str | None] = mapped_column(String(400))

    # ── Full-text search ─────────────────────────────────────────────────────
    # A generated column so it can never drift from the source text. Weighted so
    # a name match outranks a description match.
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(name, '')), 'A') || "
            "setweight(to_tsvector('english', coalesce(subtitle, '')), 'B') || "
            "setweight(to_tsvector('english', coalesce(description, '')), 'C')",
            persisted=True,
        ),
    )

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    category: Mapped[Category] = relationship(back_populates="products")
    variants: Mapped[list[ProductVariant]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin"
    )
    images: Mapped[list[ProductImage]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ProductImage.sort_order",
    )
    option_types: Mapped[list[ProductOptionType]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin"
    )
    personalization_options: Mapped[list[PersonalizationOption]] = relationship(
        back_populates="product", cascade="all, delete-orphan", lazy="selectin"
    )
    assets: Mapped[list[ProductAsset]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    tags: Mapped[list[ProductTag]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint("base_price_paisa > 0", name="base_price_positive"),
        CheckConstraint(
            "compare_at_price_paisa IS NULL OR compare_at_price_paisa > base_price_paisa",
            name="compare_at_price_above_base",
        ),
        CheckConstraint(
            "tax_rate_bp IS NULL OR (tax_rate_bp >= 0 AND tax_rate_bp <= 10000)",
            name="tax_rate_bp_is_valid",
        ),
        CheckConstraint(
            "rating_average >= 0 AND rating_average <= 5", name="rating_average_in_range"
        ),
        Index("ix_product_search_vector", "search_vector", postgresql_using="gin"),
        # Trigram index powers autocomplete and did-you-mean suggestions.
        Index(
            "ix_product_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        # Listing pages only ever query live products; a partial index keeps
        # drafts and deleted rows out of the hot index entirely.
        Index(
            "ix_product_live",
            "category_id",
            "created_at",
            postgresql_where=text("status = 'active' AND deleted_at IS NULL"),
        ),
        Index("ix_product_scheduled", "publish_at", postgresql_where=text("publish_at IS NOT NULL")),
    )

    @property
    def is_on_sale(self) -> bool:
        return self.compare_at_price_paisa is not None


class ProductOptionType(BaseModel):
    """A variant axis for one product: Size, Finish, Wood."""

    __tablename__ = "product_option_type"

    product_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    product: Mapped[Product] = relationship(back_populates="option_types")
    values: Mapped[list[ProductOptionValue]] = relationship(
        back_populates="option_type",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ProductOptionValue.sort_order",
    )

    __table_args__ = (
        UniqueConstraint("product_id", "name", name="uq_product_option_type"),
    )


class ProductOptionValue(BaseModel):
    __tablename__ = "product_option_value"

    option_type_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("product_option_type.id", ondelete="CASCADE"),
        nullable=False,
    )
    value: Mapped[str] = mapped_column(String(80), nullable=False)
    #: Hex colour or swatch image, for finish/wood pickers.
    swatch: Mapped[str | None] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    option_type: Mapped[ProductOptionType] = relationship(back_populates="values")

    __table_args__ = (
        UniqueConstraint("option_type_id", "value", name="uq_product_option_value"),
    )


class ProductVariant(BaseModel):
    """A sellable SKU. Stock lives on ``stock_level``, keyed by variant."""

    __tablename__ = "product_variant"

    product_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    sku: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String(200))

    #: Null means "inherit the product's base price".
    price_paisa: Mapped[int | None] = mapped_column(BigInteger)
    compare_at_price_paisa: Mapped[int | None] = mapped_column(BigInteger)
    cost_price_paisa: Mapped[int | None] = mapped_column(BigInteger)

    weight_g: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    #: Sellable before stock exists, with an expected availability date.
    is_preorder: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    preorder_available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    product: Mapped[Product] = relationship(back_populates="variants")
    option_values: Mapped[list[VariantOptionValue]] = relationship(
        back_populates="variant", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        CheckConstraint(
            "price_paisa IS NULL OR price_paisa > 0", name="price_positive"
        ),
        CheckConstraint(
            "NOT is_preorder OR preorder_available_at IS NOT NULL",
            name="preorder_needs_date",
        ),
    )

    def effective_price_paisa(self, product: Product | None = None) -> int:
        """Resolve this variant's price, falling back to the product's."""
        if self.price_paisa is not None:
            return self.price_paisa
        source = product or self.product
        return source.base_price_paisa


class VariantOptionValue(BaseModel):
    """Join row placing a variant at one coordinate of the option matrix."""

    __tablename__ = "variant_option_value"

    variant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product_variant.id", ondelete="CASCADE"),
        nullable=False,
    )
    option_value_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product_option_value.id", ondelete="CASCADE"),
        nullable=False,
    )

    variant: Mapped[ProductVariant] = relationship(back_populates="option_values")
    option_value: Mapped[ProductOptionValue] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("variant_id", "option_value_id", name="uq_variant_option_value"),
    )


class ProductImage(BaseModel):
    """An image and its generated size variants.

    ``base_path`` plus ``sizes`` describes a family of files on disk
    (``<base_path>_<size>.webp``) rather than one row per size.
    ``blur_data_url`` is a tiny base64 LQIP inlined by the frontend so cards
    never flash empty. ``checksum`` lets a re-seed skip regenerating an
    identical plate.
    """

    __tablename__ = "product_image"

    product_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    #: Set when the image belongs to one variant rather than the whole product.
    variant_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product_variant.id", ondelete="CASCADE")
    )

    base_path: Mapped[str] = mapped_column(String(500), nullable=False)
    sizes: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, server_default=text("'{}'::integer[]")
    )
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    aspect: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)

    alt_text: Mapped[str] = mapped_column(String(300), nullable=False, server_default="")
    blur_data_url: Mapped[str | None] = mapped_column(Text)

    #: 'generated' (procedural plate) or 'curated' (fetched photograph).
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="generated")
    attribution: Mapped[dict | None] = mapped_column(JSONB)
    checksum: Mapped[str | None] = mapped_column(String(64))

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    product: Mapped[Product] = relationship(back_populates="images")

    __table_args__ = (
        CheckConstraint("width > 0 AND height > 0", name="dimensions_positive"),
        CheckConstraint("source IN ('generated', 'curated')", name="source_is_known"),
        # Exactly one primary image per product.
        Index(
            "uq_product_image_primary",
            "product_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )


class PersonalizationOption(BaseModel):
    """A customisation a buyer can configure on a product.

    Engraving, monogram and custom dimensions. The chosen values are captured
    immutably onto ``cart_item.personalization`` and then
    ``order_item.personalization`` so the workshop instruction never changes
    after purchase, even if the option definition is later edited.
    """

    __tablename__ = "personalization_option"

    product_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    help_text: Mapped[str | None] = mapped_column(String(400))

    input_type: Mapped[PersonalizationInputType] = mapped_column(
        _enum(PersonalizationInputType, "personalization_input_type"), nullable=False
    )
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    #: Flat surcharge added once per unit when this option is used.
    surcharge_paisa: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    #: Additional surcharge per character, for engraving.
    surcharge_per_char_paisa: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )

    max_length: Mapped[int | None] = mapped_column(Integer)
    #: Allowed values for a select, or min/max bounds for dimensions.
    constraints: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    product: Mapped[Product] = relationship(back_populates="personalization_options")

    __table_args__ = (
        UniqueConstraint("product_id", "key", name="uq_personalization_option_key"),
        CheckConstraint("surcharge_paisa >= 0", name="surcharge_non_negative"),
        CheckConstraint(
            "surcharge_per_char_paisa >= 0", name="surcharge_per_char_non_negative"
        ),
    )


class ProductAsset(BaseModel):
    """Downloadable PDF: spec sheet, assembly instructions, care guide."""

    __tablename__ = "product_asset"

    product_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    product: Mapped[Product] = relationship(back_populates="assets")


class ProductQuestion(BaseModel):
    __tablename__ = "product_question"

    product_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL")
    )
    asker_name: Mapped[str | None] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    helpful_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    answers: Mapped[list[ProductAnswer]] = relationship(
        back_populates="question", cascade="all, delete-orphan", lazy="selectin"
    )


class ProductAnswer(BaseModel):
    __tablename__ = "product_answer"

    question_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product_question.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    #: Distinguishes a Woodcroft reply from another customer's answer.
    is_official: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    helpful_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    question: Mapped[ProductQuestion] = relationship(back_populates="answers")


class RecentlyViewed(BaseModel):
    __tablename__ = "recently_viewed"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    guest_session_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("guest_session.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product.id", ondelete="CASCADE"), nullable=False
    )
    viewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        CheckConstraint(
            "(user_id IS NOT NULL) <> (guest_session_id IS NOT NULL)",
            name="exactly_one_owner",
        ),
        UniqueConstraint("user_id", "product_id", name="uq_recently_viewed_user"),
        UniqueConstraint(
            "guest_session_id", "product_id", name="uq_recently_viewed_guest"
        ),
    )


class BackInStockSubscription(BaseModel):
    __tablename__ = "back_in_stock_subscription"

    variant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product_variant.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE")
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "ix_back_in_stock_pending",
            "variant_id",
            postgresql_where=text("notified_at IS NULL"),
        ),
        UniqueConstraint("variant_id", "email", name="uq_back_in_stock_subscriber"),
    )


class PriceWatch(BaseModel):
    """Notify when a wishlisted product's price drops below the watched value."""

    __tablename__ = "price_watch"

    product_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("product.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False
    )
    #: Price when the watch was created; a drop below this triggers the alert.
    watched_price_paisa: Mapped[int] = mapped_column(BigInteger, nullable=False)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("product_id", "user_id", name="uq_price_watch"),)
