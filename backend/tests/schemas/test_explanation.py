"""Unit tests for `ExplanationResponse.from_trace`."""

from app.models.confidence_breakdown import ConfidenceBreakdown
from app.models.decision_reason import DecisionReason
from app.models.decision_weight import DecisionWeight
from app.models.explanation_trace import ExplanationTrace
from app.schemas.explanation import ExplanationResponse


class TestExplanationResponse:
    def test_maps_a_full_trace(self) -> None:
        trace = ExplanationTrace(
            decision_type="duplicate",
            summary="Products match.",
            subject_id="prod-1",
            reasons=[DecisionReason(code="same_brand", description="Same brand", weight=0.4)],
            breakdown=ConfidenceBreakdown(
                components=[
                    DecisionWeight(name="embedding", value=0.9, weight=0.7, contribution=0.63)
                ],
                total=0.63,
            ),
            confidence=0.63,
        )

        response = ExplanationResponse.from_trace(trace)

        assert response.decision_type == "duplicate"
        assert response.subject_id == "prod-1"
        assert response.summary == "Products match."
        assert response.confidence == 0.63
        assert response.reasons[0].code == "same_brand"
        assert response.breakdown is not None
        assert response.breakdown.components[0].contribution == 0.63

    def test_maps_a_trace_without_a_breakdown(self) -> None:
        trace = ExplanationTrace(decision_type="recommendation", summary="Similar product.")

        response = ExplanationResponse.from_trace(trace)

        assert response.breakdown is None
        assert response.confidence is None
        assert response.reasons == []
