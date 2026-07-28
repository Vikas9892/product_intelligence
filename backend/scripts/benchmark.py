"""Runs the evaluation dataset and writes `benchmark.json`/`benchmark.md` (Phase 10).

Usage:

    uv run python scripts/benchmark.py [--dataset PATH] [--output DIR]
    uv run python scripts/benchmark.py --compare-reranking [--dataset PATH] [--output DIR]

Not part of the importable `app` package — a one-off/maintenance
entrypoint, matching `scripts/`'s own established purpose (see
`backend/README.md`'s folder-structure section: "One-off / maintenance
scripts (not part of the importable app)"). `--dataset` defaults to
`evaluation/dataset.json` (`DatasetLoader`'s own default); `--output`
defaults to `EvaluationSettings.benchmark_output_dir` (`reports/`).

Reuses `RetrievalEvaluator` entirely — this script does no evaluation
logic of its own, only report rendering (`benchmark.md`'s Markdown) and
file I/O around it. `--compare-reranking` (Phase 11) runs the dataset
with reranking forced off, then forced on, writing
`rerank_comparison.json`/`rerank_comparison.md` instead of the plain
benchmark reports — the reproducible "before vs. after" artifact the
phase spec's own worked example (MRR 0.81 -> 0.90) asks for.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Makes `app` importable when this script is run directly
# (`python scripts/benchmark.py`) rather than through pytest, which
# already puts `backend/` on `sys.path` via `pythonpath = ["."]`
# (`pyproject.toml`) — a plain script invocation only gets its own
# directory (`scripts/`) on `sys.path` by default, not `backend/`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.models.benchmark_report import BenchmarkReport
from app.models.rerank_comparison_report import RerankComparisonReport
from app.services.evaluation.dataset_loader import DatasetLoader
from app.services.evaluation.retrieval_evaluator import RetrievalEvaluator


def render_markdown(report: BenchmarkReport) -> str:
    """Render `report` as a human-readable Markdown summary."""
    lines = [
        "# Benchmark Report",
        "",
        f"- Generated at: {report.generated_at.isoformat()}",
        f"- Dataset size: {report.dataset_size}",
        f"- Total duration: {report.total_duration_seconds:.4f}s",
        f"- Failures: {report.failure_count}",
    ]
    if report.total_duration_seconds > 0:
        throughput = report.dataset_size / report.total_duration_seconds
        lines.append(f"- Throughput: {throughput:.2f} queries/second")
    lines.append("")

    for task_type in sorted(report.overall_metrics):
        metrics = report.overall_metrics[task_type]
        lines.append(f"## {task_type.title()}")
        lines.append("")
        lines.append(f"- Queries evaluated: {metrics.query_count}")
        lines.append(f"- MRR: {metrics.mrr:.4f}")
        lines.append(f"- Average latency: {metrics.average_latency_seconds:.4f}s")
        lines.append("")
        lines.append("| K | Precision@K | Recall@K | NDCG@K | Hit Rate@K |")
        lines.append("|---|---|---|---|---|")
        for k in sorted(metrics.precision_at_k):
            lines.append(
                f"| {k} | {metrics.precision_at_k[k]:.4f} | {metrics.recall_at_k[k]:.4f} "
                f"| {metrics.ndcg_at_k[k]:.4f} | {metrics.hit_rate_at_k[k]:.4f} |"
            )
        lines.append("")

    if report.failure_count:
        lines.append("## Failures")
        lines.append("")
        for result in report.query_results:
            if result.error is not None:
                lines.append(f"- `{result.query_id}` ({result.task_type.value}): {result.error}")
        lines.append("")

    return "\n".join(lines)


def render_comparison_markdown(comparison: RerankComparisonReport) -> str:
    """Render `comparison` (reranking disabled vs. enabled) as a human-readable Markdown summary."""
    lines = ["# Reranking Comparison Report", ""]

    for task_type in sorted(comparison.improvement):
        before = comparison.without_reranking.overall_metrics[task_type]
        after = comparison.with_reranking.overall_metrics[task_type]
        deltas = comparison.improvement[task_type]
        lines.append(f"## {task_type.title()}")
        lines.append("")
        lines.append("| Metric | Before | After | Delta |")
        lines.append("|---|---|---|---|")
        lines.append(f"| MRR | {before.mrr:.4f} | {after.mrr:.4f} | {deltas['mrr']:+.4f} |")
        for k in sorted(set(before.precision_at_k) & set(after.precision_at_k)):
            lines.append(
                f"| Precision@{k} | {before.precision_at_k[k]:.4f} | {after.precision_at_k[k]:.4f} "
                f"| {deltas[f'precision_at_{k}']:+.4f} |"
            )
        for k in sorted(set(before.recall_at_k) & set(after.recall_at_k)):
            lines.append(
                f"| Recall@{k} | {before.recall_at_k[k]:.4f} | {after.recall_at_k[k]:.4f} "
                f"| {deltas[f'recall_at_{k}']:+.4f} |"
            )
        for k in sorted(set(before.ndcg_at_k) & set(after.ndcg_at_k)):
            lines.append(
                f"| NDCG@{k} | {before.ndcg_at_k[k]:.4f} | {after.ndcg_at_k[k]:.4f} "
                f"| {deltas[f'ndcg_at_{k}']:+.4f} |"
            )
        for k in sorted(set(before.hit_rate_at_k) & set(after.hit_rate_at_k)):
            lines.append(
                f"| Hit Rate@{k} | {before.hit_rate_at_k[k]:.4f} | {after.hit_rate_at_k[k]:.4f} "
                f"| {deltas[f'hit_rate_at_{k}']:+.4f} |"
            )
        lines.append(
            f"| Avg latency (s) | {before.average_latency_seconds:.4f} "
            f"| {after.average_latency_seconds:.4f} "
            f"| {deltas['average_latency_seconds']:+.4f} |"
        )
        lines.append("")

    if not comparison.improvement:
        lines.append("No task type produced metrics under both configurations to compare.")
        lines.append("")

    return "\n".join(lines)


async def run_rerank_comparison(
    *, dataset_path: Path | None, output_dir: Path
) -> RerankComparisonReport:
    """Evaluate the dataset with reranking forced off, then on, and write comparison reports."""
    dataset_loader = (
        DatasetLoader(dataset_path=dataset_path) if dataset_path is not None else DatasetLoader()
    )
    evaluator = RetrievalEvaluator(dataset_loader=dataset_loader)
    comparison = await evaluator.compare_reranking()

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "rerank_comparison.json").write_text(
        json.dumps(comparison.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    (output_dir / "rerank_comparison.md").write_text(
        render_comparison_markdown(comparison), encoding="utf-8"
    )
    return comparison


async def run_benchmark(*, dataset_path: Path | None, output_dir: Path) -> BenchmarkReport:
    """Evaluate the dataset at `dataset_path` (or the configured default) and write reports to `output_dir`."""
    dataset_loader = (
        DatasetLoader(dataset_path=dataset_path) if dataset_path is not None else DatasetLoader()
    )
    evaluator = RetrievalEvaluator(dataset_loader=dataset_loader)
    report = await evaluator.evaluate()

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "benchmark.json").write_text(
        json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    (output_dir / "benchmark.md").write_text(render_markdown(report), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 10 evaluation benchmark.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Path to an evaluation dataset JSON file (defaults to evaluation/dataset.json).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Directory to write reports to "
        "(defaults to EVALUATION__BENCHMARK_OUTPUT_DIR, i.e. reports/).",
    )
    parser.add_argument(
        "--compare-reranking",
        action="store_true",
        help="Run the dataset with reranking forced off, then on, and write "
        "rerank_comparison.json/rerank_comparison.md instead of the plain benchmark reports.",
    )
    args = parser.parse_args()

    output_dir = (
        args.output if args.output is not None else settings.evaluation.benchmark_output_dir
    )

    if args.compare_reranking:
        comparison = asyncio.run(
            run_rerank_comparison(dataset_path=args.dataset, output_dir=output_dir)
        )
        print(
            f"Reranking comparison complete: {comparison.without_reranking.dataset_size} queries."
        )
        print(
            f"Reports written to {output_dir / 'rerank_comparison.json'} "
            f"and {output_dir / 'rerank_comparison.md'}"
        )
        return

    report = asyncio.run(run_benchmark(dataset_path=args.dataset, output_dir=output_dir))

    print(
        f"Benchmark complete: {report.dataset_size} queries, {report.failure_count} failures, "
        f"{report.total_duration_seconds:.4f}s total."
    )
    print(f"Reports written to {output_dir / 'benchmark.json'} and {output_dir / 'benchmark.md'}")


if __name__ == "__main__":
    main()
