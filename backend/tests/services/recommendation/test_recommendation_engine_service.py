"""Unit tests for `RecommendationEngineService`.

Composes fake `HybridSearchService`/`BaseVectorStore`/`RecommendationScorer`
doubles (each already covered by their own test modules) so the
retrieval/ranking/diversity/error-wrapping logic can be tested against
precisely controlled inputs.
"""

import asyncio
from uuid import UUID, uuid4

import pytest

from app.exceptions.errors import RecommendationException, ResourceNotFoundException
from app.models.recommendation_candidate import RecommendationCandidate
from app.models.recommendation_reason import RecommendationReason
from app.models.recommendation_type import RecommendationType
from app.models.rerank_reason import RerankReason
from app.models.rerank_result import RerankResult
from app.models.reranked_candidate import RerankedCandidate
from app.models.search import HybridSearchResult, ProductFilters, SearchModality, StoredPoint
from app.services.base_reranker import BaseReranker
from app.services.recommendation.recommendation_engine_service import RecommendationEngineService
from app.services.recommendation.recommendation_scorer import RecommendationScorer
from app.services.vectorstore.base import BaseVectorStore, VectorCollection, VectorRecord
from app.services.vectorstore.hybrid_search_service import HybridSearchService


class _FakeReranker(BaseReranker):
    """Reverses candidate order and stamps a fixed `rerank_score` — enough to prove
    the reranked order/score actually reaches `RecommendationScorer`."""

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


class _EchoingRecommendationScorer(RecommendationScorer):
    """Reflects `candidate.score` directly into every score field, so a test can
    prove whether reranking's score substitution actually reached the scorer."""

    def score(self, *, target_metadata, candidate) -> RecommendationCandidate:  # type: ignore[no-untyped-def]
        return RecommendationCandidate(
            product_id=candidate.product_id,
            similarity_score=candidate.score,
            quality_score=candidate.score,
            final_score=candidate.score,
            reason=RecommendationReason(),
        )


class _FakeHybridSearchService(HybridSearchService):
    def __init__(self, *, results: list[HybridSearchResult] | None = None) -> None:
        self._results = results if results is not None else []
        self.calls: list[dict[str, object]] = []

    async def search_by_product_id(
        self,
        product_id: UUID,
        *,
        top_k: int | None = None,
        filters: ProductFilters | None = None,
        modality: SearchModality | None = None,
    ) -> list[HybridSearchResult]:
        self.calls.append({"product_id": product_id, "top_k": top_k, "modality": modality})
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

    async def exists(self, collection: VectorCollection, product_id) -> bool:  # type: ignore[no-untyped-def]
        return self._stored_point is not None

    async def retrieve(self, collection, product_id) -> StoredPoint | None:  # type: ignore[no-untyped-def]
        return self._stored_point

    async def health(self) -> bool:
        return True


class _FakeRecommendationScorer(RecommendationScorer):
    def __init__(self, *, final_score_by_product: dict[UUID, float]) -> None:
        self._final_score_by_product = final_score_by_product

    def score(self, *, target_metadata, candidate) -> RecommendationCandidate:  # type: ignore[no-untyped-def]
        final_score = self._final_score_by_product[candidate.product_id]
        return RecommendationCandidate(
            product_id=candidate.product_id,
            similarity_score=final_score,
            quality_score=final_score,
            final_score=final_score,
            reason=RecommendationReason(),
        )


class _FixedRecommendationScorer(RecommendationScorer):
    """Returns a pre-built `RecommendationCandidate` verbatim, for full control over
    `similarity_score`/`quality_score`/`reason` in explanation tests."""

    def __init__(self, *, candidates_by_product: dict[UUID, RecommendationCandidate]) -> None:
        self._candidates_by_product = candidates_by_product

    def score(self, *, target_metadata, candidate) -> RecommendationCandidate:  # type: ignore[no-untyped-def]
        return self._candidates_by_product[candidate.product_id]


