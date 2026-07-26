"""Unit tests for `DuplicateDetectionService`.

Composes fake `HybridSearchService`/`SimilarityScorer` doubles (not the
real retrieval/scoring pipelines — those are already covered by
`test_hybrid_search_service.py`/`test_similarity_scorer.py`) so the
ranking/thresholding/decision logic can be tested against precisely
controlled inputs.
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.exceptions.errors import DuplicateDetectionException
from app.models.duplicate_decision import DuplicateDecision
from app.models.duplicate_result import DuplicateResult
from app.models.product_attributes import ProductAttributes
from app.models.search import HybridSearchResult, ProductFilters, SearchModality
from app.models.similarity_signal import SimilaritySignal
from app.schemas.product import ProductImage
from app.services.duplicate.duplicate_detection_service import DuplicateDetectionService
from app.services.duplicate.similarity_scorer import SimilarityScorer
from app.services.vectorstore.hybrid_search_service import HybridSearchService


class _FakeHybridSearchService(HybridSearchService):
    def __init__(self, *, results: list[HybridSearchResult] | None = None) -> None:
        self._results = results if results is not None else []
        self.calls: list[tuple[object, object, object]] = []

    async def search(
        self,
        *,
        image: ProductImage | None = None,
        text: str | None = None,
        top_k: int | None = None,
        filters: ProductFilters | None = None,
    ) -> list[HybridSearchResult]:
        self.calls.append((image, text, top_k))
        return self._results


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
