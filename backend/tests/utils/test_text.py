"""Unit tests for `app.utils.text`."""

from app.utils.text import build_text_representation


class TestBuildTextRepresentation:
    def test_joins_all_parts(self) -> None:
        text = build_text_representation("Widget", "Nike", "Men Tshirts", "A fine shirt")

        assert text == "Widget. Nike. Men Tshirts. A fine shirt"

    def test_omits_missing_parts(self) -> None:
        text = build_text_representation("Widget", None, None, None)

        assert text == "Widget"

    def test_omits_blank_parts(self) -> None:
        text = build_text_representation("Widget", "   ", "Men Tshirts", None)

        assert text == "Widget. Men Tshirts"

    def test_does_not_slugify_category(self) -> None:
        # Unlike ProductService's `_normalize_category`, which slugifies
        # for storage/filtering — the text representation is meant for a
        # semantic embedding model, so it should stay natural language.
        text = build_text_representation("Widget", None, "Men Tshirts", None)

        assert "Men Tshirts" in text
        assert "men-tshirts" not in text
