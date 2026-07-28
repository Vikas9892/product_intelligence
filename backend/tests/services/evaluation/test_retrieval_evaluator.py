"""Unit tests for `RetrievalEvaluator`.

Composes fake `HybridSearchService`/`DuplicateDetectionService`/
`RecommendationEngineService`/`DatasetLoader` doubles (each already
covered by their own test modules) so dispatch/metric-computation/
aggregation/error-isolation logic can be tested against precisely
controlled inputs.
"""

import asyncio
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.exceptions.errors import EvaluationException, ResourceNotFoundException
from app.models.duplicate_candidate import DuplicateCandidate
from app.models.duplicate_decision import DuplicateDecision
from app.models.evaluation_query import EvaluationQuery, EvaluationTaskType, GroundTruth
from app.models.recommendation_candidate import RecommendationCandidate
from app.models.recommendation_reason import RecommendationReason
from app.models.recommendation_result import RecommendationResult
from app.models.recommendation_type import RecommendationType
from app.models.search import HybridSearchResult, ProductFilters, SearchModality
from app.schemas.product import ProductImage
from app.services.duplicate.duplicate_detection_service import DuplicateDetectionService
from app.services.evaluation.dataset_loader import DatasetLoader
from app.services.evaluation.retrieval_evaluator import (
    RetrievalEvaluator,
    _hit_rate_at_k,
    _ndcg_at_k,
    _precision_at_k,
    _recall_at_k,
    _reciprocal_rank,
)
from app.services.recommendation.recommendation_engine_service import RecommendationEngineService
from app.services.vectorstore.hybrid_search_service import HybridSearchService


class _FakeHybridSearchService(HybridSearchService):
    def __init__(self, *, results: list[HybridSearchResult] | None = None) -> None:
        self._results = results if results is not None else []
        self.calls: list[dict[str, object]] = []

    async def search(
        self,
        *,
        image: ProductImage | None = None,
        text: str | None = None,
        top_k: int | None = None,
        filters: ProductFilters | None = None,
        reranking_enabled: bool | None = None,
    ) -> list[HybridSearchResult]:
        self.calls.append({"text": text, "top_k": top_k})
        return self._results


class _RoutingFakeHybridSearchService(HybridSearchService):
    """Routes each `search` call to the result registered for its query `text`,
    so concurrent `evaluate()` calls can be asserted to each get back their
    own result rather than one another's (or a shared/last-write-wins one)."""

    def __init__(self, results_by_text: dict[str, HybridSearchResult]) -> None:
        self._results_by_text = results_by_text

    async def search(
        self,
        *,
        image: ProductImage | None = None,
        text: str | None = None,
        top_k: int | None = None,
        filters: ProductFilters | None = None,
        reranking_enabled: bool | None = None,
    ) -> list[HybridSearchResult]:
        assert text is not None
        return [self._results_by_text[text]]


class _FakeDuplicateDetectionService(DuplicateDetectionService):
    def __init__(
        self, *, decision: DuplicateDecision | None = None, error: Exception | None = None
    ) -> None:
        self._decision = decision
        self._error = error
        self.calls: list[dict[str, object]] = []

    async def detect_by_product_id(
        self,
        product_id: UUID,
        *,
        top_k: int | None = None,
        threshold: float | None = None,
        reranking_enabled: bool | None = None,
    ) -> DuplicateDecision:
        self.calls.append({"product_id": product_id, "top_k": top_k})
        if self._error is not None:
            raise self._error
        assert self._decision is not None
        return self._decision


class _FakeRecommendationEngineService(RecommendationEngineService):
    def __init__(
        self, *, result: RecommendationResult | None = None, error: Exception | None = None
    ) -> None:
        self._result = result
        self._error = error
        self.calls: list[dict[str, object]] = []

    async def recommend(
        self,
        *,
        product_id: UUID,
        recommendation_type: RecommendationType = RecommendationType.SIMILAR,
        top_k: int | None = None,
        reranking_enabled: bool | None = None,
    ) -> RecommendationResult:
        self.calls.append(
            {"product_id": product_id, "recommendation_type": recommendation_type, "top_k": top_k}
        )
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


