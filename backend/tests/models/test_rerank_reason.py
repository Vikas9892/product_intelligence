"""Unit tests for `RerankReason`."""

from app.models.rerank_reason import RerankReason


class TestRerankReason:
    def test_constructs_with_all_fields(self) -> None:
        reason = RerankReason(original_rank=5, final_rank=2, rank_delta=3, explanation="Moved up.")

        assert reason.original_rank == 5
        assert reason.final_rank == 2
        assert reason.rank_delta == 3
        assert reason.explanation == "Moved up."

    def test_explanation_defaults_to_empty_string(self) -> None:
        reason = RerankReason(original_rank=1, final_rank=1, rank_delta=0)

        assert reason.explanation == ""

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        reason = RerankReason(original_rank=3, final_rank=1, rank_delta=2, explanation="Moved up.")

        dumped = reason.model_dump(mode="json")
        restored = RerankReason.model_validate(dumped)

        assert restored == reason
