"""Unit tests for `DuplicateDetectionService`.

Composes fake `HybridSearchService`/`SimilarityScorer` doubles (not the
real retrieval/scoring pipelines — those are already covered by
`test_hybrid_search_service.py`/`test_similarity_scorer.py`) so the
ranking/thresholding/decision logic can be tested against precisely
controlled inputs.
"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.exceptions.errors import DuplicateDetectionException, ResourceNotFoundException
from app.models.duplicate_decision import DuplicateDecision
from app.models.duplicate_result import DuplicateResult
from app.models.product_attributes import ProductAttributes
from app.models.rerank_reason import RerankReason
from app.models.rerank_result import RerankResult
from app.models.reranked_candidate import RerankedCandidate
from app.models.search import HybridSearchResult, ProductFilters, SearchModality, StoredPoint
from app.models.similarity_signal import SimilaritySignal
from app.schemas.product import ProductImage
from app.services.base_reranker import BaseReranker
from app.services.duplicate.duplicate_detection_service import DuplicateDetectionService
from app.services.duplicate.similarity_scorer import SimilarityScorer
from app.services.vectorstore.base import BaseVectorStore, VectorCollection, VectorRecord
from app.services.vectorstore.hybrid_search_service import HybridSearchService


class _FakeReranker(BaseReranker):
    """Reverses candidate order and stamps a fixed `rerank_score` — enough to prove
    the reranked order/score actually reaches `SimilarityScorer` via `text_score`."""

    def __init__(self, *, rerank_score: float = 0.9) -> None:
        self._rerank_score = rerank_score
        self.calls: list[dict[str, object]] = []

    async def rerank(
        self, query: str, candidates: list[HybridSearchResult], *, top_k: int | None = None
    ) -> RerankResult:
        self.calls.append({"query": query, "candidates": candidates, "top_k": top_k})
        reversed_candidates = list(reversed(candidates))
        return RerankResult(
            query=query,
            candidates=[
                RerankedCandidate(
                    product_id=candidate.product_id,
                    original_score=candidate.score,
                    rerank_score=self._rerank_score,
                    final_rank=rank,
                    metadata=candidate.metadata,
                    reason=RerankReason(original_rank=rank, final_rank=rank, rank_delta=0),
                )
                for rank, candidate in enumerate(reversed_candidates, start=1)
            ],
            original_count=len(candidates),
        )


class _TextScoreEchoingSimilarityScorer(SimilarityScorer):
    """Reflects `candidate.text_score` directly into `overall_similarity`, so a test
    can prove whether reranking's `text_score` substitution actually reached scoring."""

    def score(
        self,
        *,
        name: str,
        brand: str | None,
        category: str | None,
        attributes: ProductAttributes,
        candidate: HybridSearchResult,
    ) -> DuplicateResult:
        return DuplicateResult(
            product_id=candidate.product_id,
            signals=[
                SimilaritySignal(
                    name="text",
                    score=candidate.text_score,
                    weight=1.0,
                    contribution=candidate.text_score,
                )
            ],
            overall_similarity=candidate.text_score,
        )


class _FakeHybridSearchService(HybridSearchService):
    def __init__(self, *, results: list[HybridSearchResult] | None = None) -> None:
        self._results = results if results is not None else []
        self.calls: list[tuple[object, object, object]] = []
        self.by_id_calls: list[dict[str, object]] = []

    async def search(
        self,
        *,
        image: ProductImage | None = None,
        text: str | None = None,
        top_k: int | None = None,
        filters: ProductFilters | None = None,
        reranking_enabled: bool | None = None,
    ) -> list[HybridSearchResult]:
        self.calls.append((image, text, top_k))
        return self._results

    async def search_by_product_id(
        self,
        product_id: UUID,
        *,
        top_k: int | None = None,
        filters: ProductFilters | None = None,
        modality: SearchModality | None = None,
    ) -> list[HybridSearchResult]:
        self.by_id_calls.append({"product_id": product_id, "top_k": top_k})
        return self._results


class _FakeVectorStore(BaseVectorStore):
    def __init__(self, *, stored_point: StoredPoint | None = None) -> None:
        self._stored_point = stored_point

    async def upsert(self, collection: VectorCollection, records: list[VectorRecord]) -> None:
        return None

    async def search(
        self,
        collection: VectorCollection,
        query_vector: list[float],
        *,
        top_k: int,
        filters: ProductFilters | None = None,
    ) -> list:  # type: ignore[type-arg]
        return []

    async def delete(self, collection: VectorCollection, product_ids: list) -> None:  # type: ignore[type-arg]
        return None

    async def exists(self, collection: VectorCollection, product_id: UUID) -> bool:
        return self._stored_point is not None

    async def retrieve(self, collection: VectorCollection, product_id: UUID) -> StoredPoint | None:
        return self._stored_point

    async def health(self) -> bool:
        return True


