"""`HybridSearchExplainer`: explains one hybrid-search result (Phase 16).

Reads a `HybridSearchResult`'s per-modality retrieval scores (image, text)
and the configured fusion weights, and reports how the final hybrid score
was composed — the phase's own "Embedding Similarity 0.91 -> Text
Similarity 0.88 -> Final Hybrid Score 0.90" example. Pure and read-only:
it never re-runs search or mutates the result, matching
`HybridSearchService`'s own fusion formula
(`image_weight·image_score + text_weight·text_score`) rather than
inventing a new one.
"""

from app.core.config import settings
from app.models.decision_reason import DecisionReason
from app.models.explanation_trace import ExplanationTrace
from app.models.search import HybridSearchResult
from app.services.explanations.base_explainer import BaseExplainer
from app.services.explanations.explanation_builder import ExplanationBuilder


class HybridSearchExplainer(BaseExplainer[HybridSearchResult]):
    """Explains how a hybrid-search result's final score was fused from image + text similarity."""

    def __init__(
        self,
        *,
        builder: ExplanationBuilder | None = None,
        image_weight: float | None = None,
        text_weight: float | None = None,
    ) -> None:
        self._builder = builder if builder is not None else ExplanationBuilder()
        self._image_weight = (
            image_weight if image_weight is not None else settings.hybrid_search.image_weight
        )
        self._text_weight = (
            text_weight if text_weight is not None else settings.hybrid_search.text_weight
        )

    def explain(self, subject: HybridSearchResult) -> ExplanationTrace:
        """Explain how `subject`'s final hybrid score was composed."""
        image_weight = self._builder.weight(
            "image_similarity", subject.image_score, self._image_weight
        )
        text_weight = self._builder.weight("text_similarity", subject.text_score, self._text_weight)
        breakdown = self._builder.breakdown([image_weight, text_weight], total=subject.score)

        reasons = [
            DecisionReason(
                code="image_similarity",
                description=f"{subject.image_score:.0%} image similarity",
                weight=self._image_weight,
            ),
            DecisionReason(
                code="text_similarity",
                description=f"{subject.text_score:.0%} text similarity",
                weight=self._text_weight,
            ),
        ]

        return ExplanationTrace(
            decision_type="hybrid_search",
            summary=self._builder.summarize("Ranked by hybrid similarity", reasons),
            subject_id=str(subject.product_id),
            reasons=reasons,
            breakdown=breakdown,
            confidence=subject.score,
        )
