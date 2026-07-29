"""Unit tests for the Phase 16 explanation domain models."""

import pytest
from pydantic import ValidationError

from app.models.confidence_breakdown import ConfidenceBreakdown
from app.models.decision_reason import DecisionReason
from app.models.decision_weight import DecisionWeight
from app.models.explanation_trace import ExplanationTrace


class TestDecisionReason:
    def test_constructs_with_optional_weight(self) -> None:
        reason = DecisionReason(code="same_brand", description="Same brand", weight=0.5)
        assert reason.weight == 0.5

    def test_weight_defaults_to_none(self) -> None:
        reason = DecisionReason(code="same_brand", description="Same brand")
        assert reason.weight is None

    def test_rejects_a_blank_code(self) -> None:
        with pytest.raises(ValidationError):
            DecisionReason(code="", description="x")

    def test_rejects_a_weight_above_one(self) -> None:
        with pytest.raises(ValidationError):
            DecisionReason(code="c", description="d", weight=1.5)


class TestDecisionWeight:
    def test_carries_value_weight_and_contribution(self) -> None:
        weight = DecisionWeight(name="embedding", value=0.9, weight=0.7, contribution=0.63)
        assert weight.contribution == 0.63

    def test_allows_values_outside_zero_one(self) -> None:
        # A cross-encoder logit can be negative or exceed 1 — unlike SimilaritySignal.
        weight = DecisionWeight(name="cross_encoder", value=3.2, weight=1.0, contribution=3.2)
        assert weight.value == 3.2


class TestConfidenceBreakdown:
    def test_defaults_to_no_components(self) -> None:
        breakdown = ConfidenceBreakdown(total=0.9)
        assert breakdown.components == []

    def test_carries_components(self) -> None:
        breakdown = ConfidenceBreakdown(
            components=[DecisionWeight(name="a", value=1.0, weight=0.5, contribution=0.5)],
            total=0.5,
        )
        assert len(breakdown.components) == 1


class TestExplanationTrace:
    def test_defaults(self) -> None:
        trace = ExplanationTrace(decision_type="duplicate", summary="A summary.")
        assert trace.subject_id is None
        assert trace.reasons == []
        assert trace.breakdown is None
        assert trace.confidence is None
        assert trace.created_at is not None

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        trace = ExplanationTrace(
            decision_type="recommendation",
            summary="Because it is similar.",
            subject_id="abc",
            reasons=[DecisionReason(code="same_brand", description="Same brand")],
            breakdown=ConfidenceBreakdown(total=0.9),
            confidence=0.9,
        )
        restored = ExplanationTrace.model_validate(trace.model_dump(mode="json"))
        assert restored == trace
