"""Trend-report exporters (Phase 18).

Renders a `TrendReport` as human-readable Markdown for the
`GET /analytics/trends?format=markdown` export; the JSON export is just
the report's own `model_dump`, so it needs no dedicated function here.
Pure and deterministic — same report, same Markdown.
"""

from app.models.analytics_report import TrendReport


def to_markdown(report: TrendReport) -> str:
    """Render `report` as a Markdown table of period-start dates and values."""
    lines = [
        f"# {report.metric.title()} trend ({report.granularity})",
        "",
        "| Period start | Value |",
        "|---|---|",
    ]
    for point in report.points:
        value = int(point.value) if point.value.is_integer() else point.value
        lines.append(f"| {point.period_start.isoformat()} | {value} |")
    lines.append("")
    return "\n".join(lines)
