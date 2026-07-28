"""Unit tests for `app.utils.text`."""

from app.utils.text import build_text_representation, build_text_representation_from_metadata


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


class TestBuildTextRepresentationFromMetadata:
    def test_joins_all_present_fields(self) -> None:
        text = build_text_representation_from_metadata(
            {"name": "Widget", "brand": "Nike", "category": "Men Tshirts", "description": "Nice"}
        )

        assert text == "Widget. Nike. Men Tshirts. Nice"

    def test_missing_name_does_not_raise(self) -> None:
        # A blank/missing "name" degrades to an empty leading part rather
        # than being omitted entirely (`build_text_representation`'s own
        # first positional argument is always included) — a real product's
        # stored metadata always has a non-blank name, so this only
        # matters for otherwise-malformed metadata, where "doesn't crash"
        # is the actual requirement, not a particular output format.
        text = build_text_representation_from_metadata({"brand": "Nike"})

        assert "Nike" in text

    def test_non_string_values_are_tolerated_not_raised(self) -> None:
        text = build_text_representation_from_metadata(
            {"name": 123, "brand": ["Nike"], "category": None, "description": 4.5}
        )

        assert text == ""

    def test_empty_metadata_yields_an_empty_string(self) -> None:
        assert build_text_representation_from_metadata({}) == ""
