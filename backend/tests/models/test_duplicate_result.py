"""Unit tests for `DuplicateResult`."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.duplicate_result import DuplicateResult
from app.models.similarity_signal import SimilaritySignal


def _signal(name: str = "image", score: float = 0.9, weight: float = 0.35) -> SimilaritySignal:
    return SimilaritySignal(name=name, score=score, weight=weight, contribution=score * weight)


class TestDuplicateResult:
    def test_constructs_with_all_fields(self) -> None:
        product_id = uuid4()
        signals = [_signal("image", 0.9, 0.35), _signal("text", 0.8, 0.25)]

        result = DuplicateResult(product_id=product_id, signals=signals, overall_similarity=0.5)

        assert result.product_id == product_id
        assert result.signals == signals
        assert result.overall_similarity == 0.5

    def test_signals_defaults_to_empty_list(self) -> None:
        result = DuplicateResult(product_id=uuid4(), overall_similarity=0.0)

        assert result.signals == []

    def test_rejects_an_overall_similarity_above_one(self) -> None:
        with pytest.raises(ValidationError):
            DuplicateResult(product_id=uuid4(), overall_similarity=1.5)

    def test_rejects_a_negative_overall_similarity(self) -> None:
        with pytest.raises(ValidationError):
            DuplicateResult(product_id=uuid4(), overall_similarity=-0.1)

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        result = DuplicateResult(
            product_id=uuid4(),
            signals=[_signal("metadata", 0.7, 0.2)],
            overall_similarity=0.14,
        )

        dumped = result.model_dump(mode="json")
        restored = DuplicateResult.model_validate(dumped)

        assert restored == result
