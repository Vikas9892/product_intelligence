"""Unit tests for `EvaluationQueryResult`."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.evaluation_query import EvaluationTaskType
from app.models.evaluation_result import EvaluationQueryResult


class TestEvaluationQueryResult:
    def test_constructs_with_all_fields(self) -> None:
        product_id = uuid4()

        result = EvaluationQueryResult(
            query_id="q1",
            task_type=EvaluationTaskType.RETRIEVAL,
            retrieved_products=[product_id],
            latency_seconds=0.02,
            precision_at_k={1: 1.0},
            recall_at_k={1: 0.5},
            ndcg_at_k={1: 1.0},
            hit_rate_at_k={1: 1.0},
            reciprocal_rank=1.0,
        )

        assert result.retrieved_products == [product_id]
        assert result.error is None

    def test_defaults(self) -> None:
        result = EvaluationQueryResult(query_id="q1", task_type=EvaluationTaskType.RETRIEVAL)

        assert result.retrieved_products == []
        assert result.latency_seconds == 0.0
        assert result.reciprocal_rank == 0.0
        assert result.error is None

    def test_an_error_result_still_constructs(self) -> None:
        result = EvaluationQueryResult(
            query_id="q1",
            task_type=EvaluationTaskType.DUPLICATE,
            error="Product not found.",
        )

        assert result.error == "Product not found."
        assert result.retrieved_products == []

    def test_rejects_a_negative_latency(self) -> None:
        with pytest.raises(ValidationError):
            EvaluationQueryResult(
                query_id="q1", task_type=EvaluationTaskType.RETRIEVAL, latency_seconds=-0.1
            )

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        result = EvaluationQueryResult(
            query_id="q1",
            task_type=EvaluationTaskType.RECOMMENDATION,
            retrieved_products=[uuid4()],
            latency_seconds=0.01,
            precision_at_k={5: 0.6},
            reciprocal_rank=0.5,
        )

        dumped = result.model_dump(mode="json")
        restored = EvaluationQueryResult.model_validate(dumped)

        assert restored == result