class _FakeSimilarityScorer(SimilarityScorer):
    def __init__(self, *, overall_similarity_by_product: dict[UUID, float]) -> None:
        self._overall_similarity_by_product = overall_similarity_by_product

    def score(
        self,
        *,
        name: str,
        brand: str | None,
        category: str | None,
        attributes: ProductAttributes,
        candidate: HybridSearchResult,
    ) -> DuplicateResult:
        overall = self._overall_similarity_by_product[candidate.product_id]
        return DuplicateResult(
            product_id=candidate.product_id,
            signals=[
                SimilaritySignal(name="image", score=overall, weight=1.0, contribution=overall)
            ],
            overall_similarity=overall,
        )


def _hybrid_result(product_id: UUID) -> HybridSearchResult:
    return HybridSearchResult(
        product_id=product_id,
        score=0.5,
        metadata={},
        matched_modalities=[SearchModality.IMAGE],
    )


def _image() -> ProductImage:
    return ProductImage(
        original_filename="photo.jpg",
        stored_filename="stored.jpg",
        content_type="image/jpeg",
        size_bytes=10,
        uploaded_at=datetime.now(UTC),
    )


async def _detect(service: DuplicateDetectionService, *, name: str = "Widget") -> DuplicateDecision:
    return await service.detect(
        name=name,
        brand=None,
        category=None,
        description=None,
        attributes=ProductAttributes(),
        image=_image(),
    )


class TestNoCandidates:
    async def test_no_candidates_yields_a_non_duplicate_decision(self, tmp_path: Path) -> None:
        service = DuplicateDetectionService(
            hybrid_search_service=_FakeHybridSearchService(results=[]),
            similarity_scorer=_FakeSimilarityScorer(overall_similarity_by_product={}),
        )

        decision = await _detect(service)

        assert decision.is_duplicate is False
        assert decision.confidence == 0.0
        assert decision.matched_product is None
        assert decision.top_candidates == []


class TestThresholding:
    async def test_a_candidate_at_or_above_threshold_is_flagged_a_duplicate(self) -> None:
        product_id = uuid4()
        service = DuplicateDetectionService(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(product_id)]),
            similarity_scorer=_FakeSimilarityScorer(
                overall_similarity_by_product={product_id: 0.95}
            ),
            threshold=0.90,
        )

        decision = await _detect(service)

        assert decision.is_duplicate is True
        assert decision.confidence == 0.95
        assert decision.matched_product == product_id

    async def test_a_candidate_below_threshold_is_not_flagged(self) -> None:
        product_id = uuid4()
        service = DuplicateDetectionService(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(product_id)]),
            similarity_scorer=_FakeSimilarityScorer(
                overall_similarity_by_product={product_id: 0.5}
            ),
            threshold=0.90,
        )

        decision = await _detect(service)

        assert decision.is_duplicate is False
        assert decision.confidence == 0.5
        assert decision.matched_product is None

    async def test_a_candidate_exactly_at_threshold_is_flagged(self) -> None:
        product_id = uuid4()
        service = DuplicateDetectionService(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(product_id)]),
            similarity_scorer=_FakeSimilarityScorer(
                overall_similarity_by_product={product_id: 0.90}
            ),
            threshold=0.90,
        )

        decision = await _detect(service)

        assert decision.is_duplicate is True


class TestTopCandidates:
    async def test_top_candidates_are_ranked_by_descending_overall_similarity(self) -> None:
        low, mid, high = uuid4(), uuid4(), uuid4()
        service = DuplicateDetectionService(
            hybrid_search_service=_FakeHybridSearchService(
                results=[_hybrid_result(low), _hybrid_result(high), _hybrid_result(mid)]
            ),
            similarity_scorer=_FakeSimilarityScorer(
                overall_similarity_by_product={low: 0.2, mid: 0.5, high: 0.9}
            ),
            threshold=0.90,
        )

        decision = await _detect(service)

        assert [candidate.product_id for candidate in decision.top_candidates] == [
            high,
            mid,
            low,
        ]

    async def test_the_winning_candidates_signal_scores_populate_the_flattened_candidate(
        self,
    ) -> None:
        product_id = uuid4()
        service = DuplicateDetectionService(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(product_id)]),
            similarity_scorer=_FakeSimilarityScorer(
                overall_similarity_by_product={product_id: 0.95}
            ),
            threshold=0.90,
        )

        decision = await _detect(service)

        assert decision.top_candidates[0].image_similarity == 0.95
        assert decision.top_candidates[0].overall_similarity == 0.95