def _hybrid_result(product_id: UUID, *, brand: str | None = None) -> HybridSearchResult:
    return HybridSearchResult(
        product_id=product_id,
        score=0.5,
        metadata={"brand": brand} if brand is not None else {},
        matched_modalities=[SearchModality.IMAGE],
    )


def _target_point(product_id: UUID | None = None) -> StoredPoint:
    return StoredPoint(
        product_id=product_id if product_id is not None else uuid4(), vector=[0.1, 0.2]
    )


class TestTargetNotFound:
    async def test_raises_resource_not_found_when_the_product_is_not_indexed(self) -> None:
        service = RecommendationEngineService(
            hybrid_search_service=_FakeHybridSearchService(),
            vector_store=_FakeVectorStore(stored_point=None),
            recommendation_scorer=_FakeRecommendationScorer(final_score_by_product={}),
        )

        with pytest.raises(ResourceNotFoundException):
            await service.recommend(product_id=uuid4())


class TestRanking:
    async def test_recommendations_are_sorted_by_descending_final_score(self) -> None:
        low, mid, high = uuid4(), uuid4(), uuid4()
        service = RecommendationEngineService(
            hybrid_search_service=_FakeHybridSearchService(
                results=[_hybrid_result(low), _hybrid_result(high), _hybrid_result(mid)]
            ),
            vector_store=_FakeVectorStore(stored_point=_target_point()),
            recommendation_scorer=_FakeRecommendationScorer(
                final_score_by_product={low: 0.2, mid: 0.5, high: 0.9}
            ),
            diversity_enabled=False,
        )

        result = await service.recommend(product_id=uuid4())

        assert [rec.product_id for rec in result.recommendations] == [high, mid, low]

    async def test_results_are_capped_at_the_requested_top_k(self) -> None:
        ids = [uuid4() for _ in range(5)]
        service = RecommendationEngineService(
            hybrid_search_service=_FakeHybridSearchService(
                results=[_hybrid_result(pid) for pid in ids]
            ),
            vector_store=_FakeVectorStore(stored_point=_target_point()),
            recommendation_scorer=_FakeRecommendationScorer(
                final_score_by_product=dict.fromkeys(ids, 0.5)
            ),
            diversity_enabled=False,
            top_k=2,
        )

        result = await service.recommend(product_id=uuid4())

        assert len(result.recommendations) == 2

    async def test_processing_time_is_recorded(self) -> None:
        service = RecommendationEngineService(
            hybrid_search_service=_FakeHybridSearchService(),
            vector_store=_FakeVectorStore(stored_point=_target_point()),
            recommendation_scorer=_FakeRecommendationScorer(final_score_by_product={}),
        )

        result = await service.recommend(product_id=uuid4())

        assert result.processing_time >= 0.0

    async def test_recommendation_type_is_carried_onto_the_result(self) -> None:
        service = RecommendationEngineService(
            hybrid_search_service=_FakeHybridSearchService(),
            vector_store=_FakeVectorStore(stored_point=_target_point()),
            recommendation_scorer=_FakeRecommendationScorer(final_score_by_product={}),
        )

        result = await service.recommend(
            product_id=uuid4(), recommendation_type=RecommendationType.RELATED
        )

        assert result.recommendation_type is RecommendationType.RELATED


class TestRecommendationTypeDispatch:
    async def test_similar_uses_hybrid_modality(self) -> None:
        hybrid_search_service = _FakeHybridSearchService()
        service = RecommendationEngineService(
            hybrid_search_service=hybrid_search_service,
            vector_store=_FakeVectorStore(stored_point=_target_point()),
            recommendation_scorer=_FakeRecommendationScorer(final_score_by_product={}),
        )

        await service.recommend(product_id=uuid4(), recommendation_type=RecommendationType.SIMILAR)

        assert hybrid_search_service.calls[0]["modality"] is None

    async def test_related_restricts_to_text_modality(self) -> None:
        hybrid_search_service = _FakeHybridSearchService()
        service = RecommendationEngineService(
            hybrid_search_service=hybrid_search_service,
            vector_store=_FakeVectorStore(stored_point=_target_point()),
            recommendation_scorer=_FakeRecommendationScorer(final_score_by_product={}),
        )

        await service.recommend(product_id=uuid4(), recommendation_type=RecommendationType.RELATED)

        assert hybrid_search_service.calls[0]["modality"] is SearchModality.TEXT