class _FakeDatasetLoader(DatasetLoader):
    def __init__(
        self, *, queries: list[EvaluationQuery] | None = None, error: Exception | None = None
    ) -> None:
        self._queries = queries if queries is not None else []
        self._error = error

    def load(self) -> list[EvaluationQuery]:
        if self._error is not None:
            raise self._error
        return self._queries


def _hybrid_result(product_id: UUID) -> HybridSearchResult:
    return HybridSearchResult(
        product_id=product_id, score=0.9, metadata={}, matched_modalities=[SearchModality.TEXT]
    )


def _duplicate_candidate(product_id: UUID) -> DuplicateCandidate:
    return DuplicateCandidate(
        product_id=product_id,
        image_similarity=0.9,
        text_similarity=0.9,
        metadata_similarity=0.9,
        attribute_similarity=0.9,
        overall_similarity=0.9,
    )


def _recommendation_candidate(product_id: UUID) -> RecommendationCandidate:
    return RecommendationCandidate(
        product_id=product_id,
        similarity_score=0.9,
        quality_score=0.9,
        final_score=0.9,
        reason=RecommendationReason(),
    )


def _evaluator(
    *,
    hybrid_search_service: HybridSearchService | None = None,
    duplicate_detection_service: DuplicateDetectionService | None = None,
    recommendation_engine_service: RecommendationEngineService | None = None,
    dataset_loader: DatasetLoader | None = None,
    latency_metrics_enabled: bool = False,
) -> RetrievalEvaluator:
    return RetrievalEvaluator(
        hybrid_search_service=(
            hybrid_search_service
            if hybrid_search_service is not None
            else _FakeHybridSearchService()
        ),
        duplicate_detection_service=(
            duplicate_detection_service
            if duplicate_detection_service is not None
            else _FakeDuplicateDetectionService()
        ),
        recommendation_engine_service=(
            recommendation_engine_service
            if recommendation_engine_service is not None
            else _FakeRecommendationEngineService()
        ),
        dataset_loader=dataset_loader if dataset_loader is not None else _FakeDatasetLoader(),
        latency_metrics_enabled=latency_metrics_enabled,
    )


# --- Metric correctness (pure functions) ---


class TestPrecisionAtK:
    def test_all_relevant_yields_perfect_precision(self) -> None:
        expected = {uuid4() for _ in range(3)}
        retrieved = list(expected)

        assert _precision_at_k(retrieved, expected, 3) == 1.0

    def test_none_relevant_yields_zero(self) -> None:
        retrieved = [uuid4(), uuid4()]
        expected = {uuid4()}

        assert _precision_at_k(retrieved, expected, 2) == 0.0

    def test_partial_overlap(self) -> None:
        relevant = uuid4()
        retrieved = [relevant, uuid4(), uuid4()]
        expected = {relevant}

        assert _precision_at_k(retrieved, expected, 3) == pytest.approx(1 / 3)

    def test_uses_actual_returned_count_not_k_as_denominator(self) -> None:
        relevant = uuid4()
        retrieved = [relevant]
        expected = {relevant}

        # Only 1 result was returned even though k=10 was requested.
        assert _precision_at_k(retrieved, expected, 10) == 1.0

    def test_empty_expected_yields_zero(self) -> None:
        assert _precision_at_k([uuid4()], set(), 5) == 0.0

    def test_empty_retrieved_yields_zero(self) -> None:
        assert _precision_at_k([], {uuid4()}, 5) == 0.0


class TestRecallAtK:
    def test_finds_all_relevant(self) -> None:
        expected = {uuid4() for _ in range(2)}
        retrieved = [*expected, uuid4()]

        assert _recall_at_k(retrieved, expected, 10) == 1.0

    def test_finds_none(self) -> None:
        assert _recall_at_k([uuid4()], {uuid4()}, 5) == 0.0

    def test_partial_recall(self) -> None:
        found, missing = uuid4(), uuid4()
        retrieved = [found]
        expected = {found, missing}

        assert _recall_at_k(retrieved, expected, 5) == pytest.approx(0.5)

    def test_empty_expected_yields_zero(self) -> None:
        assert _recall_at_k([uuid4()], set(), 5) == 0.0

    def test_respects_the_k_cutoff(self) -> None:
        relevant = uuid4()
        retrieved = [uuid4(), uuid4(), relevant]
        expected = {relevant}

        assert _recall_at_k(retrieved, expected, 2) == 0.0
        assert _recall_at_k(retrieved, expected, 3) == 1.0


