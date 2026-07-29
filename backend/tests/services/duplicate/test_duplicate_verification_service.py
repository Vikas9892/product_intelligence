"""Unit tests for `DuplicateVerificationService` (the reranking pipeline, Milestone 3).

Composes fake `HybridSearchService`/`BaseReranker` doubles so the
retrieval -> rerank -> confidence flow is tested against precisely
controlled scores, with no real model inference. Business-rule
combination (Milestone 4) is tested separately once it exists.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.exceptions.errors import DuplicateVerificationException, RerankException
from app.models.product_attributes import ProductAttributes
from app.models.rerank_reason import RerankReason
from app.models.rerank_result import RerankResult
from app.models.reranked_candidate import RerankedCandidate
from app.models.search import HybridSearchResult, ProductFilters, SearchModality
from app.schemas.product import ProductImage
from app.services.base_reranker import BaseReranker
from app.services.duplicate.business_rules_evaluator import BusinessRulesEvaluator
from app.services.duplicate.duplicate_verification_service import DuplicateVerificationService
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
        self.calls.append({"text": text, "top_k": top_k, "reranking_enabled": reranking_enabled})
        return self._results


class _FakeReranker(BaseReranker):
    """Returns a fixed rerank score per product_id, sorted descending."""

    def __init__(
        self, *, scores: dict[UUID, float] | None = None, error: Exception | None = None
    ) -> None:
        self._scores = scores if scores is not None else {}
        self._error = error
        self.calls: list[dict[str, object]] = []

    async def rerank(
        self,
        query: str,
        candidates: list[HybridSearchResult],
        *,
        top_k: int | None = None,
    ) -> RerankResult:
        self.calls.append({"query": query, "candidates": candidates, "top_k": top_k})
        if self._error is not None:
            raise self._error
        ordered = sorted(
            candidates, key=lambda c: self._scores.get(c.product_id, 0.0), reverse=True
        )
        return RerankResult(
            query=query,
            candidates=[
                RerankedCandidate(
                    product_id=candidate.product_id,
                    original_score=candidate.score,
                    rerank_score=self._scores.get(candidate.product_id, 0.0),
                    final_rank=rank,
                    metadata=candidate.metadata,
                    reason=RerankReason(original_rank=rank, final_rank=rank, rank_delta=0),
                )
                for rank, candidate in enumerate(ordered, start=1)
            ],
            original_count=len(candidates),
        )


def _hybrid_result(
    product_id: UUID, *, score: float = 0.9, image_score: float = 0.8, text_score: float = 0.7
) -> HybridSearchResult:
    return HybridSearchResult(
        product_id=product_id,
        score=score,
        metadata={"brand": "Nike"},
        matched_modalities=[SearchModality.TEXT],
        image_score=image_score,
        text_score=text_score,
    )


def _image() -> ProductImage:
    return ProductImage(
        original_filename="photo.jpg",
        stored_filename="stored.jpg",
        content_type="image/jpeg",
        size_bytes=10,
        uploaded_at=datetime.now(UTC),
    )


def _service(
    *,
    hybrid_search_service: HybridSearchService | None = None,
    reranker: BaseReranker | None = None,
    business_rules_evaluator: BusinessRulesEvaluator | None = None,
    cross_encoder_threshold: float = 0.95,
    cross_encoder_weight: float = 1.0,
    business_rules_weight: float = 0.0,
) -> DuplicateVerificationService:
    # Weights default to 1.0/0.0 so the reranking-focused tests assert
    # `confidence == cross_encoder_score` cleanly; the business-rules
    # combination is exercised with realistic weights in its own class.
    return DuplicateVerificationService(
        hybrid_search_service=(
            hybrid_search_service
            if hybrid_search_service is not None
            else _FakeHybridSearchService()
        ),
        reranker=reranker if reranker is not None else _FakeReranker(),
        business_rules_evaluator=business_rules_evaluator,
        cross_encoder_threshold=cross_encoder_threshold,
        cross_encoder_weight=cross_encoder_weight,
        business_rules_weight=business_rules_weight,
    )


class TestNoCandidates:
    async def test_empty_retrieval_yields_a_non_duplicate(self) -> None:
        service = _service(hybrid_search_service=_FakeHybridSearchService(results=[]))

        verification = await service.verify(
            name="Widget", brand=None, category=None, description=None, image=_image()
        )

        assert verification.is_duplicate is False
        assert verification.confidence == 0.0
        assert verification.cross_encoder_score is None
        assert verification.matched_product is None
        assert verification.reasons[0].code == "no_candidates"


class TestReranking:
    async def test_ranks_by_cross_encoder_score_not_retrieval_score(self) -> None:
        low_retrieval_high_ce, high_retrieval_low_ce = uuid4(), uuid4()
        results = [
            _hybrid_result(high_retrieval_low_ce, score=0.99),
            _hybrid_result(low_retrieval_high_ce, score=0.50),
        ]
        reranker = _FakeReranker(scores={low_retrieval_high_ce: 0.98, high_retrieval_low_ce: 0.10})
        service = _service(
            hybrid_search_service=_FakeHybridSearchService(results=results), reranker=reranker
        )

        verification = await service.verify(
            name="Widget", brand=None, category=None, description=None, image=_image()
        )

        assert verification.matched_product == low_retrieval_high_ce
        assert verification.cross_encoder_score == 0.98
        assert verification.retrieval_similarity == 0.50

    async def test_flags_duplicate_when_cross_encoder_meets_threshold(self) -> None:
        product_id = uuid4()
        service = _service(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(product_id)]),
            reranker=_FakeReranker(scores={product_id: 0.96}),
            cross_encoder_threshold=0.95,
        )

        verification = await service.verify(
            name="Widget", brand=None, category=None, description=None, image=_image()
        )

        assert verification.is_duplicate is True
        assert verification.confidence == 0.96

    async def test_not_duplicate_when_below_threshold(self) -> None:
        product_id = uuid4()
        service = _service(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(product_id)]),
            reranker=_FakeReranker(scores={product_id: 0.80}),
            cross_encoder_threshold=0.95,
        )

        verification = await service.verify(
            name="Widget", brand=None, category=None, description=None, image=_image()
        )

        assert verification.is_duplicate is False

    async def test_retrieval_runs_with_reranking_disabled(self) -> None:
        product_id = uuid4()
        hybrid = _FakeHybridSearchService(results=[_hybrid_result(product_id)])
        service = _service(
            hybrid_search_service=hybrid, reranker=_FakeReranker(scores={product_id: 0.9})
        )

        await service.verify(
            name="Widget", brand=None, category=None, description=None, image=_image()
        )

        assert hybrid.calls[0]["reranking_enabled"] is False

    async def test_populates_top_candidates(self) -> None:
        a, b = uuid4(), uuid4()
        service = _service(
            hybrid_search_service=_FakeHybridSearchService(
                results=[_hybrid_result(a), _hybrid_result(b)]
            ),
            reranker=_FakeReranker(scores={a: 0.9, b: 0.4}),
        )

        verification = await service.verify(
            name="Widget", brand=None, category=None, description=None, image=_image()
        )

        assert [c.product_id for c in verification.top_candidates] == [a, b]
        assert verification.top_candidates[0].overall_similarity == 0.9


class TestErrorHandling:
    async def test_wraps_an_unexpected_rerank_failure(self) -> None:
        product_id = uuid4()
        service = _service(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(product_id)]),
            reranker=_FakeReranker(error=RuntimeError("boom")),
        )

        with pytest.raises(DuplicateVerificationException):
            await service.verify(
                name="Widget", brand=None, category=None, description=None, image=_image()
            )

    async def test_lets_a_rerank_exception_propagate_unwrapped(self) -> None:
        product_id = uuid4()
        service = _service(
            hybrid_search_service=_FakeHybridSearchService(results=[_hybrid_result(product_id)]),
            reranker=_FakeReranker(error=RerankException("cross-encoder down")),
        )

        with pytest.raises(RerankException):
            await service.verify(
                name="Widget", brand=None, category=None, description=None, image=_image()
            )


class TestBusinessRulesCombination:
    async def test_confidence_blends_cross_encoder_and_business_scores(self) -> None:
        product_id = uuid4()
        # Candidate metadata matches brand + category + name -> business
        # score contributes; blended confidence = 0.7*ce + 0.3*business.
        results = [
            HybridSearchResult(
                product_id=product_id,
                score=0.5,
                metadata={"brand": "Nike", "category": "Shoes", "name": "Nike Air Max"},
                matched_modalities=[SearchModality.TEXT],
            )
        ]
        service = _service(
            hybrid_search_service=_FakeHybridSearchService(results=results),
            reranker=_FakeReranker(scores={product_id: 0.90}),
            business_rules_evaluator=BusinessRulesEvaluator(),
            cross_encoder_weight=0.7,
            business_rules_weight=0.3,
        )

        verification = await service.verify(
            name="Nike Air Max",
            brand="Nike",
            category="Shoes",
            description=None,
            image=_image(),
        )

        # brand/category/title all satisfied -> business score 1.0.
        assert verification.confidence == pytest.approx(0.7 * 0.90 + 0.3 * 1.0)
        assert {r.code for r in verification.reasons} >= {
            "cross_encoder",
            "same_brand",
            "same_category",
            "title_similarity",
        }

    async def test_a_hard_gate_veto_overrides_a_high_cross_encoder_score(self) -> None:
        product_id = uuid4()
        results = [
            HybridSearchResult(
                product_id=product_id,
                score=0.5,
                metadata={"brand": "Adidas"},
                matched_modalities=[SearchModality.TEXT],
            )
        ]
        evaluator = BusinessRulesEvaluator(require_same_brand=True)
        service = _service(
            hybrid_search_service=_FakeHybridSearchService(results=results),
            reranker=_FakeReranker(scores={product_id: 0.99}),
            business_rules_evaluator=evaluator,
            cross_encoder_threshold=0.95,
            cross_encoder_weight=0.7,
            business_rules_weight=0.3,
        )

        verification = await service.verify(
            name="Widget",
            brand="Nike",
            category=None,
            description=None,
            image=_image(),
            attributes=ProductAttributes(),
        )

        # Cross-encoder 0.99 clears the 0.95 threshold, but the brand
        # mismatch veto forces is_duplicate False.
        assert verification.cross_encoder_score == 0.99
        assert verification.is_duplicate is False
        assert "brand_mismatch" in {r.code for r in verification.reasons}