class TestOverfetch:
    async def test_diversity_enabled_overfetches_candidates(self) -> None:
        hybrid_search_service = _FakeHybridSearchService()
        service = RecommendationEngineService(
            hybrid_search_service=hybrid_search_service,
            vector_store=_FakeVectorStore(stored_point=_target_point()),
            recommendation_scorer=_FakeRecommendationScorer(final_score_by_product={}),
            diversity_enabled=True,
            top_k=5,
        )

        await service.recommend(product_id=uuid4())

        assert hybrid_search_service.calls[0]["top_k"] == 15

    async def test_diversity_disabled_requests_exactly_top_k(self) -> None:
        hybrid_search_service = _FakeHybridSearchService()
        service = RecommendationEngineService(
            hybrid_search_service=hybrid_search_service,
            vector_store=_FakeVectorStore(stored_point=_target_point()),
            recommendation_scorer=_FakeRecommendationScorer(final_score_by_product={}),
            diversity_enabled=False,
            top_k=5,
        )

        await service.recommend(product_id=uuid4())

        assert hybrid_search_service.calls[0]["top_k"] == 5


class TestDiversity:
    async def test_avoids_returning_the_same_brand_repeatedly(self) -> None:
        # Five Nike candidates score highest, then one each of three other
        # brands score lower — the phase's own worked example: without
        # diversity, top_k=4 would be all Nike; with it, every other
        # brand should appear before a second Nike does.
        nikes = [uuid4() for _ in range(5)]
        adidas, puma, asics = uuid4(), uuid4(), uuid4()
        results = [_hybrid_result(pid, brand="Nike") for pid in nikes] + [
            _hybrid_result(adidas, brand="Adidas"),
            _hybrid_result(puma, brand="Puma"),
            _hybrid_result(asics, brand="Asics"),
        ]
        scores = {pid: 0.9 - i * 0.01 for i, pid in enumerate(nikes)}
        scores.update({adidas: 0.5, puma: 0.4, asics: 0.3})
        service = RecommendationEngineService(
            hybrid_search_service=_FakeHybridSearchService(results=results),
            vector_store=_FakeVectorStore(stored_point=_target_point()),
            recommendation_scorer=_FakeRecommendationScorer(final_score_by_product=scores),
            diversity_enabled=True,
            top_k=4,
        )

        result = await service.recommend(product_id=uuid4())

        recommended_ids = [rec.product_id for rec in result.recommendations]
        assert recommended_ids[0] == nikes[0]
        assert set(recommended_ids[1:4]) == {adidas, puma, asics}

    async def test_disabling_diversity_returns_the_raw_score_order(self) -> None:
        nikes = [uuid4() for _ in range(4)]
        results = [_hybrid_result(pid, brand="Nike") for pid in nikes]
        scores = {pid: 0.9 - i * 0.01 for i, pid in enumerate(nikes)}
        service = RecommendationEngineService(
            hybrid_search_service=_FakeHybridSearchService(results=results),
            vector_store=_FakeVectorStore(stored_point=_target_point()),
            recommendation_scorer=_FakeRecommendationScorer(final_score_by_product=scores),
            diversity_enabled=False,
            top_k=4,
        )

        result = await service.recommend(product_id=uuid4())

        assert [rec.product_id for rec in result.recommendations] == nikes

    async def test_requesting_more_than_available_candidates_returns_what_exists(self) -> None:
        nike, adidas = uuid4(), uuid4()
        service = RecommendationEngineService(
            hybrid_search_service=_FakeHybridSearchService(
                results=[
                    _hybrid_result(nike, brand="Nike"),
                    _hybrid_result(adidas, brand="Adidas"),
                ]
            ),
            vector_store=_FakeVectorStore(stored_point=_target_point()),
            recommendation_scorer=_FakeRecommendationScorer(
                final_score_by_product={nike: 0.9, adidas: 0.8}
            ),
            diversity_enabled=True,
            top_k=10,
        )

        result = await service.recommend(product_id=uuid4())

        assert len(result.recommendations) == 2

    async def test_a_missing_brand_is_still_handled_without_crashing(self) -> None:
        product_id = uuid4()
        service = RecommendationEngineService(
            hybrid_search_service=_FakeHybridSearchService(
                results=[_hybrid_result(product_id, brand=None)]
            ),
            vector_store=_FakeVectorStore(stored_point=_target_point()),
            recommendation_scorer=_FakeRecommendationScorer(
                final_score_by_product={product_id: 0.5}
            ),
            diversity_enabled=True,
            top_k=1,
        )

        result = await service.recommend(product_id=uuid4())

        assert len(result.recommendations) == 1


