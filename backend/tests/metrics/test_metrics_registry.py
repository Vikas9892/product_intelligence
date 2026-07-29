"""Unit tests for `MetricsRegistry`.

Every test constructs with its own fresh `CollectorRegistry` (never the
process-wide default) plus a fake synchronous Redis client, so tests
never depend on shared global state or a real Redis server.
"""

from typing import Any

from prometheus_client import CollectorRegistry

from app.metrics.metrics_registry import MetricsRegistry


class _FakeSyncRedisClient:
    """Fake enough of `redis.Redis` for `_poll_queue_length`'s `llen`/`hlen` calls."""

    def __init__(self, *, lengths: dict[str, int] | None = None, raises: bool = False) -> None:
        self._lengths = lengths if lengths is not None else {}
        self._raises = raises

    def llen(self, key: str) -> int:
        if self._raises:
            raise ConnectionError("boom")
        return self._lengths.get(key, 0)

    def hlen(self, key: str) -> int:
        if self._raises:
            raise ConnectionError("boom")
        return self._lengths.get(key, 0)


def _registry(**kwargs: Any) -> MetricsRegistry:
    return MetricsRegistry(
        registry=CollectorRegistry(),
        sync_redis_client=kwargs.pop("sync_redis_client", _FakeSyncRedisClient()),
        **kwargs,
    )


class TestConstruction:
    def test_can_be_constructed_more_than_once_without_raising(self) -> None:
        registry = CollectorRegistry()
        client = _FakeSyncRedisClient()

        MetricsRegistry(registry=registry, sync_redis_client=client)
        MetricsRegistry(registry=registry, sync_redis_client=client)  # must not raise

    def test_applies_the_configured_namespace(self) -> None:
        registry = CollectorRegistry()

        metrics = MetricsRegistry(
            registry=registry, namespace="myns", sync_redis_client=_FakeSyncRedisClient()
        )

        metrics.recommendation_requests_total.inc()
        assert registry.get_sample_value("myns_recommendation_requests_total") == 1.0


class TestObserveEmbedding:
    def test_records_latency_and_success(self) -> None:
        metrics = _registry()

        metrics.observe_embedding(model="clip", seconds=0.1, success=True)

        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_embedding_inference_total",
                {"model": "clip", "status": "success"},
            )
            == 1.0
        )

    def test_records_failure_status(self) -> None:
        metrics = _registry()

        metrics.observe_embedding(model="bge", seconds=0.1, success=False)

        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_embedding_inference_total",
                {"model": "bge", "status": "failure"},
            )
            == 1.0
        )

    def test_no_ops_when_disabled(self) -> None:
        metrics = _registry(enabled=False)

        metrics.observe_embedding(model="clip", seconds=0.1, success=True)

        # No sample at all — the label combination was never touched,
        # unlike an enabled call which would create it at value 1.0.
        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_embedding_inference_total",
                {"model": "clip", "status": "success"},
            )
            is None
        )


class TestObserveModelLoad:
    def test_records_load_time_per_model_type(self) -> None:
        metrics = _registry()

        metrics.observe_model_load(model_type="image_embedding", seconds=2.5)

        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_model_load_seconds_count", {"model_type": "image_embedding"}
            )
            == 1.0
        )


class TestObserveRerank:
    def test_records_latency_and_success(self) -> None:
        metrics = _registry()

        metrics.observe_rerank(seconds=0.2, success=True)

        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_rerank_inference_total", {"status": "success"}
            )
            == 1.0
        )
        assert (
            metrics._registry.get_sample_value("product_intelligence_rerank_latency_seconds_count")
            == 1.0
        )


class TestRecordRecommendationRequest:
    def test_increments_the_counter(self) -> None:
        metrics = _registry()

        metrics.record_recommendation_request()
        metrics.record_recommendation_request()

        assert (
            metrics._registry.get_sample_value("product_intelligence_recommendation_requests_total")
            == 2.0
        )


class TestRecordDuplicateDetection:
    def test_increments_total_and_observes_each_similarity_score(self) -> None:
        metrics = _registry()

        metrics.record_duplicate_detection(similarity_scores=[0.5, 0.9])

        assert (
            metrics._registry.get_sample_value("product_intelligence_duplicate_detection_total")
            == 1.0
        )
        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_duplicate_similarity_score_count"
            )
            == 2.0
        )

    def test_handles_an_empty_candidate_list(self) -> None:
        metrics = _registry()

        metrics.record_duplicate_detection(similarity_scores=[])

        assert (
            metrics._registry.get_sample_value("product_intelligence_duplicate_detection_total")
            == 1.0
        )
        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_duplicate_similarity_score_count"
            )
            == 0.0
        )


class TestObserveProductUpload:
    def test_records_a_sample(self) -> None:
        metrics = _registry()

        metrics.observe_product_upload(1.23)

        assert (
            metrics._registry.get_sample_value("product_intelligence_product_upload_seconds_count")
            == 1.0
        )


class TestRecordWorkerJob:
    def test_records_success(self) -> None:
        metrics = _registry()

        metrics.record_worker_job(status="success", seconds=0.5)

        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_worker_jobs_total", {"status": "success"}
            )
            == 1.0
        )
        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_worker_job_duration_seconds_count"
            )
            == 1.0
        )

    def test_records_failure(self) -> None:
        metrics = _registry()

        metrics.record_worker_job(status="failure", seconds=0.5)

        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_worker_jobs_total", {"status": "failure"}
            )
            == 1.0
        )


