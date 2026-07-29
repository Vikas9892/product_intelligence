"""Unit tests for `scripts/benchmark.py`.

`scripts/` has no `__init__.py` (it's not part of the importable `app`
package, matching every other file there — see that module's own
docstring) but is still importable as a namespace package here, since
`pyproject.toml`'s `pythonpath = ["."]` already puts `backend/` on
`sys.path` for the test suite.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from app.models.benchmark_report import BenchmarkReport
from app.models.evaluation_query import EvaluationTaskType
from app.models.evaluation_result import EvaluationQueryResult
from app.models.model_info import ModelInfo
from app.models.model_type import ModelType
from app.models.rerank_comparison_report import RerankComparisonReport
from app.models.retrieval_metrics import RetrievalMetrics
from scripts import benchmark


def _report(
    *,
    failure_count: int = 0,
    query_results: list[EvaluationQueryResult] | None = None,
    total_duration_seconds: float = 0.5,
    models: list[ModelInfo] | None = None,
) -> BenchmarkReport:
    return BenchmarkReport(
        generated_at=datetime.now(UTC),
        dataset_size=3,
        overall_metrics={
            "retrieval": RetrievalMetrics(
                precision_at_k={1: 1.0, 5: 0.8, 10: 0.6},
                recall_at_k={1: 0.2, 5: 0.6, 10: 0.9},
                ndcg_at_k={1: 1.0, 5: 0.9, 10: 0.85},
                hit_rate_at_k={1: 1.0, 5: 1.0, 10: 1.0},
                mrr=0.75,
                average_latency_seconds=0.01,
                query_count=3,
            )
        },
        query_results=query_results if query_results is not None else [],
        total_duration_seconds=total_duration_seconds,
        failure_count=failure_count,
        models=models if models is not None else [],
    )


class TestRenderMarkdown:
    def test_includes_summary_fields(self) -> None:
        markdown = benchmark.render_markdown(_report())

        assert "# Benchmark Report" in markdown
        assert "Dataset size: 3" in markdown
        assert "Failures: 0" in markdown

    def test_includes_a_throughput_line_when_duration_is_positive(self) -> None:
        markdown = benchmark.render_markdown(_report())

        assert "Throughput:" in markdown
        assert "queries/second" in markdown

    def test_omits_throughput_when_duration_is_zero(self) -> None:
        report = _report(total_duration_seconds=0.0)

        markdown = benchmark.render_markdown(report)

        assert "Throughput:" not in markdown

    def test_includes_a_per_task_type_metrics_table(self) -> None:
        markdown = benchmark.render_markdown(_report())

        assert "## Retrieval" in markdown
        assert "Precision@K" in markdown
        assert "| 1 | 1.0000 | 0.2000 | 1.0000 | 1.0000 |" in markdown

    def test_omits_a_models_section_when_none_were_recorded(self) -> None:
        markdown = benchmark.render_markdown(_report())

        assert "## Models" not in markdown

    def test_includes_a_models_section_listing_each_active_model(self) -> None:
        report = _report(
            models=[
                ModelInfo(
                    model_name="openai/clip-vit-base-patch32",
                    version="1.0.0",
                    model_type=ModelType.IMAGE_EMBEDDING,
                    dimension=512,
                )
            ]
        )

        markdown = benchmark.render_markdown(report)

        assert "## Models" in markdown
        assert "openai/clip-vit-base-patch32" in markdown
        assert "v1.0.0" in markdown

    def test_omits_a_failures_section_when_there_are_none(self) -> None:
        markdown = benchmark.render_markdown(_report(failure_count=0))

        assert "## Failures" not in markdown

    def test_includes_a_failures_section_listing_each_error(self) -> None:
        report = _report(
            failure_count=1,
            query_results=[
                EvaluationQueryResult(
                    query_id="bad-query",
                    task_type=EvaluationTaskType.DUPLICATE,
                    error="Product not found.",
                )
            ],
        )

        markdown = benchmark.render_markdown(report)

        assert "## Failures" in markdown
        assert "bad-query" in markdown
        assert "Product not found." in markdown


def _metrics_report(*, mrr: float) -> BenchmarkReport:
    return BenchmarkReport(
        generated_at=datetime.now(UTC),
        dataset_size=3,
        overall_metrics={
            "retrieval": RetrievalMetrics(
                precision_at_k={1: 1.0},
                recall_at_k={1: 0.2},
                ndcg_at_k={1: 1.0},
                hit_rate_at_k={1: 1.0},
                mrr=mrr,
                average_latency_seconds=0.01,
                query_count=3,
            )
        },
        total_duration_seconds=0.5,
        failure_count=0,
    )


def _comparison_report(
    *, mrr_before: float = 0.81, mrr_after: float = 0.90
) -> RerankComparisonReport:
    return RerankComparisonReport(
        without_reranking=_metrics_report(mrr=mrr_before),
        with_reranking=_metrics_report(mrr=mrr_after),
        improvement={
            "retrieval": {
                "mrr": mrr_after - mrr_before,
                "precision_at_1": 0.0,
                "recall_at_1": 0.0,
                "ndcg_at_1": 0.0,
                "hit_rate_at_1": 0.0,
                "average_latency_seconds": 0.0,
            }
        },
    )


class TestRenderComparisonMarkdown:
    def test_includes_the_header(self) -> None:
        markdown = benchmark.render_comparison_markdown(_comparison_report())

        assert "# Reranking Comparison Report" in markdown

    def test_includes_a_per_task_type_before_after_delta_table(self) -> None:
        markdown = benchmark.render_comparison_markdown(_comparison_report())

        assert "## Retrieval" in markdown
        assert "| MRR | 0.8100 | 0.9000 | +0.0900 |" in markdown

    def test_empty_improvement_yields_an_explanatory_note(self) -> None:
        comparison = RerankComparisonReport(
            without_reranking=_report(), with_reranking=_report(), improvement={}
        )

        markdown = benchmark.render_comparison_markdown(comparison)

        assert "No task type produced metrics" in markdown


class TestRunRerankComparison:
    async def test_writes_rerank_comparison_json_and_markdown_for_an_empty_dataset(
        self, tmp_path: Path
    ) -> None:
        dataset_path = tmp_path / "dataset.json"
        dataset_path.write_text("[]", encoding="utf-8")
        output_dir = tmp_path / "reports"

        comparison = await benchmark.run_rerank_comparison(
            dataset_path=dataset_path, output_dir=output_dir
        )

        assert comparison.without_reranking.dataset_size == 0
        assert comparison.with_reranking.dataset_size == 0
        json_path = output_dir / "rerank_comparison.json"
        markdown_path = output_dir / "rerank_comparison.md"
        assert json_path.is_file()
        assert markdown_path.is_file()

        dumped = json.loads(json_path.read_text(encoding="utf-8"))
        assert dumped["without_reranking"]["dataset_size"] == 0
        assert "# Reranking Comparison Report" in markdown_path.read_text(encoding="utf-8")

    async def test_creates_the_output_directory_if_missing(self, tmp_path: Path) -> None:
        dataset_path = tmp_path / "dataset.json"
        dataset_path.write_text("[]", encoding="utf-8")
        output_dir = tmp_path / "nested" / "reports"
        assert not output_dir.exists()

        await benchmark.run_rerank_comparison(dataset_path=dataset_path, output_dir=output_dir)

        assert output_dir.is_dir()


class TestRunBenchmark:
    async def test_writes_benchmark_json_and_markdown_for_an_empty_dataset(
        self, tmp_path: Path
    ) -> None:
        dataset_path = tmp_path / "dataset.json"
        dataset_path.write_text("[]", encoding="utf-8")
        output_dir = tmp_path / "reports"

        report = await benchmark.run_benchmark(dataset_path=dataset_path, output_dir=output_dir)

        assert report.dataset_size == 0
        json_path = output_dir / "benchmark.json"
        markdown_path = output_dir / "benchmark.md"
        assert json_path.is_file()
        assert markdown_path.is_file()

        dumped = json.loads(json_path.read_text(encoding="utf-8"))
        assert dumped["dataset_size"] == 0
        assert "# Benchmark Report" in markdown_path.read_text(encoding="utf-8")

    async def test_creates_the_output_directory_if_missing(self, tmp_path: Path) -> None:
        dataset_path = tmp_path / "dataset.json"
        dataset_path.write_text("[]", encoding="utf-8")
        output_dir = tmp_path / "nested" / "reports"
        assert not output_dir.exists()

        await benchmark.run_benchmark(dataset_path=dataset_path, output_dir=output_dir)

        assert output_dir.is_dir()