class TestReranking:
    async def test_disabled_by_default(self) -> None:
        candidate_id = uuid4()
        reranker = _FakeReranker()
        service = RecommendationEngineService(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(candidate_id)]),
            vector_store=_FakeVectorStore(stored_point=_target_point()),
            recommendation_scorer=_FakeRecommendationScorer(
                final_score_by_product={candidate_id: 0.5}
            ),
            reranker=reranker,
        )

        await service.recommend(product_id=uuid4())

        assert reranker.calls == []

    async def test_reranking_uses_the_targets_own_text_representation(self) -> None:
        candidate_id = uuid4()
        target_point = StoredPoint(
            product_id=uuid4(), vector=[0.1], metadata={"name": "Red Shoe", "brand": "Nike"}
        )
        reranker = _FakeReranker()
        service = RecommendationEngineService(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(candidate_id)]),
            vector_store=_FakeVectorStore(stored_point=target_point),
            recommendation_scorer=_FakeRecommendationScorer(
                final_score_by_product={candidate_id: 0.5}
            ),
            reranker=reranker,
            reranking_enabled=True,
        )

        await service.recommend(product_id=uuid4())

        assert reranker.calls[0]["query"] == "Red Shoe. Nike"

    async def test_reranked_score_flows_into_the_scorer(self) -> None:
        first, second = uuid4(), uuid4()
        service = RecommendationEngineService(
            hybrid_search_service=_FakeHybridSearchService(
                results=[_hybrid_result(first), _hybrid_result(second)]
            ),
            vector_store=_FakeVectorStore(stored_point=_target_point()),
            recommendation_scorer=_EchoingRecommendationScorer(),
            reranker=_FakeReranker(rerank_score=0.83),
            reranking_enabled=True,
            diversity_enabled=False,
            top_k=2,
        )

        result = await service.recommend(product_id=uuid4())

        assert [rec.product_id for rec in result.recommendations] == [second, first]
        assert all(rec.similarity_score == 0.83 for rec in result.recommendations)

    async def test_overfetches_at_least_rerank_top_n(self) -> None:
        hybrid_search_service = _FakeHybridSearchService()
        service = RecommendationEngineService(
            hybrid_search_service=hybrid_search_service,
            vector_store=_FakeVectorStore(stored_point=_target_point()),
            recommendation_scorer=_FakeRecommendationScorer(final_score_by_product={}),
            reranker=_FakeReranker(),
            reranking_enabled=True,
            diversity_enabled=False,
            top_k=5,
        )

        await service.recommend(product_id=uuid4())

        requested_top_k = hybrid_search_service.calls[0]["top_k"]
        assert isinstance(requested_top_k, int)
        assert requested_top_k >= 50

    async def test_no_candidates_skips_reranking(self) -> None:
        reranker = _FakeReranker()
        service = RecommendationEngineService(
            hybrid_search_service=_FakeHybridSearchService(results=[]),
            vector_store=_FakeVectorStore(stored_point=_target_point()),
            recommendation_scorer=_FakeRecommendationScorer(final_score_by_product={}),
            reranker=reranker,
            reranking_enabled=True,
        )

        result = await service.recommend(product_id=uuid4())

        assert result.recommendations == []
        assert reranker.calls == []

    async def test_per_call_override_disables_reranking(self) -> None:
        candidate_id = uuid4()
        reranker = _FakeReranker()
        service = RecommendationEngineService(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(candidate_id)]),
            vector_store=_FakeVectorStore(stored_point=_target_point()),
            recommendation_scorer=_FakeRecommendationScorer(
                final_score_by_product={candidate_id: 0.5}
            ),
            reranker=reranker,
            reranking_enabled=True,
        )

        await service.recommend(product_id=uuid4(), reranking_enabled=False)

        assert reranker.calls == []


