"""Unit tests for `app.metrics.metric_names` — mostly a duplication guard.

A typo that accidentally reused an existing constant's string value would
silently merge two logically distinct metrics into one Prometheus series;
this test only has to catch that.
"""

from app.metrics import metric_names


class TestMetricNames:
    def test_every_name_is_unique(self) -> None:
        names = [
            value
            for key, value in vars(metric_names).items()
            if key.isupper() and isinstance(value, str)
        ]

        assert len(names) == len(set(names))

    def test_includes_every_milestone_4_required_name(self) -> None:
        required = {
            metric_names.PRODUCT_UPLOAD_SECONDS,
            metric_names.EMBEDDING_LATENCY_SECONDS,
            metric_names.RERANK_LATENCY_SECONDS,
            metric_names.QUEUE_DEPTH,
            metric_names.WORKER_JOBS_TOTAL,
            metric_names.DUPLICATE_DETECTION_TOTAL,
            metric_names.RECOMMENDATION_REQUESTS_TOTAL,
        }

        assert required == {
            "product_upload_seconds",
            "embedding_latency_seconds",
            "rerank_latency_seconds",
            "queue_depth",
            "worker_jobs_total",
            "duplicate_detection_total",
            "recommendation_requests_total",
        }
