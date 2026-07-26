"""Unit tests for `DuplicateDecision`."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.duplicate_candidate import DuplicateCandidate
from app.models.duplicate_decision import DuplicateDecision


def _candidate(product_id: object = None, overall: float = 0.9) -> DuplicateCandidate:
    return DuplicateCandidate(
        product_id=product_id if product_id is not None else uuid4(),
        image_similarity=overall,
        text_similarity=overall,
        metadata_similarity=overall,
        attribute_similarity=overall,
        overall_similarity=overall,
    )


class TestDuplicateDecision:
    def test_constructs_a_duplicate_decision(self) -> None:
        matched_product = uuid4()
        candidates = [_candidate(matched_product, 0.95)]

        decision = DuplicateDecision(
            is_duplicate=True,
            confidence=0.95,
            reason="Overall similarity 0.95 exceeds the 0.90 threshold.",
            matched_product=matched_product,
            top_candidates=candidates,
        )

        assert decision.is_duplicate is True
        assert decision.confidence == 0.95
        assert decision.matched_product == matched_product
        assert decision.top_candidates == candidates

    def test_constructs_a_non_duplicate_decision_without_a_matched_product(self) -> None:
        decision = DuplicateDecision(
            is_duplicate=False, confidence=0.2, reason="No candidate exceeded the threshold."
        )

        assert decision.is_duplicate is False
        assert decision.matched_product is None
        assert decision.top_candidates == []

    def test_rejects_a_confidence_above_one(self) -> None:
        with pytest.raises(ValidationError):
            DuplicateDecision(is_duplicate=False, confidence=1.5, reason="invalid")

    def test_rejects_a_negative_confidence(self) -> None:
        with pytest.raises(ValidationError):
            DuplicateDecision(is_duplicate=False, confidence=-0.1, reason="invalid")

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        matched_product = uuid4()
        decision = DuplicateDecision(
            is_duplicate=True,
            confidence=0.91,
            reason="Matched an existing product.",
            matched_product=matched_product,
            top_candidates=[_candidate(matched_product, 0.91)],
        )

        dumped = decision.model_dump(mode="json")
        restored = DuplicateDecision.model_validate(dumped)

        assert restored == decision
