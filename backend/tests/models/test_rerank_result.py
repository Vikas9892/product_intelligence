"""Unit tests for `RerankResult`."""

from uuid import uuid4

from app.models.rerank_reason import RerankReason
from app.models.rerank_result import RerankResult
from app.models.reranked_candidate import RerankedCandidate


def _candidate() -> RerankedCandidate:
    return RerankedCandidate(
        product_id=uuid4(),
        original_score=0.4,
        rerank_score=0.9,
        final_rank=1,
        reason=RerankReason(original_rank=2, final_rank=1, rank_delta=1),
    )


class TestRerankResult:
    def test_defaults(self) -> None:
        result = RerankResult(query="red shoes")

        assert result.query == "red shoes"
        assert result.candidates == []
        assert result.processing_time == 0.0
        assert result.original_count == 0

    def test_constructs_with_all_fields(self) -> None:
        candidate = _candidate()

        result = RerankResult(
            query="red shoes",
            candidates=[candidate],
            processing_time=0.05,
            original_count=10,
        )

        assert result.candidates == [candidate]
        assert result.processing_time == 0.05
        assert result.original_count == 10

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        result = RerankResult(
            query="red shoes", candidates=[_candidate()], processing_time=0.02, original_count=5
        )

        dumped = result.model_dump(mode="json")
        restored = RerankResult.model_validate(dumped)

        assert restored == result
