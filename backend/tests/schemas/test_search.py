"""Unit tests for the search schemas."""

from uuid import uuid4

from app.schemas.search import ProductSearchResponse, ProductSearchResult


class TestProductSearchResult:
    def test_constructs_with_all_fields(self) -> None:
        product_id = uuid4()

        result = ProductSearchResult(
            product_id=product_id, score=0.94, metadata={"category": "shoes"}
        )

        assert result.product_id == product_id
        assert result.score == 0.94
        assert result.metadata == {"category": "shoes"}


class TestProductSearchResponse:
    def test_round_trips_through_model_dump_and_validate(self) -> None:
        response = ProductSearchResponse(
            results=[
                ProductSearchResult(product_id=uuid4(), score=0.9, metadata={"name": "Widget"})
            ]
        )

        dumped = response.model_dump(mode="json")
        restored = ProductSearchResponse.model_validate(dumped)

        assert restored == response

    def test_accepts_an_empty_results_list(self) -> None:
        response = ProductSearchResponse(results=[])

        assert response.results == []
