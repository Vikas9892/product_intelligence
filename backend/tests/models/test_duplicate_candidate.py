"""Unit tests for `DuplicateCandidate`."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.duplicate_candidate import DuplicateCandidate


class TestDuplicateCandidate:
    def test_constructs_with_all_fields(self) -> None:
        product_id = uuid4()

        candidate = DuplicateCandidate(
            product_id=product_id,
            image_similarity=0.95,
            text_similarity=0.8,
            metadata_similarity=0.7,
            attribute_similarity=0.6,
            overall_similarity=0.82,
        )

        assert candidate.product_id == product_id
        assert candidate.image_similarity == 0.95
        assert candidate.text_similarity == 0.8
        assert candidate.metadata_similarity == 0.7
        assert candidate.attribute_similarity == 0.6
        assert candidate.overall_similarity == 0.82

    def test_rejects_a_similarity_above_one(self) -> None:
        with pytest.raises(ValidationError):
            DuplicateCandidate(
                product_id=uuid4(),
                image_similarity=1.5,
                text_similarity=0.5,
                metadata_similarity=0.5,
                attribute_similarity=0.5,
                overall_similarity=0.5,
            )

    def test_rejects_a_negative_similarity(self) -> None:
        with pytest.raises(ValidationError):
            DuplicateCandidate(
                product_id=uuid4(),
                image_similarity=-0.1,
                text_similarity=0.5,
                metadata_similarity=0.5,
                attribute_similarity=0.5,
                overall_similarity=0.5,
            )

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        candidate = DuplicateCandidate(
            product_id=uuid4(),
            image_similarity=0.95,
            text_similarity=0.8,
            metadata_similarity=0.7,
            attribute_similarity=0.6,
            overall_similarity=0.82,
        )

        dumped = candidate.model_dump(mode="json")
        restored = DuplicateCandidate.model_validate(dumped)

        assert restored == candidate