class TestHitRateAtK:
    def test_a_hit_within_k_yields_one(self) -> None:
        relevant = uuid4()
        assert _hit_rate_at_k([uuid4(), relevant], {relevant}, 2) == 1.0

    def test_no_hit_yields_zero(self) -> None:
        assert _hit_rate_at_k([uuid4()], {uuid4()}, 5) == 0.0

    def test_empty_expected_yields_zero(self) -> None:
        assert _hit_rate_at_k([uuid4()], set(), 5) == 0.0


class TestReciprocalRank:
    def test_first_result_relevant_yields_one(self) -> None:
        relevant = uuid4()
        assert _reciprocal_rank([relevant, uuid4()], {relevant}) == 1.0

    def test_second_result_relevant_yields_one_half(self) -> None:
        relevant = uuid4()
        assert _reciprocal_rank([uuid4(), relevant], {relevant}) == pytest.approx(0.5)

    def test_no_relevant_result_yields_zero(self) -> None:
        assert _reciprocal_rank([uuid4()], {uuid4()}) == 0.0

    def test_empty_expected_yields_zero(self) -> None:
        assert _reciprocal_rank([uuid4()], set()) == 0.0


class TestNdcgAtK:
    def test_perfect_ranking_yields_one(self) -> None:
        expected = {uuid4(), uuid4()}
        retrieved = list(expected)

        assert _ndcg_at_k(retrieved, expected, 2) == pytest.approx(1.0)

    def test_no_relevant_result_yields_zero(self) -> None:
        assert _ndcg_at_k([uuid4()], {uuid4()}, 5) == 0.0

    def test_a_later_rank_scores_lower_than_an_earlier_one(self) -> None:
        relevant = uuid4()
        early = _ndcg_at_k([relevant, uuid4()], {relevant}, 2)
        late = _ndcg_at_k([uuid4(), relevant], {relevant}, 2)

        assert early > late

    def test_empty_expected_yields_zero(self) -> None:
        assert _ndcg_at_k([uuid4()], set(), 5) == 0.0

    def test_is_never_above_one(self) -> None:
        expected = {uuid4() for _ in range(5)}
        retrieved = list(expected) + [uuid4() for _ in range(10)]

        assert _ndcg_at_k(retrieved, expected, 10) <= 1.0


# --- Orchestration ---


class TestRetrievalDispatch:
    async def test_a_retrieval_query_uses_hybrid_search(self) -> None:
        product_id = uuid4()
        hybrid_search_service = _FakeHybridSearchService(results=[_hybrid_result(product_id)])
        evaluator = _evaluator(hybrid_search_service=hybrid_search_service)
        query = EvaluationQuery(
            query_id="q1",
            text="red shoes",
            ground_truth=GroundTruth(expected_products=[product_id]),
        )

        report = await evaluator.evaluate([query])

        assert report.query_results[0].retrieved_products == [product_id]
        assert hybrid_search_service.calls[0]["text"] == "red shoes"

    async def test_an_image_only_retrieval_query_fails_as_its_own_error(self) -> None:
        # image_path alone satisfies EvaluationQuery's own validation
        # (image-query evaluation is "future-ready" at the domain-model
        # level) — but RetrievalEvaluator doesn't dispatch it yet, so it
        # fails as this query's own error, not a crash.
        evaluator = _evaluator()
        query = EvaluationQuery(
            query_id="q1",
            image_path=Path("/some/path.jpg"),
            ground_truth=GroundTruth(),
        )

        report = await evaluator.evaluate([query])

        assert report.query_results[0].error is not None
        assert report.failure_count == 1


class TestRecommendationDispatch:
    async def test_a_recommendation_query_uses_the_recommendation_engine(self) -> None:
        target_id, recommended_id = uuid4(), uuid4()
        recommendation_engine_service = _FakeRecommendationEngineService(
            result=RecommendationResult(
                recommendations=[_recommendation_candidate(recommended_id)],
                processing_time=0.0,
                recommendation_type=RecommendationType.SIMILAR,
            )
        )
        evaluator = _evaluator(recommendation_engine_service=recommendation_engine_service)
        query = EvaluationQuery(
            query_id="q1",
            task_type=EvaluationTaskType.RECOMMENDATION,
            product_id=target_id,
            ground_truth=GroundTruth(expected_products=[recommended_id]),
        )

        report = await evaluator.evaluate([query])

        assert report.query_results[0].retrieved_products == [recommended_id]
        assert recommendation_engine_service.calls[0]["product_id"] == target_id


