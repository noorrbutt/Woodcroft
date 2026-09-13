"""Catalog response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import Field

from app.core.config import settings
from app.models.enums import PersonalizationInputType, WoodSpecies
from app.schemas.common import Money, Schema


def media_url(path: str | None, size: int | None = None) -> str | None:
    """Build a servable URL for a stored media path."""
    if not path:
        return None
    if path.startswith("http"):
        return path
    suffix = f"_{size}.webp" if size else ".webp"
    return f"{settings.MEDIA_URL}/{path}{suffix}"


class ImageOut(Schema):
    id: uuid.UUID
    url: str
    thumb_url: str
    srcset: str
    alt_text: str
    width: int
    height: int
    aspect: Decimal
    blur_data_url: str | None
    is_primary: bool

    @classmethod
    def from_model(cls, image) -> ImageOut:
        sizes = image.sizes or [400, 800, 1600]
        return cls(
            id=image.id,
            url=media_url(image.base_path, max(sizes)) or "",
            thumb_url=media_url(image.base_path, min(sizes)) or "",
            # A real srcset so the browser downloads the size it needs rather
            # than a 2000px plate onto a product card.
            srcset=", ".join(f"{media_url(image.base_path, s)} {s}w" for s in sizes),
            alt_text=image.alt_text or "",
            width=image.width,
            height=image.height,
            aspect=image.aspect,
            blur_data_url=image.blur_data_url,
            is_primary=image.is_primary,
        )


class CategoryOut(Schema):
    id: uuid.UUID
    name: str
    slug: str
    path: str
    depth: int
    description: str | None
    image_url: str | None
    product_count: int = 0
    children: list[CategoryOut] = Field(default_factory=list)


class OptionValueOut(Schema):
    id: uuid.UUID
    value: str
    swatch: str | None
    #: False when no in-stock variant carries this value.
    available: bool = True


class OptionTypeOut(Schema):
    id: uuid.UUID
    name: str
    values: list[OptionValueOut]


class PersonalizationOptionOut(Schema):
    id: uuid.UUID
    key: str
    label: str
    help_text: str | None
    input_type: PersonalizationInputType
    is_required: bool
    surcharge: Money
    surcharge_per_char: Money
    max_length: int | None
    constraints: dict


class StockOut(Schema):
    """What the PDP needs to say about availability."""

    available: int
    is_in_stock: bool
    is_low: bool
    #: Only set when low, to drive the "only 2 left" line.
    remaining_label: str | None = None
    is_preorder: bool = False
    preorder_available_at: datetime | None = None


class VariantOut(Schema):
    id: uuid.UUID
    sku: str
    name: str | None
    price: Money
    compare_at_price: Money | None
    option_value_ids: list[uuid.UUID]
    stock: StockOut
    is_active: bool


class TagOut(Schema):
    name: str
    slug: str
    accent: str | None


class ProductCardOut(Schema):
    """The shape a listing grid needs. Deliberately smaller than the PDP."""

    id: uuid.UUID
    name: str
    slug: str
    subtitle: str | None
    category_name: str | None
    price: Money
    compare_at_price: Money | None
    discount_percent: int | None
    primary_image: ImageOut | None
    rating_average: Decimal
    rating_count: int
    wood_species: WoodSpecies | None
    wood_species_label: str | None
    tags: list[TagOut]
    is_in_stock: bool
    is_new_arrival: bool
    is_bestseller: bool


class ProductDetailOut(ProductCardOut):
    description: str
    story: str | None
    care_instructions: str | None
    specifications: dict
    dimensions: dict | None
    weight_g: int | None
    images: list[ImageOut]
    option_types: list[OptionTypeOut]
    variants: list[VariantOut]
    personalization_options: list[PersonalizationOptionOut]
    assets: list[AssetOut]
    meta_title: str | None
    meta_description: str | None
    category_path: str


class AssetOut(Schema):
    id: uuid.UUID
    title: str
    kind: str
    url: str
    file_size_bytes: int | None


class FacetValue(Schema):
    value: str
    label: str
    count: int


class Facets(Schema):
    """Filter counts, computed against the current result set."""

    categories: list[FacetValue] = Field(default_factory=list)
    wood_species: list[FacetValue] = Field(default_factory=list)
    tags: list[FacetValue] = Field(default_factory=list)
    price_min_paisa: int = 0
    price_max_paisa: int = 0


class ProductListOut(Schema):
    items: list[ProductCardOut]
    total: int
    page: int
    per_page: int
    pages: int
    facets: Facets
    #: Populated on a zero-result search when we can offer a closer term.
    did_you_mean: str | None = None


class SearchSuggestion(Schema):
    kind: str  # product | category | term
    label: str
    slug: str | None = None
    image_url: str | None = None


class QuestionOut(Schema):
    id: uuid.UUID
    body: str
    asker_name: str | None
    created_at: datetime
    answers: list[AnswerOut]
    helpful_count: int


class AnswerOut(Schema):
    id: uuid.UUID
    body: str
    is_official: bool
    created_at: datetime
    helpful_count: int


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
    images: list[str]
    reply: ReplyOut | None = None


class ReplyOut(Schema):
    display_name: str
    body: str
    created_at: datetime


class RatingBreakdown(Schema):
    average: Decimal
    total: int
    #: Count per star, keyed "1".."5".
    counts: dict[str, int]


CategoryOut.model_rebuild()
ProductDetailOut.model_rebuild()
QuestionOut.model_rebuild()
ReviewOut.model_rebuild()
