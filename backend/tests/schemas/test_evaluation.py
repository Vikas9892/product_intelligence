"""Unit tests for the evaluation schemas."""

from uuid import uuid4

from app.schemas.evaluation import (
    EvaluationMetricsInfo,
    EvaluationQueryResultInfo,
    EvaluationRunRequest,
    EvaluationRunResponse,
)


class TestEvaluationRunRequest:
    def test_defaults_to_running_everything(self) -> None:
        request = EvaluationRunRequest()

        assert request.query_ids is None
        assert request.limit is None

    def test_constructs_with_all_fields(self) -> None:
        request = EvaluationRunRequest(query_ids=["q1", "q2"], limit=5)

        assert request.query_ids == ["q1", "q2"]
        assert request.limit == 5


class TestEvaluationMetricsInfo:
    def test_defaults(self) -> None:
        metrics = EvaluationMetricsInfo()

        assert metrics.precision_at_k == {}
        assert metrics.mrr == 0.0
        assert metrics.query_count == 0


class TestEvaluationRunResponse:
    def test_round_trips_through_model_dump_and_validate(self) -> None:
        response = EvaluationRunResponse(
            summary="1 queries evaluated, 0 failures, 0.01s total.",
            dataset_size=1,
            total_duration_seconds=0.01,
            average_latency_seconds=0.005,
            failure_count=0,
            overall_metrics={"retrieval": EvaluationMetricsInfo(mrr=1.0, query_count=1)},
            query_results=[
                EvaluationQueryResultInfo(
                    query_id="q1",
                    task_type="retrieval",
                    retrieved_products=[uuid4()],
                    latency_seconds=0.005,
                    reciprocal_rank=1.0,
                )
            ],
        )

        dumped = response.model_dump(mode="json")
        restored = EvaluationRunResponse.model_validate(dumped)

        assert restored == response

    def test_defaults(self) -> None:
        response = EvaluationRunResponse(
            summary="0 queries evaluated, 0 failures, 0.00s total.",
            dataset_size=0,
            total_duration_seconds=0.0,
            average_latency_seconds=0.0,
            failure_count=0,
        )

        assert response.overall_metrics == {}
        assert response.query_results == []
