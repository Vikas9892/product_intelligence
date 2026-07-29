"""Unit tests for `BenchmarkReport`."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.benchmark_report import BenchmarkReport
from app.models.evaluation_query import EvaluationTaskType
from app.models.evaluation_result import EvaluationQueryResult
from app.models.model_info import ModelInfo
from app.models.model_type import ModelType
from app.models.retrieval_metrics import RetrievalMetrics


class TestBenchmarkReport:
    def test_constructs_with_all_fields(self) -> None:
        report = BenchmarkReport(
            generated_at=datetime.now(UTC),
            dataset_size=5,
            overall_metrics={"retrieval": RetrievalMetrics(mrr=0.8, query_count=5)},
            query_results=[
                EvaluationQueryResult(query_id="q1", task_type=EvaluationTaskType.RETRIEVAL)
            ],
            total_duration_seconds=1.5,
            failure_count=0,
        )

        assert report.dataset_size == 5
        assert report.overall_metrics["retrieval"].mrr == 0.8
        assert len(report.query_results) == 1

    def test_defaults(self) -> None:
        report = BenchmarkReport(
            generated_at=datetime.now(UTC), dataset_size=0, total_duration_seconds=0.0
        )

        assert report.overall_metrics == {}
        assert report.query_results == []
        assert report.failure_count == 0
        assert report.models == []

    def test_records_the_models_snapshot(self) -> None:
        model_info = ModelInfo(
            model_name="openai/clip-vit-base-patch32",
            version="1.0.0",
            model_type=ModelType.IMAGE_EMBEDDING,
            dimension=512,
        )

        report = BenchmarkReport(
            generated_at=datetime.now(UTC),
            dataset_size=0,
            total_duration_seconds=0.0,
            models=[model_info],
        )

        assert report.models == [model_info]

    def test_rejects_a_negative_dataset_size(self) -> None:
        with pytest.raises(ValidationError):
            BenchmarkReport(
                generated_at=datetime.now(UTC), dataset_size=-1, total_duration_seconds=0.0
            )

    def test_rejects_a_negative_duration(self) -> None:
        with pytest.raises(ValidationError):
            BenchmarkReport(
                generated_at=datetime.now(UTC), dataset_size=0, total_duration_seconds=-1.0
            )

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        report = BenchmarkReport(
            generated_at=datetime.now(UTC),
            dataset_size=2,
            overall_metrics={
                "retrieval": RetrievalMetrics(mrr=0.5),
                "duplicate": RetrievalMetrics(mrr=0.9),
            },
            query_results=[
                EvaluationQueryResult(query_id="q1", task_type=EvaluationTaskType.RETRIEVAL),
                EvaluationQueryResult(
                    query_id="q2", task_type=EvaluationTaskType.DUPLICATE, error="boom"
                ),
            ],
            total_duration_seconds=2.0,
            failure_count=1,
        )

        dumped = report.model_dump(mode="json")
        restored = BenchmarkReport.model_validate(dumped)

        assert restored == report
