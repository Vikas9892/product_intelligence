"""Unit tests for the internal `ImageEmbedding` domain model."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.embedding import ImageEmbedding


def _embedding(**overrides: object) -> ImageEmbedding:
    defaults: dict[str, object] = {
        "product_id": uuid4(),
        "model_name": "openai/clip-vit-base-patch32",
        "embedding_dimension": 4,
        "vector": [0.1, 0.2, 0.3, 0.4],
    }
    defaults.update(overrides)
    return ImageEmbedding(**defaults)


class TestImageEmbedding:
    def test_constructs_with_all_fields(self) -> None:
        product_id = uuid4()

        embedding = _embedding(product_id=product_id)

        assert embedding.product_id == product_id
        assert embedding.model_name == "openai/clip-vit-base-patch32"
        assert embedding.embedding_dimension == 4
        assert embedding.vector == [0.1, 0.2, 0.3, 0.4]

    def test_defaults_created_at_to_now(self) -> None:
        before = datetime.now(UTC)

        embedding = _embedding()

        after = datetime.now(UTC)
        assert before <= embedding.created_at <= after

    def test_accepts_an_explicit_created_at(self) -> None:
        created_at = datetime(2026, 1, 1, tzinfo=UTC)

        embedding = _embedding(created_at=created_at)

        assert embedding.created_at == created_at

    def test_rejects_a_non_positive_embedding_dimension(self) -> None:
        with pytest.raises(ValidationError):
            _embedding(embedding_dimension=0)

    def test_rejects_a_vector_shorter_than_the_declared_dimension(self) -> None:
        with pytest.raises(ValidationError):
            _embedding(embedding_dimension=4, vector=[0.1, 0.2, 0.3])

    def test_rejects_a_vector_longer_than_the_declared_dimension(self) -> None:
        with pytest.raises(ValidationError):
            _embedding(embedding_dimension=4, vector=[0.1, 0.2, 0.3, 0.4, 0.5])

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        embedding = _embedding()

        dumped = embedding.model_dump(mode="json")
        restored = ImageEmbedding.model_validate(dumped)

        assert restored == embedding
