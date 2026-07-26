"""Unit tests for `HybridSearchService`.

Composes fake `SearchService`/`TextSearchService` doubles (not the real
image/text pipelines — those are `test_search_service.py`/
`test_text_search_service.py`'s job) to exercise dispatch and score-fusion
logic in isolation.
"""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.exceptions.errors import HybridSearchException, ValidationException
from app.models.search import NearestNeighbor, ProductFilters, SearchModality, SearchResult
from app.schemas.product import ProductImage
from app.services.vectorstore import hybrid_search_service as hybrid_search_service_module
from app.services.vectorstore.hybrid_search_service import HybridSearchService
from app.services.vectorstore.search_service import SearchService
from app.services.vectorstore.text_search_service import TextSearchService


class _FakeSearchService(SearchService):
    """Bypasses `SearchService.__init__` entirely — these tests only care
    about `HybridSearchService`'s dispatch/fusion, not image processing.
    """

    def __init__(self, *, neighbors: list[NearestNeighbor] | None = None) -> None:
        self._neighbors = neighbors if neighbors is not None else []
        self.calls: list[dict[str, object]] = []

    async def search_by_image(self, image, *, top_k=None, filters=None) -> SearchResult:  # type: ignore[no-untyped-def]
        self.calls.append({"image": image, "top_k": top_k, "filters": filters})
        return SearchResult(query_model_name="fake-clip-model", neighbors=self._neighbors)


class _FakeTextSearchService(TextSearchService):
    def __init__(self, *, neighbors: list[NearestNeighbor] | None = None) -> None:
        self._neighbors = neighbors if neighbors is not None else []
        self.calls: list[dict[str, object]] = []

    async def search_by_text(self, query, *, top_k=None, filters=None) -> SearchResult:  # type: ignore[no-untyped-def]
        self.calls.append({"query": query, "top_k": top_k, "filters": filters})
        return SearchResult(query_model_name="fake-text-model", neighbors=self._neighbors)


class _RoutingFakeTextSearchService(TextSearchService):
    """Returns a different, query-specific neighbor per call — unlike
    `_FakeTextSearchService`'s single fixed response, this lets a
    concurrency test prove that concurrent calls each get back *their
    own* correct result, not one call's result leaking into another's.
    """

    def __init__(self, neighbors_by_query: dict[str, NearestNeighbor]) -> None:
        self._neighbors_by_query = neighbors_by_query

    async def search_by_text(self, query, *, top_k=None, filters=None) -> SearchResult:  # type: ignore[no-untyped-def]
        await asyncio.sleep(0)  # yield control, widening any race window
        return SearchResult(
            query_model_name="fake-text-model", neighbors=[self._neighbors_by_query[query]]
        )


def _image() -> ProductImage:
    return ProductImage(
        original_filename="query.jpg",
        stored_filename="query.jpg",
        content_type="image/jpeg",
        size_bytes=5,
        uploaded_at=datetime.now(UTC),
    )


def _build_service(
    *,
    image_neighbors: list[NearestNeighbor] | None = None,
    text_neighbors: list[NearestNeighbor] | None = None,
    image_weight: float | None = None,
    text_weight: float | None = None,
) -> HybridSearchService:
    return HybridSearchService(
        search_service=_FakeSearchService(neighbors=image_neighbors),
        text_search_service=_FakeTextSearchService(neighbors=text_neighbors),
        image_weight=image_weight,
        text_weight=text_weight,
    )


class TestValidation:
    async def test_raises_when_neither_image_nor_text_is_given(self) -> None:
        service = _build_service()

        with pytest.raises(ValidationException):
            await service.search()

    async def test_raises_when_text_is_blank_and_no_image_is_given(self) -> None:
        service = _build_service()

        with pytest.raises(ValidationException):
            await service.search(text="   ")


class TestImageOnlySearch:
    async def test_returns_the_images_own_scores_unweighted(self) -> None:
        product_id = uuid4()
        neighbor = NearestNeighbor(product_id=product_id, score=0.83, metadata={"name": "Widget"})
        service = _build_service(image_neighbors=[neighbor], image_weight=0.7, text_weight=0.3)

        results = await service.search(image=_image())

        assert len(results) == 1
        assert results[0].product_id == product_id
        assert results[0].score == 0.83
        assert results[0].matched_modalities == [SearchModality.IMAGE]

    async def test_does_not_call_the_text_search_service(self) -> None:
        text_search_service = _FakeTextSearchService()
        service = HybridSearchService(
            search_service=_FakeSearchService(), text_search_service=text_search_service
        )

        await service.search(image=_image())

        assert text_search_service.calls == []


class TestTextOnlySearch:
    async def test_returns_the_texts_own_scores_unweighted(self) -> None:
        product_id = uuid4()
        neighbor = NearestNeighbor(product_id=product_id, score=0.61, metadata={"name": "Widget"})
        service = _build_service(text_neighbors=[neighbor], image_weight=0.7, text_weight=0.3)

        results = await service.search(text="a red running shoe")

        assert len(results) == 1
        assert results[0].product_id == product_id
        assert results[0].score == 0.61
        assert results[0].matched_modalities == [SearchModality.TEXT]

    async def test_does_not_call_the_image_search_service(self) -> None:
        search_service = _FakeSearchService()
        service = HybridSearchService(
            search_service=search_service, text_search_service=_FakeTextSearchService()
        )

        await service.search(text="a red running shoe")

        assert search_service.calls == []


