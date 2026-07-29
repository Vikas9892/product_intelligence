"""Unit tests for `RerankerService`.

Composes a fake `CrossEncoderService` (already covered by its own test
module) so sorting/pooling/truncation/reason-generation logic can be
tested against precisely controlled scores, without any real model
inference.
"""

import asyncio
from uuid import UUID, uuid4

import pytest
from prometheus_client import CollectorRegistry

from app.exceptions.errors import RerankException
from app.metrics.metrics_registry import MetricsRegistry
from app.models.search import HybridSearchResult, SearchModality
from app.services.cross_encoder_service import CrossEncoderService
from app.services.reranker_service import RerankerService


class _FakeCrossEncoderService(CrossEncoderService):
    """Scores each pair by looking up its document text in a fixed table."""

    def __init__(
        self, *, scores_by_document: dict[str, float] | None = None, error: Exception | None = None
    ) -> None:
        self._scores_by_document = scores_by_document if scores_by_document is not None else {}
        self._error = error
        self.calls: list[list[tuple[str, str]]] = []

    async def score_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.calls.append(pairs)
        if self._error is not None:
            raise self._error
        return [self._scores_by_document.get(document, 0.0) for _query, document in pairs]


def _candidate(
    product_id: UUID | None = None, *, score: float = 0.5, **metadata: object
) -> HybridSearchResult:
    return HybridSearchResult(
        product_id=product_id if product_id is not None else uuid4(),
        score=score,
        metadata=metadata,
        matched_modalities=[SearchModality.TEXT],
    )


class TestRerankingCorrectness:
    async def test_sorts_candidates_by_descending_rerank_score(self) -> None:
        low_id, high_id = uuid4(), uuid4()
        candidates = [
            _candidate(low_id, name="Low match"),
            _candidate(high_id, name="High match"),
        ]
        cross_encoder = _FakeCrossEncoderService(
            scores_by_document={"Low match": -2.0, "High match": 5.0}
        )
        service = RerankerService(cross_encoder_service=cross_encoder)

        result = await service.rerank("query", candidates)

        assert [c.product_id for c in result.candidates] == [high_id, low_id]
        assert result.candidates[0].final_rank == 1
        assert result.candidates[1].final_rank == 2

    async def test_rerank_score_is_normalized_into_zero_one(self) -> None:
        candidate = _candidate(name="Widget")
        cross_encoder = _FakeCrossEncoderService(scores_by_document={"Widget": 8.0})
        service = RerankerService(cross_encoder_service=cross_encoder)

        result = await service.rerank("query", [candidate])

        assert 0.0 < result.candidates[0].rerank_score < 1.0

    async def test_preserves_original_score_and_metadata(self) -> None:
        candidate = _candidate(score=0.42, name="Widget", brand="Nike")
        cross_encoder = _FakeCrossEncoderService(scores_by_document={"Widget. Nike": 1.0})
        service = RerankerService(cross_encoder_service=cross_encoder)

        result = await service.rerank("query", [candidate])

        assert result.candidates[0].original_score == 0.42
        assert result.candidates[0].metadata == {"name": "Widget", "brand": "Nike"}

    async def test_rank_delta_reflects_movement(self) -> None:
        moved_up, moved_down = uuid4(), uuid4()
        candidates = [
            _candidate(moved_down, name="Was first"),
            _candidate(moved_up, name="Was second"),
        ]
        cross_encoder = _FakeCrossEncoderService(
            scores_by_document={"Was first": -1.0, "Was second": 1.0}
        )
        service = RerankerService(cross_encoder_service=cross_encoder)

        result = await service.rerank("query", candidates)

        by_id = {c.product_id: c for c in result.candidates}
        assert by_id[moved_up].reason.original_rank == 2
        assert by_id[moved_up].reason.final_rank == 1
        assert by_id[moved_up].reason.rank_delta == 1
        assert by_id[moved_down].reason.rank_delta == -1

    async def test_truncates_to_top_k(self) -> None:
        candidates = [_candidate(name=f"item-{i}") for i in range(5)]
        service = RerankerService(cross_encoder_service=_FakeCrossEncoderService())

        result = await service.rerank("query", candidates, top_k=2)

        assert len(result.candidates) == 2

    async def test_pools_only_the_configured_top_n_before_scoring(self) -> None:
        candidates = [_candidate(name=f"item-{i}") for i in range(5)]
        cross_encoder = _FakeCrossEncoderService()
        service = RerankerService(cross_encoder_service=cross_encoder, top_n=3)

        result = await service.rerank("query", candidates)

        assert len(cross_encoder.calls[0]) == 3
        assert result.original_count == 3
        assert len(result.candidates) == 3


