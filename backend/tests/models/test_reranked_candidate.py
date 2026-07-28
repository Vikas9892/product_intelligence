"""Unit tests for `RerankedCandidate`."""

from uuid import uuid4

from app.models.rerank_reason import RerankReason
from app.models.reranked_candidate import RerankedCandidate


class TestRerankedCandidate:
    def test_constructs_with_all_fields(self) -> None:
        product_id = uuid4()
        reason = RerankReason(original_rank=3, final_rank=1, rank_delta=2)

        candidate = RerankedCandidate(
            product_id=product_id,
            original_score=0.4,
            rerank_score=0.9,
            final_rank=1,
            metadata={"name": "Widget"},
            reason=reason,
        )

        assert candidate.product_id == product_id
        assert candidate.original_score == 0.4
        assert candidate.rerank_score == 0.9
        assert candidate.final_rank == 1
        assert candidate.metadata == {"name": "Widget"}
        assert candidate.reason == reason

    def test_metadata_defaults_to_an_empty_dict(self) -> None:
        candidate = RerankedCandidate(
            product_id=uuid4(),
            original_score=0.1,
            rerank_score=0.2,
            final_rank=1,
            reason=RerankReason(original_rank=1, final_rank=1, rank_delta=0),
        )

        assert candidate.metadata == {}

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        candidate = RerankedCandidate(
            product_id=uuid4(),
            original_score=0.4,
            rerank_score=0.9,
            final_rank=2,
            metadata={"brand": "Nike"},
            reason=RerankReason(
                original_rank=4, final_rank=2, rank_delta=2, explanation="Moved up."
            ),
        )

        dumped = candidate.model_dump(mode="json")
        restored = RerankedCandidate.model_validate(dumped)

        assert restored == candidate
