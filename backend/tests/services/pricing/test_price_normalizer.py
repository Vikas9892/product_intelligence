"""Unit tests for `PriceNormalizer`."""

from uuid import uuid4

from app.models.search import HybridSearchResult, SearchModality
from app.services.pricing.price_normalizer import PriceNormalizer


def _result(*, price: object, score: float = 0.9, **metadata: object) -> HybridSearchResult:
    return HybridSearchResult(
        product_id=uuid4(),
        score=score,
        metadata={"price": price, **metadata},
        matched_modalities=[SearchModality.TEXT],
    )


class TestToComparables:
    def test_keeps_positively_priced_results(self) -> None:
        results = [_result(price=99.0, brand="Nike", name="Shoe", category="Shoes")]

        comparables = PriceNormalizer().to_comparables(results)

        assert len(comparables) == 1
        assert comparables[0].price == 99.0
        assert comparables[0].brand == "Nike"
        assert comparables[0].similarity == 0.9

    def test_drops_results_without_a_price(self) -> None:
        results = [_result(price=None), _result(price=50.0)]

        comparables = PriceNormalizer().to_comparables(results)

        assert len(comparables) == 1
        assert comparables[0].price == 50.0

    def test_drops_non_positive_prices(self) -> None:
        results = [_result(price=0.0), _result(price=-5.0), _result(price=10.0)]

        comparables = PriceNormalizer().to_comparables(results)

        assert [c.price for c in comparables] == [10.0]

    def test_drops_non_numeric_prices(self) -> None:
        results = [_result(price="not-a-number"), _result(price=True), _result(price=20.0)]

        comparables = PriceNormalizer().to_comparables(results)

        assert [c.price for c in comparables] == [20.0]

    def test_coerces_blank_metadata_strings_to_none(self) -> None:
        comparables = PriceNormalizer().to_comparables([_result(price=10.0, brand="   ")])

        assert comparables[0].brand is None