class TestEmptyCandidates:
    async def test_returns_an_empty_result_without_calling_the_cross_encoder(self) -> None:
        cross_encoder = _FakeCrossEncoderService()
        service = RerankerService(cross_encoder_service=cross_encoder)

        result = await service.rerank("query", [])

        assert result.candidates == []
        assert result.query == "query"
        assert cross_encoder.calls == []


class TestMalformedMetadata:
    async def test_a_candidate_with_no_metadata_falls_back_to_its_product_id(self) -> None:
        product_id = uuid4()
        candidate = HybridSearchResult(
            product_id=product_id, score=0.5, metadata={}, matched_modalities=[SearchModality.TEXT]
        )
        cross_encoder = _FakeCrossEncoderService(scores_by_document={str(product_id): 1.0})
        service = RerankerService(cross_encoder_service=cross_encoder)

        result = await service.rerank("query", [candidate])

        assert result.candidates[0].product_id == product_id

    async def test_non_string_metadata_values_do_not_crash_reranking(self) -> None:
        candidate = _candidate(name=123, brand=["Nike"], description={"nested": True})
        service = RerankerService(cross_encoder_service=_FakeCrossEncoderService())

        result = await service.rerank("query", [candidate])

        assert len(result.candidates) == 1


class TestErrorHandling:
    async def test_wraps_a_cross_encoder_failure(self) -> None:
        cross_encoder = _FakeCrossEncoderService(error=RerankException("boom"))
        service = RerankerService(cross_encoder_service=cross_encoder)

        with pytest.raises(RerankException):
            await service.rerank("query", [_candidate(name="Widget")])

    async def test_wraps_an_unexpected_failure(self) -> None:
        cross_encoder = _FakeCrossEncoderService(error=RuntimeError("boom"))
        service = RerankerService(cross_encoder_service=cross_encoder)

        with pytest.raises(RerankException):
            await service.rerank("query", [_candidate(name="Widget")])


class TestMetrics:
    async def test_records_rerank_latency_and_success(self) -> None:
        metrics = MetricsRegistry(registry=CollectorRegistry())
        cross_encoder = _FakeCrossEncoderService(scores_by_document={"Widget": 1.0})
        service = RerankerService(cross_encoder_service=cross_encoder, metrics_registry=metrics)

        await service.rerank("query", [_candidate(name="Widget")])

        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_rerank_inference_total", {"status": "success"}
            )
            == 1.0
        )

    async def test_records_failure_when_the_cross_encoder_raises(self) -> None:
        metrics = MetricsRegistry(registry=CollectorRegistry())
        cross_encoder = _FakeCrossEncoderService(error=RuntimeError("boom"))
        service = RerankerService(cross_encoder_service=cross_encoder, metrics_registry=metrics)

        with pytest.raises(RerankException):
            await service.rerank("query", [_candidate(name="Widget")])

        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_rerank_inference_total", {"status": "failure"}
            )
            == 1.0
        )


class TestConcurrency:
    async def test_concurrent_rerank_calls_each_return_their_own_result(self) -> None:
        queries = [f"query-{i}" for i in range(8)]
        top_ids = {query: uuid4() for query in queries}
        cross_encoder = _FakeCrossEncoderService(
            scores_by_document={str(top_ids[query]): 5.0 for query in queries}
        )
        service = RerankerService(cross_encoder_service=cross_encoder)

        async def _run(query: str) -> UUID:
            candidate = HybridSearchResult(
                product_id=top_ids[query],
                score=0.1,
                metadata={},
                matched_modalities=[SearchModality.TEXT],
            )
            other = _candidate(name="other", score=0.1)
            result = await service.rerank(query, [other, candidate])
            return result.candidates[0].product_id

        results = await asyncio.gather(*(_run(query) for query in queries))

        for query, product_id in zip(queries, results, strict=True):
            assert product_id == top_ids[query]