class TestDuplicateDispatch:
    async def test_a_duplicate_query_uses_duplicate_detection(self) -> None:
        target_id, matched_id = uuid4(), uuid4()
        duplicate_detection_service = _FakeDuplicateDetectionService(
            decision=DuplicateDecision(
                is_duplicate=True,
                confidence=0.95,
                reason="matched",
                matched_product=matched_id,
                top_candidates=[_duplicate_candidate(matched_id)],
            )
        )
        evaluator = _evaluator(duplicate_detection_service=duplicate_detection_service)
        query = EvaluationQuery(
            query_id="q1",
            task_type=EvaluationTaskType.DUPLICATE,
            product_id=target_id,
            ground_truth=GroundTruth(expected_products=[matched_id], is_duplicate=True),
        )

        report = await evaluator.evaluate([query])

        assert report.query_results[0].retrieved_products == [matched_id]
        assert duplicate_detection_service.calls[0]["product_id"] == target_id


class TestPerQueryFailureIsolation:
    async def test_one_querys_failure_does_not_abort_the_run(self) -> None:
        good_id, expected_id = uuid4(), uuid4()
        duplicate_detection_service = _FakeDuplicateDetectionService(
            error=ResourceNotFoundException("not found", resource="product")
        )
        hybrid_search_service = _FakeHybridSearchService(results=[_hybrid_result(expected_id)])
        evaluator = _evaluator(
            hybrid_search_service=hybrid_search_service,
            duplicate_detection_service=duplicate_detection_service,
        )
        good_query = EvaluationQuery(
            query_id="good", text="shoes", ground_truth=GroundTruth(expected_products=[expected_id])
        )
        bad_query = EvaluationQuery(
            query_id="bad",
            task_type=EvaluationTaskType.DUPLICATE,
            product_id=good_id,
            ground_truth=GroundTruth(),
        )

        report = await evaluator.evaluate([good_query, bad_query])

        assert report.failure_count == 1
        assert report.dataset_size == 2
        results_by_id = {result.query_id: result for result in report.query_results}
        assert results_by_id["good"].error is None
        assert results_by_id["bad"].error is not None

    async def test_a_failed_query_is_excluded_from_aggregate_metrics(self) -> None:
        expected_id = uuid4()
        hybrid_search_service = _FakeHybridSearchService(results=[_hybrid_result(expected_id)])
        recommendation_engine_service = _FakeRecommendationEngineService(
            error=ResourceNotFoundException("not found", resource="product")
        )
        evaluator = _evaluator(
            hybrid_search_service=hybrid_search_service,
            recommendation_engine_service=recommendation_engine_service,
        )
        good_query = EvaluationQuery(
            query_id="good", text="shoes", ground_truth=GroundTruth(expected_products=[expected_id])
        )
        bad_recommendation_query = EvaluationQuery(
            query_id="bad",
            task_type=EvaluationTaskType.RECOMMENDATION,
            product_id=uuid4(),
            ground_truth=GroundTruth(expected_products=[uuid4()]),
        )

        report = await evaluator.evaluate([good_query, bad_recommendation_query])

        assert "recommendation" not in report.overall_metrics
        assert report.overall_metrics["retrieval"].query_count == 1