class TestErrorWrapping:
    async def test_wraps_an_unexpected_scoring_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        product_id = uuid4()
        service = RecommendationEngineService(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(product_id)]),
            vector_store=_FakeVectorStore(stored_point=_target_point()),
            recommendation_scorer=_FakeRecommendationScorer(
                final_score_by_product={product_id: 0.5}
            ),
        )

        def _broken_score(*args: object, **kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(service._recommendation_scorer, "score", _broken_score)

        with pytest.raises(RecommendationException):
            await service.recommend(product_id=uuid4())


class TestExplanations:
    async def _recommend_one(self, candidate: RecommendationCandidate) -> str:
        service = RecommendationEngineService(
            hybrid_search_service=_FakeHybridSearchService(
                results=[_hybrid_result(candidate.product_id)]
            ),
            vector_store=_FakeVectorStore(stored_point=_target_point()),
            recommendation_scorer=_FixedRecommendationScorer(
                candidates_by_product={candidate.product_id: candidate}
            ),
            diversity_enabled=False,
        )
        result = await service.recommend(product_id=uuid4())
        return result.recommendations[0].explanation

    async def test_high_similarity_mentions_visual_appearance(self) -> None:
        explanation = await self._recommend_one(
            RecommendationCandidate(
                product_id=uuid4(),
                similarity_score=0.9,
                quality_score=0.0,
                final_score=0.9,
                reason=RecommendationReason(),
            )
        )

        assert "similar visual appearance" in explanation.lower()

    async def test_shared_category_is_mentioned(self) -> None:
        explanation = await self._recommend_one(
            RecommendationCandidate(
                product_id=uuid4(),
                similarity_score=0.0,
                quality_score=0.0,
                final_score=0.0,
                reason=RecommendationReason(shared_category=True),
            )
        )

        assert "same category" in explanation.lower()

    async def test_shared_brand_is_mentioned(self) -> None:
        explanation = await self._recommend_one(
            RecommendationCandidate(
                product_id=uuid4(),
                similarity_score=0.0,
                quality_score=0.0,
                final_score=0.0,
                reason=RecommendationReason(shared_brand=True),
            )
        )

        assert "same brand" in explanation.lower()

    async def test_matched_attributes_are_named(self) -> None:
        explanation = await self._recommend_one(
            RecommendationCandidate(
                product_id=uuid4(),
                similarity_score=0.0,
                quality_score=0.0,
                final_score=0.0,
                reason=RecommendationReason(matched_attributes=["color", "material"]),
            )
        )

        assert "shared attributes (color, material)" in explanation.lower()

    async def test_shared_tags_are_named_and_truncated(self) -> None:
        explanation = await self._recommend_one(
            RecommendationCandidate(
                product_id=uuid4(),
                similarity_score=0.0,
                quality_score=0.0,
                final_score=0.0,
                reason=RecommendationReason(shared_tags=["running", "red", "blue", "green"]),
            )
        )

        assert "matching tags (running, red, blue)" in explanation.lower()
        assert "green" not in explanation.lower()

    async def test_high_quality_is_mentioned(self) -> None:
        explanation = await self._recommend_one(
            RecommendationCandidate(
                product_id=uuid4(),
                similarity_score=0.0,
                quality_score=0.9,
                final_score=0.5,
                reason=RecommendationReason(),
            )
        )

        assert "high catalog quality" in explanation.lower()

    async def test_no_matching_signals_yields_a_fallback_explanation(self) -> None:
        explanation = await self._recommend_one(
            RecommendationCandidate(
                product_id=uuid4(),
                similarity_score=0.1,
                quality_score=0.1,
                final_score=0.1,
                reason=RecommendationReason(),
            )
        )

        assert explanation == "Related based on overall similarity."

    async def test_explanation_is_capitalized_and_ends_with_a_period(self) -> None:
        explanation = await self._recommend_one(
            RecommendationCandidate(
                product_id=uuid4(),
                similarity_score=0.9,
                quality_score=0.0,
                final_score=0.9,
                reason=RecommendationReason(),
            )
        )

        assert explanation[0].isupper()
        assert explanation.endswith(".")

    async def test_multiple_clauses_are_joined(self) -> None:
        explanation = await self._recommend_one(
            RecommendationCandidate(
                product_id=uuid4(),
                similarity_score=0.9,
                quality_score=0.9,
                final_score=0.9,
                reason=RecommendationReason(shared_category=True, shared_brand=True),
            )
        )

        assert "; " in explanation


class _RoutingFakeHybridSearchService(HybridSearchService):
    """Returns a different candidate set per target product_id — unlike
    `_FakeHybridSearchService`'s single fixed response, this lets a
    concurrency test prove that concurrent `.recommend()` calls each get
    back *their own* correct candidates, not one call's result leaking
    into another's.
    """

    def __init__(self, results_by_product: dict[UUID, list[HybridSearchResult]]) -> None:
        self._results_by_product = results_by_product

    async def search_by_product_id(
        self,
        product_id: UUID,
        *,
        top_k: int | None = None,
        filters: ProductFilters | None = None,
        modality: SearchModality | None = None,
    ) -> list[HybridSearchResult]:
        await asyncio.sleep(0)  # yield control, widening any race window
        return self._results_by_product[product_id]


class _RoutingFakeVectorStore(BaseVectorStore):
    """Returns a different target `StoredPoint` per product_id."""

    def __init__(self, points_by_product: dict[UUID, StoredPoint]) -> None:
        self._points_by_product = points_by_product

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
        return product_id in self._points_by_product

    async def retrieve(self, collection: VectorCollection, product_id: UUID) -> StoredPoint | None:
        await asyncio.sleep(0)  # yield control, widening any race window
        return self._points_by_product.get(product_id)

    async def health(self) -> bool:
        return True


class TestConcurrency:
    async def test_concurrent_recommend_calls_each_return_their_own_result(self) -> None:
        targets = [uuid4() for _ in range(8)]
        candidate_by_target = {target: uuid4() for target in targets}
        results_by_product = {
            target: [_hybrid_result(candidate_id)]
            for target, candidate_id in candidate_by_target.items()
        }
        points_by_product = {target: _target_point(target) for target in targets}
        scores = dict.fromkeys(candidate_by_target.values(), 0.9)

        service = RecommendationEngineService(
            hybrid_search_service=_RoutingFakeHybridSearchService(results_by_product),
            vector_store=_RoutingFakeVectorStore(points_by_product),
            recommendation_scorer=_FakeRecommendationScorer(final_score_by_product=scores),
            diversity_enabled=False,
        )

        results = await asyncio.gather(*(service.recommend(product_id=t) for t in targets))

        for target, result in zip(targets, results, strict=True):
            assert result.recommendations[0].product_id == candidate_by_target[target]
