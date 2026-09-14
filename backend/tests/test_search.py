"""Search behaviour.

A shop search that only matches whole words is broken in a way customers read
as "you do not sell this". Typing "sheesha" has to find Sheesham, the same way
it would on any other shop.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.services.catalog import search_products


@pytest.fixture
def catalogue(db):
    """A handful of products with names that overlap in useful ways."""
    category = db.execute(
        text(
            "INSERT INTO category (name, slug, path, depth) "
            "VALUES ('Dining', 'dining', 'dining', 0) RETURNING id"
        )
    ).scalar_one()

    rows = [
        ("Lahore Six-Seat Dining Table", "lahore-dining-table",
         "Seats six in solid sheesham", "Hand joined from Sheesham boards.", "sheesham"),
        ("Murree Round Dining Table", "murree-round-table",
         "Four-seat pedestal round", "A round table on a turned pedestal.", "deodar"),
        ("Gulberg Sideboard in Sheesham", "gulberg-sideboard-sheesham",
         "Four doors, brass pulls", "Long low sideboard with brass.", "sheesham"),
        ("Grain End-Grain Chopping Board", "grain-chopping-board",
         "End grain, kind to knives", "An end grain board for the kitchen.", "acacia"),
        ("Clifton Media Console", "clifton-media-console",
         "Cable management", "Sized for a sixty five inch screen.", "walnut"),
    ]
    for name, slug, subtitle, description, wood in rows:
        db.execute(
            text(
                "INSERT INTO product (category_id, name, slug, subtitle, description, "
                "                     wood_species, base_price_paisa, status) "
                "VALUES (:c, :n, :s, :sub, :d, :w, 1000000, 'active')"
            ),
            {"c": category, "n": name, "s": slug, "sub": subtitle,
             "d": description, "w": wood},
        )
    db.flush()
    return category


def names(db, query: str, **kwargs) -> list[str]:
    result = search_products(db, query=query, per_page=50, **kwargs)
    return [p.name for p in result["items"]]


class TestPartialWords:
    """The bug this file exists for."""

    def test_partial_word_matches(self, db, catalogue) -> None:
        found = names(db, "sheesha")
        assert "Gulberg Sideboard in Sheesham" in found
        assert "Lahore Six-Seat Dining Table" in found

    @pytest.mark.parametrize("query", ["s", "sh", "shee", "sheesh", "sheesham"])
    def test_every_prefix_length_works(self, db, catalogue, query: str) -> None:
        assert "Gulberg Sideboard in Sheesham" in names(db, query)

    def test_middle_of_a_word_matches(self, db, catalogue) -> None:
        """Substring, not just prefix. "eesham" is inside "Sheesham"."""
        assert "Gulberg Sideboard in Sheesham" in names(db, "eesham")

    def test_full_word_still_matches(self, db, catalogue) -> None:
        assert len(names(db, "sheesham")) >= 2


class TestCase:
    @pytest.mark.parametrize("query", ["sheesha", "SHEESHA", "ShEeShA", "Sheesha"])
    def test_case_is_ignored(self, db, catalogue, query: str) -> None:
        assert "Gulberg Sideboard in Sheesham" in names(db, query)

    def test_all_casings_give_the_same_results(self, db, catalogue) -> None:
        assert sorted(names(db, "dining")) == sorted(names(db, "DINING"))


class TestPhrases:
    def test_partial_phrase_across_two_words(self, db, catalogue) -> None:
        """"dining tab" spans a word boundary, which full-text alone misses."""
        assert "Lahore Six-Seat Dining Table" in names(db, "dining tab")

    def test_word_order_does_not_matter(self, db, catalogue) -> None:
        assert set(names(db, "table dining")) == set(names(db, "dining table"))

    def test_matches_the_subtitle(self, db, catalogue) -> None:
        assert "Grain End-Grain Chopping Board" in names(db, "kind to knives")

    def test_matches_the_description(self, db, catalogue) -> None:
        assert "Clifton Media Console" in names(db, "sixty five inch")


class TestRelevance:
    def test_name_match_ranks_above_description_match(self, db, catalogue) -> None:
        ranked = names(db, "chopping", sort="relevance")
        assert ranked[0] == "Grain End-Grain Chopping Board"

    def test_starts_with_ranks_first(self, db, catalogue) -> None:
        ranked = names(db, "clifton", sort="relevance")
        assert ranked[0] == "Clifton Media Console"


class TestNoMatches:
    def test_nonsense_finds_nothing(self, db, catalogue) -> None:
        assert names(db, "xyzzyplugh") == []

    def test_punctuation_does_not_break_the_query(self, db, catalogue) -> None:
        """to_tsquery parses its input, so a stray & or : must not reach it."""
        for query in ["sheesha & ", "table | chair", "dining:*", "!!!", "a & b | c"]:
            search_products(db, query=query, per_page=10)

    def test_empty_query_returns_everything(self, db, catalogue) -> None:
        assert len(names(db, "")) == 5

    def test_whitespace_only_returns_everything(self, db, catalogue) -> None:
        assert len(names(db, "   ")) == 5


class TestFiltersStillApply:
    def test_search_combines_with_a_filter(self, db, catalogue) -> None:
        found = names(db, "table", wood_species=["sheesham"])
        assert found == ["Lahore Six-Seat Dining Table"]

    def test_facet_counts_match_the_result_set(self, db, catalogue) -> None:
        """Counts are computed from the same WHERE, so they cannot disagree."""
        result = search_products(db, query="sheesha", per_page=50)
        species = {f["value"]: f["count"] for f in result["facets"]["wood_species"]}
        assert species.get("sheesham") == 2
        assert result["total"] == 2
