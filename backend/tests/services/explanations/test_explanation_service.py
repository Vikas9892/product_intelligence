"""Unit tests for `ExplanationService`."""

from uuid import uuid4

from app.models.confidence_breakdown import ConfidenceBreakdown
from app.models.decision_reason import DecisionReason
from app.models.decision_weight import DecisionWeight
from app.models.duplicate_verification import DuplicateVerification
from app.models.recommendation_candidate import RecommendationCandidate
from app.models.recommendation_reason import RecommendationReason
from app.models.rerank_reason import RerankReason
from app.models.reranked_candidate import RerankedCandidate
from app.models.search import HybridSearchResult, SearchModality
from app.services.explanations.explanation_service import ExplanationService


class TestExplainDelegators:
    def test_explain_hybrid_search(self) -> None:
        result = HybridSearchResult(
            product_id=uuid4(),
            score=0.9,
            metadata={},
            matched_modalities=[SearchModality.TEXT],
            image_score=0.8,
            text_score=0.7,
        )

        trace = ExplanationService().explain_hybrid_search(result)

        assert trace.decision_type == "hybrid_search"

    def test_explain_rerank(self) -> None:
        candidate = RerankedCandidate(
            product_id=uuid4(),
            original_score=0.5,
            rerank_score=0.9,
            final_rank=1,
            metadata={},
            reason=RerankReason(original_rank=3, final_rank=1, rank_delta=2),
        )

        trace = ExplanationService().explain_rerank(candidate)

        assert trace.decision_type == "reranking"

    def test_explain_duplicate(self) -> None:
        verification = DuplicateVerification(is_duplicate=True, confidence=0.9)

        trace = ExplanationService().explain_duplicate(verification)

        assert trace.decision_type == "duplicate"

    def test_explain_recommendation(self) -> None:
        candidate = RecommendationCandidate(
            product_id=uuid4(),
            similarity_score=0.9,
            quality_score=0.8,
            final_score=0.88,
            reason=RecommendationReason(shared_brand=True),
        )

        trace = ExplanationService().explain_recommendation(candidate)

        assert trace.decision_type == "recommendation"


class TestMetrics:
    def test_explain_records_a_metric(self) -> None:
        from prometheus_client import CollectorRegistry

        from app.metrics.metrics_registry import MetricsRegistry

        metrics = MetricsRegistry(registry=CollectorRegistry())
        verification = DuplicateVerification(is_duplicate=True, confidence=0.9)
        service = ExplanationService(metrics_registry=metrics)

        service.explain_duplicate(verification)

        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_explanations_total", {"decision_type": "duplicate"}
            )
            == 1.0
        )
        assert (
            metrics._registry.get_sample_value("product_intelligence_explanation_seconds_count")
            == 1.0
        )


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
