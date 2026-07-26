"""Unit tests for `SimilaritySignal`."""

import pytest
from pydantic import ValidationError

from app.models.similarity_signal import SimilaritySignal


class TestSimilaritySignal:
    def test_constructs_with_all_fields(self) -> None:
        signal = SimilaritySignal(name="image", score=0.9, weight=0.35, contribution=0.315)

        assert signal.name == "image"
        assert signal.score == 0.9
        assert signal.weight == 0.35
        assert signal.contribution == 0.315

    def test_rejects_a_score_above_one(self) -> None:
        with pytest.raises(ValidationError):
            SimilaritySignal(name="image", score=1.5, weight=0.35, contribution=0.5)

    def test_rejects_a_negative_score(self) -> None:
        with pytest.raises(ValidationError):
            SimilaritySignal(name="image", score=-0.1, weight=0.35, contribution=0.0)

    def test_rejects_a_negative_weight(self) -> None:
        with pytest.raises(ValidationError):
            SimilaritySignal(name="image", score=0.5, weight=-0.1, contribution=0.0)

    def test_rejects_a_contribution_above_one(self) -> None:
        with pytest.raises(ValidationError):
            SimilaritySignal(name="image", score=1.0, weight=1.0, contribution=1.1)

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        signal = SimilaritySignal(name="text", score=0.7, weight=0.25, contribution=0.175)

        dumped = signal.model_dump(mode="json")
        restored = SimilaritySignal.model_validate(dumped)

        assert restored == signal
