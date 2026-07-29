"""Unit tests for `ExplanationService`."""

from app.models.confidence_breakdown import ConfidenceBreakdown
from app.models.decision_reason import DecisionReason
from app.models.decision_weight import DecisionWeight
from app.services.explanations.explanation_service import ExplanationService


class TestBuildTrace:
    def test_builds_a_summary_from_the_reasons(self) -> None:
        service = ExplanationService()

        trace = service.build_trace(
            decision_type="duplicate",
            lead_in="Products match because",
            reasons=[
                DecisionReason(code="same_brand", description="they share the same brand"),
                DecisionReason(code="same_category", description="the same category"),
            ],
            subject_id="prod-1",
            confidence=0.9,
        )

        assert trace.decision_type == "duplicate"
        assert trace.subject_id == "prod-1"
        assert trace.confidence == 0.9
        assert trace.summary == (
            "Products match because: they share the same brand and the same category."
        )
        assert len(trace.reasons) == 2

    def test_carries_the_confidence_breakdown(self) -> None:
        service = ExplanationService()
        breakdown = ConfidenceBreakdown(
            components=[DecisionWeight(name="embedding", value=0.9, weight=0.7, contribution=0.63)],
            total=0.63,
        )

        trace = service.build_trace(
            decision_type="hybrid_search",
            lead_in="Ranked by",
            reasons=[],
            breakdown=breakdown,
            confidence=0.63,
        )

        assert trace.breakdown == breakdown

    def test_empty_reasons_still_produce_a_summary(self) -> None:
        service = ExplanationService()

        trace = service.build_trace(
            decision_type="duplicate", lead_in="No duplicate found", reasons=[]
        )

        assert trace.summary == "No duplicate found."
