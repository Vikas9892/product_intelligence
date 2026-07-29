"""`RerankExplainer`: explains one cross-encoder reranking outcome (Phase 16).

Reads a `RerankedCandidate` (its original retrieval score, its
cross-encoder rerank score, and how far it moved) and reports the
"Initial Rank -> Cross-Encoder Score -> Final Rank" story the phase asks
for. Pure and read-only — it explains a rerank that already happened,
reusing the `RerankReason` the reranker itself produced rather than
recomputing rank movement.
"""

from app.models.decision_reason import DecisionReason
from app.models.explanation_trace import ExplanationTrace
from app.models.reranked_candidate import RerankedCandidate
from app.services.explanations.base_explainer import BaseExplainer
from app.services.explanations.explanation_builder import ExplanationBuilder


class RerankExplainer(BaseExplainer[RerankedCandidate]):
    """Explains how cross-encoder reranking changed a candidate's rank and score."""

    def __init__(self, *, builder: ExplanationBuilder | None = None) -> None:
        self._builder = builder if builder is not None else ExplanationBuilder()

    def explain(self, subject: RerankedCandidate) -> ExplanationTrace:
        """Explain `subject`'s rank movement and cross-encoder score."""
        original = self._builder.weight("original_score", subject.original_score, 1.0)
        rerank = self._builder.weight("cross_encoder_score", subject.rerank_score, 1.0)
        breakdown = self._builder.breakdown([original, rerank], total=subject.rerank_score)

        reasons = [
            DecisionReason(
                code="cross_encoder_score",
                description=f"cross-encoder relevance {subject.rerank_score:.0%}",
                weight=subject.rerank_score,
            ),
            DecisionReason(
                code="rank_movement",
                description=(
                    subject.reason.explanation
                    or f"final rank {subject.reason.final_rank} "
                    f"(from {subject.reason.original_rank})"
                ),
            ),
        ]

        return ExplanationTrace(
            decision_type="reranking",
            summary=self._builder.summarize("Reranked by cross-encoder", reasons),
            subject_id=str(subject.product_id),
            reasons=reasons,
            breakdown=breakdown,
            confidence=subject.rerank_score,
        )