class TestRecordDuplicateVerification:
    def test_records_confidence_and_a_duplicate_decision(self) -> None:
        metrics = _registry()

        metrics.record_duplicate_verification(confidence=0.98, is_duplicate=True)

        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_duplicate_verification_confidence_count"
            )
            == 1.0
        )
        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_duplicate_verification_decisions_total",
                {"decision": "duplicate"},
            )
            == 1.0
        )

    def test_records_a_not_duplicate_decision(self) -> None:
        metrics = _registry()

        metrics.record_duplicate_verification(confidence=0.10, is_duplicate=False)

        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_duplicate_verification_decisions_total",
                {"decision": "not_duplicate"},
            )
            == 1.0
        )

    def test_none_confidence_still_counts_the_decision_without_a_sample(self) -> None:
        metrics = _registry()

        metrics.record_duplicate_verification(confidence=None, is_duplicate=False)

        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_duplicate_verification_confidence_count"
            )
            == 0.0
        )
        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_duplicate_verification_decisions_total",
                {"decision": "not_duplicate"},
            )
            == 1.0
        )


class TestRecordExplanation:
    def test_records_latency_decision_type_and_confidence(self) -> None:
        metrics = _registry()

        metrics.record_explanation(decision_type="duplicate", seconds=0.01, confidence=0.9)

        assert (
            metrics._registry.get_sample_value("product_intelligence_explanation_seconds_count")
            == 1.0
        )
        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_explanations_total", {"decision_type": "duplicate"}
            )
            == 1.0
        )
        assert (
            metrics._registry.get_sample_value("product_intelligence_explanation_confidence_count")
            == 1.0
        )

    def test_none_confidence_still_records_latency_and_count(self) -> None:
        metrics = _registry()

        metrics.record_explanation(decision_type="recommendation", seconds=0.01, confidence=None)

        assert (
            metrics._registry.get_sample_value("product_intelligence_explanation_confidence_count")
            == 0.0
        )
        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_explanations_total", {"decision_type": "recommendation"}
            )
            == 1.0
        )


class TestDisabledNoOpsEverywhere:
    def test_every_record_and_observe_method_no_ops_when_disabled(self) -> None:
        metrics = _registry(enabled=False)

        metrics.observe_model_load(model_type="image_embedding", seconds=1.0)
        metrics.observe_rerank(seconds=1.0, success=True)
        metrics.record_recommendation_request()
        metrics.record_duplicate_detection(similarity_scores=[0.5])
        metrics.observe_product_upload(1.0)
        metrics.record_worker_job(status="success", seconds=1.0)
        metrics.record_duplicate_verification(confidence=0.9, is_duplicate=True)
        metrics.record_explanation(decision_type="duplicate", seconds=1.0, confidence=0.9)

        # `model_load_seconds`/`worker_jobs_total` are labeled — no sample
        # exists at all until `.labels(...)` is actually called.
        assert (
            metrics._registry.get_sample_value("product_intelligence_model_load_seconds_count")
            is None
        )
        assert metrics._registry.get_sample_value("product_intelligence_worker_jobs_total") is None
        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_duplicate_verification_confidence_count"
            )
            == 0.0
        )
        # The rest are unlabeled — `prometheus_client` initializes them at
        # 0.0 on construction, so "no-op" means "still 0.0", not "no sample".
        assert (
            metrics._registry.get_sample_value("product_intelligence_rerank_latency_seconds_count")
            == 0.0
        )
        assert (
            metrics._registry.get_sample_value("product_intelligence_recommendation_requests_total")
            == 0.0
        )
        assert (
            metrics._registry.get_sample_value("product_intelligence_duplicate_detection_total")
            == 0.0
        )
        assert (
            metrics._registry.get_sample_value("product_intelligence_product_upload_seconds_count")
            == 0.0
        )


class TestQueueGauges:
    def test_queue_depth_reflects_the_pending_list_length(self) -> None:
        client = _FakeSyncRedisClient(lengths={"product_processing:pending": 3})
        metrics = MetricsRegistry(registry=CollectorRegistry(), sync_redis_client=client)

        assert metrics._registry.get_sample_value("product_intelligence_queue_depth") == 3.0

    def test_worker_jobs_running_reflects_the_processing_hash_length(self) -> None:
        client = _FakeSyncRedisClient(lengths={"product_processing:processing": 2})
        metrics = MetricsRegistry(registry=CollectorRegistry(), sync_redis_client=client)

        assert metrics._registry.get_sample_value("product_intelligence_worker_jobs_running") == 2.0

    def test_worker_dead_letter_size_reflects_the_dead_letter_list_length(self) -> None:
        client = _FakeSyncRedisClient(lengths={"product_processing:dead_letter": 1})
        metrics = MetricsRegistry(registry=CollectorRegistry(), sync_redis_client=client)

        assert (
            metrics._registry.get_sample_value("product_intelligence_worker_dead_letter_size")
            == 1.0
        )

    def test_gauges_report_zero_when_redis_is_unreachable(self) -> None:
        client = _FakeSyncRedisClient(raises=True)
        metrics = MetricsRegistry(registry=CollectorRegistry(), sync_redis_client=client)

        assert metrics._registry.get_sample_value("product_intelligence_queue_depth") == 0.0
