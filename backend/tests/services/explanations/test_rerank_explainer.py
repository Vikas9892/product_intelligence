"""Unit tests for `RerankExplainer`."""

from uuid import uuid4

from app.models.rerank_reason import RerankReason
from app.models.reranked_candidate import RerankedCandidate
from app.services.explanations.rerank_explainer import RerankExplainer


def _candidate(
    *,
    original_score: float = 0.5,
    rerank_score: float = 0.92,
    original_rank: int = 5,
    final_rank: int = 1,
    explanation: str = "Moved up from position 5 to 1 after cross-encoder reranking.",
) -> RerankedCandidate:
    return RerankedCandidate(
        product_id=uuid4(),
        original_score=original_score,
        rerank_score=rerank_score,
        final_rank=final_rank,
        metadata={},
        reason=RerankReason(
            original_rank=original_rank,
            final_rank=final_rank,
            rank_delta=original_rank - final_rank,
            explanation=explanation,
        ),
    )


class TestRerankExplainer:
    def test_confidence_is_the_rerank_score(self) -> None:
        trace = RerankExplainer().explain(_candidate(rerank_score=0.92))

        assert trace.decision_type == "reranking"
        assert trace.confidence == 0.92

    def test_summary_includes_the_rank_movement_explanation(self) -> None:
        trace = RerankExplainer().explain(
            _candidate(explanation="Moved up from position 5 to 1 after cross-encoder reranking.")
        )

        assert "Moved up from position 5 to 1" in trace.summary

    def test_breakdown_has_original_and_cross_encoder_scores(self) -> None:
        trace = RerankExplainer().explain(_candidate(original_score=0.5, rerank_score=0.92))

        assert trace.breakdown is not None
        names = {c.name for c in trace.breakdown.components}
        assert names == {"original_score", "cross_encoder_score"}
        assert trace.breakdown.total == 0.92

    def test_falls_back_when_the_reason_has_no_explanation(self) -> None:
        trace = RerankExplainer().explain(_candidate(original_rank=3, final_rank=2, explanation=""))

        assert "final rank 2" in trace.summary
        assert "from 3" in trace.summary