class TestHybridSearchWiring:
    async def test_passes_top_k_and_a_built_text_query_to_hybrid_search(self) -> None:
        hybrid_search_service = _FakeHybridSearchService(results=[])
        service = DuplicateDetectionService(
            hybrid_search_service=hybrid_search_service,
            similarity_scorer=_FakeSimilarityScorer(overall_similarity_by_product={}),
            top_k=5,
        )

        await service.detect(
            name="Widget",
            brand="Nike",
            category="Shoes",
            description=None,
            attributes=ProductAttributes(),
            image=_image(),
        )

        assert len(hybrid_search_service.calls) == 1
        _, text, top_k = hybrid_search_service.calls[0]
        assert text == "Widget. Nike. Shoes"
        assert top_k == 5


class TestPerCallOverrides:
    async def test_a_per_call_top_k_overrides_the_configured_default(self) -> None:
        hybrid_search_service = _FakeHybridSearchService(results=[])
        service = DuplicateDetectionService(
            hybrid_search_service=hybrid_search_service,
            similarity_scorer=_FakeSimilarityScorer(overall_similarity_by_product={}),
            top_k=10,
        )

        await service.detect(
            name="Widget",
            brand=None,
            category=None,
            description=None,
            attributes=ProductAttributes(),
            image=_image(),
            top_k=3,
        )

        _, _, top_k = hybrid_search_service.calls[0]
        assert top_k == 3

    async def test_a_per_call_threshold_overrides_the_configured_default(self) -> None:
        product_id = uuid4()
        service = DuplicateDetectionService(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(product_id)]),
            similarity_scorer=_FakeSimilarityScorer(
                overall_similarity_by_product={product_id: 0.5}
            ),
            threshold=0.90,
        )

        decision = await service.detect(
            name="Widget",
            brand=None,
            category=None,
            description=None,
            attributes=ProductAttributes(),
            image=_image(),
            threshold=0.3,
        )

        assert decision.is_duplicate is True


class TestErrorWrapping:
    async def test_wraps_an_unexpected_scoring_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        product_id = uuid4()
        service = DuplicateDetectionService(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(product_id)]),
            similarity_scorer=_FakeSimilarityScorer(
                overall_similarity_by_product={product_id: 0.5}
            ),
        )

        def _broken_score(*args: object, **kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(service._similarity_scorer, "score", _broken_score)

        with pytest.raises(DuplicateDetectionException):
            await _detect(service)


class _RoutingFakeHybridSearchService(HybridSearchService):
    """Returns a different candidate set depending on the query text, so
    concurrent `.detect()` calls (each for a different product) can be
    verified to never see each other's candidates.
    """

    def __init__(self, results_by_text: dict[str, list[HybridSearchResult]]) -> None:
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
        return self._results_by_text[text]


class TestConcurrency:
    async def test_concurrent_detect_calls_each_return_their_own_decision(self) -> None:
        product_ids = {f"Widget-{i}": uuid4() for i in range(8)}
        results_by_text = {
            name: [_hybrid_result(product_id)] for name, product_id in product_ids.items()
        }
        service = DuplicateDetectionService(
            hybrid_search_service=_RoutingFakeHybridSearchService(results_by_text),
            similarity_scorer=_FakeSimilarityScorer(
                overall_similarity_by_product=dict.fromkeys(product_ids.values(), 0.95)
            ),
            threshold=0.90,
        )

        decisions = await asyncio.gather(
            *(
                service.detect(
                    name=name,
                    brand=None,
                    category=None,
                    description=None,
                    attributes=ProductAttributes(),
                    image=_image(),
                )
                for name in product_ids
            )
        )

        for name, decision in zip(product_ids, decisions, strict=True):
            assert decision.matched_product == product_ids[name]


class TestMalformedInput:
    async def test_unicode_and_very_long_text_does_not_crash_detection(self) -> None:
        product_id = uuid4()
        service = DuplicateDetectionService(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(product_id)]),
            similarity_scorer=_FakeSimilarityScorer(
                overall_similarity_by_product={product_id: 0.5}
            ),
        )

        decision = await service.detect(
            name="   \t\n  ",
            brand="",
            category=None,
            description="日本語 emoji 🚀🚀🚀 " + ("x" * 5000),
            attributes=ProductAttributes(),
            image=_image(),
        )

        assert isinstance(decision, DuplicateDecision)
        assert 0.0 <= decision.confidence <= 1.0


