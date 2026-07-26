"""Unit tests for the internal search domain models."""

from uuid import uuid4

from app.models.search import NearestNeighbor


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
