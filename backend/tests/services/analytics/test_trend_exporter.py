"""Unit tests for `trend_exporter.to_markdown`."""

from datetime import date

from app.models.analytics_report import TrendPoint, TrendReport
from app.services.analytics.trend_exporter import to_markdown


class TestToMarkdown:
    def test_renders_a_table(self) -> None:
        report = TrendReport(
            metric="uploads",
            granularity="daily",
            points=[
                TrendPoint(period_start=date(2026, 1, 1), value=5.0),
                TrendPoint(period_start=date(2026, 1, 2), value=0.0),
            ],
        )

        markdown = to_markdown(report)

        assert "# Uploads trend (daily)" in markdown
        assert "| Period start | Value |" in markdown
        assert "| 2026-01-01 | 5 |" in markdown
        assert "| 2026-01-02 | 0 |" in markdown

    def test_renders_a_fractional_value_as_is(self) -> None:
        report = TrendReport(
            metric="searches",
            granularity="weekly",
            points=[TrendPoint(period_start=date(2026, 1, 1), value=2.5)],
        )

        markdown = to_markdown(report)

        assert "| 2026-01-01 | 2.5 |" in markdown
