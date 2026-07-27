"""Unit tests for `RetrievalMetrics`."""

import pytest
from pydantic import ValidationError

from app.models.retrieval_metrics import RetrievalMetrics


class TestRetrievalMetrics:
    def test_defaults(self) -> None:
        metrics = RetrievalMetrics()

        assert metrics.precision_at_k == {}
        assert metrics.recall_at_k == {}
        assert metrics.ndcg_at_k == {}
        assert metrics.hit_rate_at_k == {}
        assert metrics.mrr == 0.0
        assert metrics.average_latency_seconds == 0.0
        assert metrics.query_count == 0

    def test_constructs_with_all_fields(self) -> None:
        metrics = RetrievalMetrics(
            precision_at_k={1: 1.0, 5: 0.8, 10: 0.6},
            recall_at_k={1: 0.2, 5: 0.6, 10: 0.9},
            ndcg_at_k={1: 1.0, 5: 0.9, 10: 0.85},
            hit_rate_at_k={1: 1.0, 5: 1.0, 10: 1.0},
            mrr=0.75,
            average_latency_seconds=0.05,
            query_count=20,
        )

        assert metrics.precision_at_k[5] == 0.8
        assert metrics.mrr == 0.75
        assert metrics.query_count == 20

    def test_rejects_an_mrr_above_one(self) -> None:
        with pytest.raises(ValidationError):
            RetrievalMetrics(mrr=1.5)

    def test_rejects_a_negative_average_latency(self) -> None:
        with pytest.raises(ValidationError):
            RetrievalMetrics(average_latency_seconds=-0.1)

    def test_round_trips_through_model_dump_and_validate_with_integer_keys_preserved(self) -> None:
        metrics = RetrievalMetrics(
            precision_at_k={1: 1.0, 5: 0.8, 10: 0.6},
            mrr=0.5,
            query_count=3,
        )

        dumped = metrics.model_dump(mode="json")
        restored = RetrievalMetrics.model_validate(dumped)

        assert restored == metrics
        assert set(restored.precision_at_k.keys()) == {1, 5, 10}
