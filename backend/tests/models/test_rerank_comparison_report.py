"""Unit tests for `RerankComparisonReport`."""

from datetime import UTC, datetime

from app.models.benchmark_report import BenchmarkReport
from app.models.rerank_comparison_report import RerankComparisonReport
from app.models.retrieval_metrics import RetrievalMetrics


def _report(*, mrr: float) -> BenchmarkReport:
    return BenchmarkReport(
        generated_at=datetime.now(UTC),
        dataset_size=1,
        overall_metrics={"retrieval": RetrievalMetrics(mrr=mrr, query_count=1)},
        total_duration_seconds=0.01,
        failure_count=0,
    )


class TestRerankComparisonReport:
    def test_defaults(self) -> None:
        without_reranking = _report(mrr=0.81)
        with_reranking = _report(mrr=0.90)

        report = RerankComparisonReport(
            without_reranking=without_reranking, with_reranking=with_reranking
        )

        assert report.without_reranking == without_reranking
        assert report.with_reranking == with_reranking
        assert report.improvement == {}

    def test_constructs_with_improvement(self) -> None:
        report = RerankComparisonReport(
            without_reranking=_report(mrr=0.81),
            with_reranking=_report(mrr=0.90),
            improvement={"retrieval": {"mrr": 0.09}},
        )

        assert report.improvement["retrieval"]["mrr"] == 0.09

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        report = RerankComparisonReport(
            without_reranking=_report(mrr=0.81),
            with_reranking=_report(mrr=0.90),
            improvement={"retrieval": {"mrr": 0.09}},
        )

        dumped = report.model_dump(mode="json")
        restored = RerankComparisonReport.model_validate(dumped)

        assert restored == report
