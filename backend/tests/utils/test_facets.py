"""Unit tests for `normalize_facet`.

Regression tests for filtered search returning zero results. Ingest slugified
category and merely trimmed brand; the query path passed the raw user string
into Qdrant's exact, case-sensitive `MatchValue`. Confirmed by scrolling Qdrant
directly: `category="men-shoes"` matched 5 points, `category="Men shoes"`
matched 0; `brand="Nike"` matched 1, `brand="nike"` matched 0.
"""

import pytest

from app.utils.facets import normalize_facet


class TestCanonicalForm:
    @pytest.mark.parametrize(
        "value",
        [
            "Men shoes",  # what the user typed
            "men-shoes",  # what was stored
            " men-shoes ",
            "Men  Shoes",
            "MEN SHOES",
            "men_shoes",
            "--Men--Shoes--",
        ],
    )
    def test_every_spelling_of_the_same_facet_agrees(self, value: str) -> None:
        assert normalize_facet(value) == "men-shoes"

    @pytest.mark.parametrize("value", ["Nike", "nike", "NIKE", " Nike "])
    def test_brand_case_variants_agree(self, value: str) -> None:
        assert normalize_facet(value) == "nike"

    def test_digits_survive(self) -> None:
        """A model number is part of the identity, not a separator."""
        assert normalize_facet("Nike 90s") == "nike-90s"

    def test_distinct_facets_stay_distinct(self) -> None:
        """Normalizing must not collapse genuinely different values."""
        assert normalize_facet("Nike") != normalize_facet("Adidas")
        assert normalize_facet("men-shoes") != normalize_facet("women-shoes")


class TestNoFilterCases:
    """Blank input means "no filter", never a filter on the empty string."""

    @pytest.mark.parametrize("value", [None, "", "   ", "---", "!!!"])
    def test_blank_input_normalizes_to_none(self, value: str | None) -> None:
        assert normalize_facet(value) is None


class TestRoundTrip:
    """The value written at ingest and the value used at query must agree."""

    @pytest.mark.parametrize(
        ("typed_at_ingest", "typed_at_query"),
        [
            ("Men shoes", "men-shoes"),
            ("Men shoes", "MEN SHOES"),
            ("men-shoes", "Men  Shoes"),
            ("Nike", "nike"),
            ("nike", "NIKE"),
        ],
    )
    def test_both_paths_produce_the_identical_string(
        self, typed_at_ingest: str, typed_at_query: str
    ) -> None:
        assert normalize_facet(typed_at_ingest) == normalize_facet(typed_at_query)