class TestMetrics:
    async def test_records_a_check_and_each_candidate_similarity(self) -> None:
        from prometheus_client import CollectorRegistry

        from app.metrics.metrics_registry import MetricsRegistry

        metrics = MetricsRegistry(registry=CollectorRegistry())
        a, b = uuid4(), uuid4()
        service = DuplicateDetectionService(
            hybrid_search_service=_FakeHybridSearchService(
                results=[_hybrid_result(a), _hybrid_result(b)]
            ),
            similarity_scorer=_FakeSimilarityScorer(overall_similarity_by_product={a: 0.5, b: 0.9}),
            metrics_registry=metrics,
        )

        await _detect(service)

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


class TestDetectByProductId:
    async def test_raises_resource_not_found_when_the_product_is_not_indexed(self) -> None:
        service = DuplicateDetectionService(
            hybrid_search_service=_FakeHybridSearchService(),
            vector_store=_FakeVectorStore(stored_point=None),
            similarity_scorer=_FakeSimilarityScorer(overall_similarity_by_product={}),
        )

        with pytest.raises(ResourceNotFoundException):
            await service.detect_by_product_id(uuid4())

    async def test_reuses_search_by_product_id_for_candidate_retrieval(self) -> None:
        target_id = uuid4()
        candidate_id = uuid4()
        hybrid_search_service = _FakeHybridSearchService(results=[_hybrid_result(candidate_id)])
        service = DuplicateDetectionService(
            hybrid_search_service=hybrid_search_service,
            vector_store=_FakeVectorStore(
                stored_point=StoredPoint(product_id=target_id, vector=[0.1], metadata={})
            ),
            similarity_scorer=_FakeSimilarityScorer(
                overall_similarity_by_product={candidate_id: 0.95}
            ),
            threshold=0.90,
        )

        decision = await service.detect_by_product_id(target_id)

        assert len(hybrid_search_service.by_id_calls) == 1
        assert hybrid_search_service.by_id_calls[0]["product_id"] == target_id
        assert decision.is_duplicate is True
        assert decision.matched_product == candidate_id

    async def test_uses_the_targets_own_stored_metadata_for_scoring(self) -> None:
        target_id = uuid4()
        candidate_id = uuid4()

        class _RecordingScorer(SimilarityScorer):
            def __init__(self) -> None:
                self.received: dict[str, object] = {}

            def score(self, *, name, brand, category, attributes, candidate) -> DuplicateResult:  # type: ignore[no-untyped-def]
                self.received = {
                    "name": name,
                    "brand": brand,
                    "category": category,
                    "attributes": attributes,
                }
                return DuplicateResult(product_id=candidate.product_id, overall_similarity=0.5)

        scorer = _RecordingScorer()
        service = DuplicateDetectionService(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(candidate_id)]),
            vector_store=_FakeVectorStore(
                stored_point=StoredPoint(
                    product_id=target_id,
                    vector=[0.1],
                    metadata={
                        "name": "Nike Widget",
                        "brand": "Nike",
                        "category": "men-tshirts",
                        "color": "Red",
                        "material": "Mesh",
                    },
                )
            ),
            similarity_scorer=scorer,
        )

        await service.detect_by_product_id(target_id)

        assert scorer.received["name"] == "Nike Widget"
        assert scorer.received["brand"] == "Nike"
        assert scorer.received["category"] == "men-tshirts"
        attributes = scorer.received["attributes"]
        assert isinstance(attributes, ProductAttributes)
        assert attributes.color == "Red"
        assert attributes.material == "Mesh"

    async def test_per_call_top_k_and_threshold_override_the_configured_defaults(self) -> None:
        target_id = uuid4()
        candidate_id = uuid4()
        hybrid_search_service = _FakeHybridSearchService(results=[_hybrid_result(candidate_id)])
        service = DuplicateDetectionService(
            hybrid_search_service=hybrid_search_service,
            vector_store=_FakeVectorStore(
                stored_point=StoredPoint(product_id=target_id, vector=[0.1], metadata={})
            ),
            similarity_scorer=_FakeSimilarityScorer(
                overall_similarity_by_product={candidate_id: 0.5}
            ),
            threshold=0.90,
            top_k=10,
        )

        decision = await service.detect_by_product_id(target_id, top_k=3, threshold=0.3)

        assert hybrid_search_service.by_id_calls[0]["top_k"] == 3
        assert decision.is_duplicate is True

    async def test_wraps_an_unexpected_scoring_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target_id = uuid4()
        candidate_id = uuid4()
        service = DuplicateDetectionService(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(candidate_id)]),
            vector_store=_FakeVectorStore(
                stored_point=StoredPoint(product_id=target_id, vector=[0.1], metadata={})
            ),
            similarity_scorer=_FakeSimilarityScorer(
                overall_similarity_by_product={candidate_id: 0.5}
            ),
        )

        def _broken_score(*args: object, **kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(service._similarity_scorer, "score", _broken_score)

        with pytest.raises(DuplicateDetectionException):
            await service.detect_by_product_id(target_id)


class TestReranking:
    async def test_disabled_by_default(self) -> None:
        candidate_id = uuid4()
        reranker = _FakeReranker()
        service = DuplicateDetectionService(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(candidate_id)]),
            similarity_scorer=_FakeSimilarityScorer(
                overall_similarity_by_product={candidate_id: 0.5}
            ),
            reranker=reranker,
        )

        await _detect(service)

        assert reranker.calls == []

    async def test_reranked_text_score_flows_into_scoring(self) -> None:
        first, second = uuid4(), uuid4()
        service = DuplicateDetectionService(
            hybrid_search_service=_FakeHybridSearchService(
                results=[_hybrid_result(first), _hybrid_result(second)]
            ),
            similarity_scorer=_TextScoreEchoingSimilarityScorer(),
            reranker=_FakeReranker(rerank_score=0.87),
            reranking_enabled=True,
            threshold=0.5,
        )

        decision = await _detect(service)

        # `_FakeReranker` reverses order, so `second` (originally last)
        # becomes the top-ranked, highest-`text_score` candidate.
        assert decision.matched_product == second
        assert decision.confidence == pytest.approx(0.87)

    async def test_does_not_double_rerank_via_hybrid_search_service(self) -> None:
        # `HybridSearchService.search` is called with `reranking_enabled=False`
        # explicitly — this class applies its own single rerank pass.
        candidate_id = uuid4()

        class _RecordingHybridSearchService(HybridSearchService):
            def __init__(self) -> None:
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
                self.calls.append({"reranking_enabled": reranking_enabled})
                return [_hybrid_result(candidate_id)]

        hybrid_search_service = _RecordingHybridSearchService()
        service = DuplicateDetectionService(
            hybrid_search_service=hybrid_search_service,
            similarity_scorer=_FakeSimilarityScorer(
                overall_similarity_by_product={candidate_id: 0.5}
            ),
            reranker=_FakeReranker(),
            reranking_enabled=True,
        )

        await _detect(service)

        assert hybrid_search_service.calls[0]["reranking_enabled"] is False

    async def test_no_candidates_skips_reranking(self) -> None:
        reranker = _FakeReranker()
        service = DuplicateDetectionService(
            hybrid_search_service=_FakeHybridSearchService(results=[]),
            similarity_scorer=_FakeSimilarityScorer(overall_similarity_by_product={}),
            reranker=reranker,
            reranking_enabled=True,
        )

        decision = await _detect(service)

        assert decision.is_duplicate is False
        assert reranker.calls == []

    async def test_per_call_override_disables_reranking(self) -> None:
        candidate_id = uuid4()
        reranker = _FakeReranker()
        service = DuplicateDetectionService(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(candidate_id)]),
            similarity_scorer=_FakeSimilarityScorer(
                overall_similarity_by_product={candidate_id: 0.5}
            ),
            reranker=reranker,
            reranking_enabled=True,
        )

        await service.detect(
            name="Widget",
            brand=None,
            category=None,
            description=None,
            attributes=ProductAttributes(),
            image=_image(),
            reranking_enabled=False,
        )

        assert reranker.calls == []

    async def test_reranking_by_product_id_uses_the_targets_stored_metadata(self) -> None:
        target_id = uuid4()
        candidate_id = uuid4()
        reranker = _FakeReranker()
        service = DuplicateDetectionService(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(candidate_id)]),
            vector_store=_FakeVectorStore(
                stored_point=StoredPoint(
                    product_id=target_id,
                    vector=[0.1],
                    metadata={"name": "Red Shoe", "brand": "Nike"},
                )
            ),
            similarity_scorer=_FakeSimilarityScorer(
                overall_similarity_by_product={candidate_id: 0.5}
            ),
            reranker=reranker,
            reranking_enabled=True,
        )

        await service.detect_by_product_id(target_id)

        assert reranker.calls[0]["query"] == "Red Shoe. Nike"
