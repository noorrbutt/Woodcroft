"""Catalog guarantees: search vector, pricing constraints, option matrix.

The full-text and trigram tests matter because search is built directly on
these Postgres features rather than an external engine - if the generated
column or the GIN indexes are wrong, search silently returns nothing.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

CATEGORY = text(
    "INSERT INTO category (name, slug, path, depth) "
    "VALUES (:n, :s, :p, :d) RETURNING id"
)
PRODUCT = text(
    "INSERT INTO product (category_id, name, slug, subtitle, description, "
    "                     base_price_paisa, compare_at_price_paisa, status) "
    "VALUES (:c, :n, :s, :sub, :d, :price, :compare, :status) RETURNING id"
)


@pytest.fixture
def category_id(raw):
    return raw.execute(
        CATEGORY, {"n": "Dining", "s": "dining", "p": "dining", "d": 0}
    ).scalar_one()


def _product(raw, category_id, **kw):
    params = {
        "c": category_id,
        "n": kw.get("name", "Sheesham Dining Table"),
        "s": kw.get("slug", "sheesham-dining-table"),
        "sub": kw.get("subtitle", "Seats six in solid rosewood"),
        "d": kw.get("description", "Hand-joined from a single board of Sheesham."),
        "price": kw.get("price", 24_999_00),
        "compare": kw.get("compare"),
        "status": kw.get("status", "active"),
    }
    return raw.execute(PRODUCT, params).scalar_one()


class TestCategoryTree:
    def test_path_is_unique(self, raw, category_id) -> None:
        with pytest.raises(IntegrityError):
            raw.execute(
                CATEGORY, {"n": "Dining Again", "s": "dining-2", "p": "dining", "d": 0}
            )

    def test_category_cannot_be_its_own_parent(self, raw, category_id) -> None:
        with pytest.raises(IntegrityError):
            raw.execute(
                text("UPDATE category SET parent_id = id WHERE id = :i"),
                {"i": category_id},
            )

    def test_prefix_query_finds_descendants(self, raw, category_id) -> None:
        raw.execute(
            CATEGORY, {"n": "Tables", "s": "tables", "p": "dining/tables", "d": 1}
        )
        raw.execute(
            CATEGORY, {"n": "Beds", "s": "beds", "p": "bedroom/beds", "d": 1}
        )
        found = raw.execute(
            text("SELECT count(*) FROM category WHERE path LIKE :prefix"),
            {"prefix": "dining%"},
        ).scalar_one()
        assert found == 2  # "dining" itself plus "dining/tables"


class TestProductPricing:
    def test_rejects_zero_price(self, raw, category_id) -> None:
        with pytest.raises(IntegrityError):
            _product(raw, category_id, price=0)

    def test_rejects_negative_price(self, raw, category_id) -> None:
        with pytest.raises(IntegrityError):
            _product(raw, category_id, price=-100)

    def test_compare_at_price_must_exceed_base(self, raw, category_id) -> None:
        """A strike-through price below the real price would be a lie."""
        with pytest.raises(IntegrityError):
            _product(raw, category_id, price=24_999_00, compare=19_999_00)

    def test_valid_sale_price_accepted(self, raw, category_id) -> None:
        _product(raw, category_id, price=19_999_00, compare=24_999_00)


class TestFullTextSearch:
    def test_search_vector_is_generated(self, raw, category_id) -> None:
        pid = _product(raw, category_id)
        vector = raw.execute(
            text("SELECT search_vector::text FROM product WHERE id = :i"), {"i": pid}
        ).scalar_one()
        assert "sheesham" in vector.lower()
        assert "dine" in vector.lower() or "dining" in vector.lower()

    def test_search_vector_updates_with_the_row(self, raw, category_id) -> None:
        """Being a generated column, it can never drift from the source text."""
        pid = _product(raw, category_id)
        raw.execute(
            text(
                "UPDATE product SET name = 'Walnut Console', subtitle = 'Two drawers', "
                "description = 'Turned legs in solid walnut.' WHERE id = :i"
            ),
            {"i": pid},
        )
        vector = raw.execute(
            text("SELECT search_vector::text FROM product WHERE id = :i"), {"i": pid}
        ).scalar_one()
        assert "'walnut':1A" in vector  # new name, at weight A
        assert "sheesham" not in vector.lower()  # old text fully gone

    def test_name_is_weighted_above_description(self, raw, category_id) -> None:
        pid = _product(raw, category_id)
        vector = raw.execute(
            text("SELECT search_vector::text FROM product WHERE id = :i"), {"i": pid}
        ).scalar_one()
        # "sheesham" appears in both the name (A) and the description (C).
        assert "'sheesham':1A" in vector

    def test_full_text_query_matches(self, raw, category_id) -> None:
        _product(raw, category_id)
        _product(raw, category_id, name="Teak Wardrobe", slug="teak-wardrobe",
                 subtitle="Four-door", description="Solid teak with brass fittings.")
        hits = raw.execute(
            text(
                "SELECT name FROM product "
                "WHERE search_vector @@ websearch_to_tsquery('english', :q)"
            ),
            {"q": "sheesham"},
        ).scalars().all()
        assert hits == ["Sheesham Dining Table"]

    def test_name_outranks_description(self, raw, category_id) -> None:
        """Weighting means a name hit beats a passing mention in body copy."""
        _product(raw, category_id, name="Teak Wardrobe", slug="teak-wardrobe",
                 subtitle="Four-door", description="Solid teak.")
        _product(raw, category_id, name="Oak Shelf", slug="oak-shelf",
                 subtitle="Wall mounted",
                 description="Pairs beautifully with our teak wardrobe.")
        ranked = raw.execute(
            text(
                "SELECT name FROM product "
                "WHERE search_vector @@ websearch_to_tsquery('english', :q) "
                "ORDER BY ts_rank(search_vector, websearch_to_tsquery('english', :q)) DESC"
            ),
            {"q": "teak wardrobe"},
        ).scalars().all()
        assert ranked[0] == "Teak Wardrobe"

    def test_trigram_similarity_powers_did_you_mean(self, raw, category_id) -> None:
        """A misspelling still finds the product, via pg_trgm."""
        _product(raw, category_id)
        hits = raw.execute(
            text(
                "SELECT name FROM product "
                "WHERE similarity(name, :q) > 0.2 "
                "ORDER BY similarity(name, :q) DESC"
            ),
            {"q": "sheshum dining"},
        ).scalars().all()
        assert "Sheesham Dining Table" in hits


class TestProductImage:
    def test_only_one_primary_image_per_product(self, raw, category_id) -> None:
        pid = _product(raw, category_id)
        stmt = text(
            "INSERT INTO product_image "
            "(product_id, base_path, width, height, aspect, is_primary) "
            "VALUES (:p, :path, 2000, 2500, 0.8, true)"
        )
        raw.execute(stmt, {"p": pid, "path": "products/a"})
        with pytest.raises(IntegrityError):
            raw.execute(stmt, {"p": pid, "path": "products/b"})

    def test_rejects_unknown_source(self, raw, category_id) -> None:
        pid = _product(raw, category_id)
        with pytest.raises(IntegrityError):
            raw.execute(
                text(
                    "INSERT INTO product_image "
                    "(product_id, base_path, width, height, aspect, source) "
                    "VALUES (:p, 'x', 100, 100, 1.0, 'stock-photo')"
                ),
                {"p": pid},
            )


class TestVariants:
    def test_sku_is_globally_unique(self, raw, category_id) -> None:
        pid = _product(raw, category_id)
        stmt = text(
            "INSERT INTO product_variant (product_id, sku) VALUES (:p, 'WC-SHE-001')"
        )
        raw.execute(stmt, {"p": pid})
        with pytest.raises(IntegrityError):
            raw.execute(stmt, {"p": pid})

    def test_preorder_requires_a_date(self, raw, category_id) -> None:
        pid = _product(raw, category_id)
        with pytest.raises(IntegrityError):
            raw.execute(
                text(
                    "INSERT INTO product_variant (product_id, sku, is_preorder) "
                    "VALUES (:p, 'WC-PRE-001', true)"
                ),
                {"p": pid},
            )

    def test_preorder_with_date_accepted(self, raw, category_id) -> None:
        pid = _product(raw, category_id)
        raw.execute(
            text(
                "INSERT INTO product_variant "
                "(product_id, sku, is_preorder, preorder_available_at) "
                "VALUES (:p, 'WC-PRE-002', true, now() + interval '30 days')"
            ),
            {"p": pid},
        )


class TestPersonalization:
    def test_option_key_unique_per_product(self, raw, category_id) -> None:
        pid = _product(raw, category_id)
        stmt = text(
            "INSERT INTO personalization_option "
            "(product_id, key, label, input_type) "
            "VALUES (:p, 'engraving', 'Engraving', 'text')"
        )
        raw.execute(stmt, {"p": pid})
        with pytest.raises(IntegrityError):
            raw.execute(stmt, {"p": pid})

    def test_surcharges_cannot_be_negative(self, raw, category_id) -> None:
        pid = _product(raw, category_id)
        with pytest.raises(IntegrityError):
            raw.execute(
                text(
                    "INSERT INTO personalization_option "
                    "(product_id, key, label, input_type, surcharge_paisa) "
                    "VALUES (:p, 'monogram', 'Monogram', 'monogram', -500)"
                ),
                {"p": pid},
            )


class TestRecentlyViewed:
    def test_requires_exactly_one_owner(self, raw, category_id) -> None:
        """A row must belong to a user or a guest session, never both/neither."""
        pid = _product(raw, category_id)
        with pytest.raises(IntegrityError):
            raw.execute(
                text(
                    "INSERT INTO recently_viewed (product_id) VALUES (:p)"
                ),
                {"p": pid},
            )
