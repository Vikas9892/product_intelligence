"""`ExplanationService`: the facade the explanation API depends on (Phase 16).

Composes the per-subject explainers (`HybridSearchExplainer`,
`RerankExplainer`, `DuplicateExplainer`, `RecommendationExplainer`) behind
one typed facade, so a route depends only on this service rather than
wiring four explainers itself — matching every other `*Service` facade in
this codebase. `build_trace` remains for ad-hoc structured explanations;
the `explain_*` methods delegate to the matching explainer.

Accepts an optional `MetricsRegistry` (per this project's observability
convention); the actual explanation metrics — latency, count, average
confidence, decision-type distribution — are recorded here in Milestone
5. Holds no mutable per-request state, so one instance is safe to share
across concurrent requests.
"""

from collections.abc import Sequence

from app.core.logging import get_logger
from app.metrics.metrics_registry import MetricsRegistry
from app.models.confidence_breakdown import ConfidenceBreakdown
from app.models.decision_reason import DecisionReason
from app.models.duplicate_verification import DuplicateVerification
from app.models.explanation_trace import ExplanationTrace
from app.models.recommendation_candidate import RecommendationCandidate
from app.models.reranked_candidate import RerankedCandidate
from app.models.search import HybridSearchResult
from app.services.explanations.duplicate_explainer import DuplicateExplainer
from app.services.explanations.explanation_builder import ExplanationBuilder
from app.services.explanations.hybrid_search_explainer import HybridSearchExplainer
from app.services.explanations.recommendation_explainer import RecommendationExplainer
from app.services.explanations.rerank_explainer import RerankExplainer

logger = get_logger(__name__)


class ExplanationService:
    """Builds explanation traces from decisions or ad-hoc structured inputs."""

    def __init__(
        self,
        *,
        builder: ExplanationBuilder | None = None,
        hybrid_search_explainer: HybridSearchExplainer | None = None,
        rerank_explainer: RerankExplainer | None = None,
        duplicate_explainer: DuplicateExplainer | None = None,
        recommendation_explainer: RecommendationExplainer | None = None,
        metrics_registry: MetricsRegistry | None = None,
    ) -> None:
        self._builder = builder if builder is not None else ExplanationBuilder()
        self._hybrid_search_explainer = (
            hybrid_search_explainer
            if hybrid_search_explainer is not None
            else HybridSearchExplainer(builder=self._builder)
        )
        self._rerank_explainer = (
            rerank_explainer
            if rerank_explainer is not None
            else RerankExplainer(builder=self._builder)
        )
        self._duplicate_explainer = (
            duplicate_explainer
            if duplicate_explainer is not None
            else DuplicateExplainer(builder=self._builder)
        )
        self._recommendation_explainer = (
            recommendation_explainer
            if recommendation_explainer is not None
            else RecommendationExplainer(builder=self._builder)
        )
        self._metrics = metrics_registry if metrics_registry is not None else MetricsRegistry()

    def explain_hybrid_search(self, result: HybridSearchResult) -> ExplanationTrace:
        """Explain one hybrid-search result's fused score."""
        return self._hybrid_search_explainer.explain(result)

    def explain_rerank(self, candidate: RerankedCandidate) -> ExplanationTrace:
        """Explain one reranked candidate's rank movement and cross-encoder score."""
        return self._rerank_explainer.explain(candidate)

    def explain_duplicate(self, verification: DuplicateVerification) -> ExplanationTrace:
        """Explain one duplicate-verification decision."""
        return self._duplicate_explainer.explain(verification)

    def explain_recommendation(self, candidate: RecommendationCandidate) -> ExplanationTrace:
        """Explain one recommended product."""
        return self._recommendation_explainer.explain(candidate)

    def build_trace(
        self,
        *,
        decision_type: str,
        lead_in: str,
        reasons: Sequence[DecisionReason],
        subject_id: str | None = None,
        breakdown: ConfidenceBreakdown | None = None,
        confidence: float | None = None,
    ) -> ExplanationTrace:
        """Assemble an `ExplanationTrace` from already-decided structured inputs.

        `lead_in` seeds the natural-language summary; `reasons`'
        descriptions are joined onto it by `ExplanationBuilder`. Never
        recomputes the decision — it only phrases and structures what the
        caller already decided.
        """
        summary = self._builder.summarize(lead_in, reasons)
        trace = ExplanationTrace(
            decision_type=decision_type,
            summary=summary,
            subject_id=subject_id,
            reasons=list(reasons),
            breakdown=breakdown,
            confidence=confidence,
        )
        logger.info(
            "Explanation built: decision_type=%s, subject_id=%s, reasons=%d",
            decision_type,
            subject_id,
            len(trace.reasons),
        )
        return trace