class TestHybridFusion:
    async def test_fuses_scores_using_configured_weights(self) -> None:
        product_id = uuid4()
        image_neighbor = NearestNeighbor(product_id=product_id, score=1.0)
        text_neighbor = NearestNeighbor(product_id=product_id, score=0.5)
        service = _build_service(
            image_neighbors=[image_neighbor],
            text_neighbors=[text_neighbor],
            image_weight=0.7,
            text_weight=0.3,
        )

        results = await service.search(image=_image(), text="query")

        assert len(results) == 1
        assert results[0].score == pytest.approx(0.7 * 1.0 + 0.3 * 0.5)
        assert set(results[0].matched_modalities) == {SearchModality.IMAGE, SearchModality.TEXT}

    async def test_a_product_only_in_image_results_gets_zero_text_contribution(self) -> None:
        product_id = uuid4()
        image_neighbor = NearestNeighbor(product_id=product_id, score=0.8)
        service = _build_service(
            image_neighbors=[image_neighbor], text_neighbors=[], image_weight=0.7, text_weight=0.3
        )

        results = await service.search(image=_image(), text="query")

        assert results[0].score == pytest.approx(0.7 * 0.8)
        assert results[0].matched_modalities == [SearchModality.IMAGE]

    async def test_a_product_only_in_text_results_gets_zero_image_contribution(self) -> None:
        product_id = uuid4()
        text_neighbor = NearestNeighbor(product_id=product_id, score=0.6)
        service = _build_service(
            image_neighbors=[], text_neighbors=[text_neighbor], image_weight=0.7, text_weight=0.3
        )

        results = await service.search(image=_image(), text="query")

        assert results[0].score == pytest.approx(0.3 * 0.6)
        assert results[0].matched_modalities == [SearchModality.TEXT]

    async def test_deduplicates_a_product_present_in_both_result_sets(self) -> None:
        product_id = uuid4()
        service = _build_service(
            image_neighbors=[NearestNeighbor(product_id=product_id, score=0.9)],
            text_neighbors=[NearestNeighbor(product_id=product_id, score=0.4)],
        )

        results = await service.search(image=_image(), text="query")

        assert len(results) == 1

    async def test_orders_fused_results_by_descending_score(self) -> None:
        high_id, low_id = uuid4(), uuid4()
        service = _build_service(
            image_neighbors=[
                NearestNeighbor(product_id=low_id, score=0.1),
                NearestNeighbor(product_id=high_id, score=0.9),
            ],
            image_weight=1.0,
            text_weight=0.0,
        )

        results = await service.search(image=_image(), text="query")

        assert [result.product_id for result in results] == [high_id, low_id]

    async def test_limits_fused_results_to_top_k(self) -> None:
        neighbors = [NearestNeighbor(product_id=uuid4(), score=0.5) for _ in range(5)]
        service = _build_service(image_neighbors=neighbors, image_weight=1.0, text_weight=0.0)

        results = await service.search(image=_image(), text="query", top_k=2)

        assert len(results) == 2

    async def test_returns_an_empty_list_when_neither_search_finds_anything(self) -> None:
        service = _build_service()

        results = await service.search(image=_image(), text="query")

        assert results == []

    async def test_passes_filters_to_both_sub_searches(self) -> None:
        search_service = _FakeSearchService()
        text_search_service = _FakeTextSearchService()
        service = HybridSearchService(
            search_service=search_service, text_search_service=text_search_service
        )
        filters = ProductFilters(category="shoes")

        await service.search(image=_image(), text="query", filters=filters)

        assert search_service.calls[0]["filters"] == filters
        assert text_search_service.calls[0]["filters"] == filters

    async def test_wraps_an_unexpected_fusion_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _broken_fuse(*args: object, **kwargs: object) -> list:  # type: ignore[type-arg]
            raise RuntimeError("boom")

        monkeypatch.setattr(hybrid_search_service_module, "_fuse", _broken_fuse)
        service = _build_service(
            image_neighbors=[NearestNeighbor(product_id=uuid4(), score=0.5)],
            text_neighbors=[NearestNeighbor(product_id=uuid4(), score=0.5)],
        )

        with pytest.raises(HybridSearchException):
            await service.search(image=_image(), text="query")


class TestConcurrency:
    async def test_concurrent_text_searches_each_return_their_own_result(self) -> None:
        neighbors_by_query = {
            f"query-{i}": NearestNeighbor(product_id=uuid4(), score=0.5) for i in range(8)
        }
        service = HybridSearchService(
            search_service=_FakeSearchService(),
            text_search_service=_RoutingFakeTextSearchService(neighbors_by_query),
        )

        results = await asyncio.gather(
            *(service.search(text=query) for query in neighbors_by_query)
        )

        for query, result in zip(neighbors_by_query, results, strict=True):
            assert result[0].product_id == neighbors_by_query[query].product_id
