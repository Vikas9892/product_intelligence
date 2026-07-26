"""Unit tests for the internal search domain models."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.search import NearestNeighbor, SearchQuery, SearchResult


class TestNearestNeighbor:
    def test_constructs_with_all_fields(self) -> None:
        product_id = uuid4()

        neighbor = NearestNeighbor(
            product_id=product_id, score=0.94, metadata={"category": "shoes"}
        )

        assert neighbor.product_id == product_id
        assert neighbor.score == 0.94
        assert neighbor.metadata == {"category": "shoes"}

    def test_metadata_defaults_to_empty_dict(self) -> None:
        neighbor = NearestNeighbor(product_id=uuid4(), score=0.5)

        assert neighbor.metadata == {}

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        neighbor = NearestNeighbor(product_id=uuid4(), score=0.75, metadata={"name": "Widget"})

        dumped = neighbor.model_dump(mode="json")
        restored = NearestNeighbor.model_validate(dumped)

        assert restored == neighbor


class TestSearchQuery:
    def test_constructs_with_all_fields(self) -> None:
        query = SearchQuery(
            vector=[0.1, 0.2],
            model_name="openai/clip-vit-base-patch32",
            top_k=5,
            filters={"category": "shoes"},
        )

        assert query.vector == [0.1, 0.2]
        assert query.model_name == "openai/clip-vit-base-patch32"
        assert query.top_k == 5
        assert query.filters == {"category": "shoes"}

    def test_filters_defaults_to_none(self) -> None:
        query = SearchQuery(vector=[0.1], model_name="fake-model", top_k=5)

        assert query.filters is None

    def test_rejects_a_non_positive_top_k(self) -> None:
        with pytest.raises(ValidationError):
            SearchQuery(vector=[0.1], model_name="fake-model", top_k=0)


class TestSearchResult:
    def test_constructs_with_neighbors(self) -> None:
        neighbor = NearestNeighbor(product_id=uuid4(), score=0.9)

        result = SearchResult(query_model_name="fake-model", neighbors=[neighbor])

        assert result.query_model_name == "fake-model"
        assert result.neighbors == [neighbor]

    def test_accepts_an_empty_neighbor_list(self) -> None:
        result = SearchResult(query_model_name="fake-model", neighbors=[])

        assert result.neighbors == []