class TestAggregation:
    async def test_metrics_are_grouped_by_task_type(self) -> None:
        retrieval_hit = uuid4()
        recommendation_hit = uuid4()
        hybrid_search_service = _FakeHybridSearchService(results=[_hybrid_result(retrieval_hit)])
        recommendation_engine_service = _FakeRecommendationEngineService(
            result=RecommendationResult(
                recommendations=[_recommendation_candidate(recommendation_hit)],
                processing_time=0.0,
                recommendation_type=RecommendationType.SIMILAR,
            )
        )
        evaluator = _evaluator(
            hybrid_search_service=hybrid_search_service,
            recommendation_engine_service=recommendation_engine_service,
        )
        retrieval_query = EvaluationQuery(
            query_id="r1", text="shoes", ground_truth=GroundTruth(expected_products=[retrieval_hit])
        )
        recommendation_query = EvaluationQuery(
            query_id="c1",
            task_type=EvaluationTaskType.RECOMMENDATION,
            product_id=uuid4(),
            ground_truth=GroundTruth(expected_products=[recommendation_hit]),
        )

        report = await evaluator.evaluate([retrieval_query, recommendation_query])

        assert report.overall_metrics["retrieval"].mrr == 1.0
        assert report.overall_metrics["recommendation"].mrr == 1.0
        assert report.overall_metrics["retrieval"].query_count == 1
        assert report.overall_metrics["recommendation"].query_count == 1

    async def test_uses_the_configured_dataset_loader_when_no_queries_are_given(self) -> None:
        product_id = uuid4()
        dataset_loader = _FakeDatasetLoader(
            queries=[
                EvaluationQuery(
                    query_id="q1",
                    text="shoes",
                    ground_truth=GroundTruth(expected_products=[product_id]),
                )
            ]
        )
        evaluator = _evaluator(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(product_id)]),
            dataset_loader=dataset_loader,
        )

        report = await evaluator.evaluate()

        assert report.dataset_size == 1

    async def test_dataset_loading_failure_propagates(self) -> None:
        evaluator = _evaluator(
            dataset_loader=_FakeDatasetLoader(error=EvaluationException("bad dataset"))
        )

        with pytest.raises(EvaluationException):
            await evaluator.evaluate()

    async def test_processing_time_is_recorded(self) -> None:
        evaluator = _evaluator()

        report = await evaluator.evaluate([])

        assert report.total_duration_seconds >= 0.0

    async def test_wraps_an_unexpected_aggregation_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import app.services.evaluation.retrieval_evaluator as retrieval_evaluator_module

        def _broken_aggregate(*args: object, **kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(retrieval_evaluator_module, "_aggregate", _broken_aggregate)
        evaluator = _evaluator()

        with pytest.raises(EvaluationException):
            await evaluator.evaluate([])


class TestEmptyDataset:
    async def test_an_empty_dataset_yields_an_empty_report(self) -> None:
        evaluator = _evaluator()

        report = await evaluator.evaluate([])

        assert report.dataset_size == 0
        assert report.query_results == []
        assert report.overall_metrics == {}
        assert report.failure_count == 0


class TestLatencyMetrics:
    async def test_latency_is_recorded_when_enabled(self) -> None:
        product_id = uuid4()
        evaluator = _evaluator(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(product_id)]),
            latency_metrics_enabled=True,
        )
        query = EvaluationQuery(
            query_id="q1", text="shoes", ground_truth=GroundTruth(expected_products=[product_id])
        )

        report = await evaluator.evaluate([query])

        assert report.query_results[0].latency_seconds >= 0.0

    async def test_latency_is_zero_when_disabled(self) -> None:
        product_id = uuid4()
        evaluator = _evaluator(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(product_id)]),
            latency_metrics_enabled=False,
        )
        query = EvaluationQuery(
            query_id="q1", text="shoes", ground_truth=GroundTruth(expected_products=[product_id])
        )

        report = await evaluator.evaluate([query])

        assert report.query_results[0].latency_seconds == 0.0


class TestConcurrency:
    async def test_concurrent_evaluate_calls_each_return_their_own_result(self) -> None:
        texts = [f"query-{i}" for i in range(8)]
        expected_by_text = {text: uuid4() for text in texts}
        results_by_text = {
            text: _hybrid_result(product_id) for text, product_id in expected_by_text.items()
        }
        evaluator = _evaluator(
            hybrid_search_service=_RoutingFakeHybridSearchService(results_by_text)
        )
        queries = [
            EvaluationQuery(
                query_id=text,
                text=text,
                ground_truth=GroundTruth(expected_products=[expected_by_text[text]]),
            )
            for text in texts
        ]

        reports = await asyncio.gather(*(evaluator.evaluate([query]) for query in queries))

        for text, report in zip(texts, reports, strict=True):
            assert report.query_results[0].query_id == text
            assert report.query_results[0].retrieved_products == [expected_by_text[text]]
