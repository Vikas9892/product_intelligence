"""Unit tests for `PricingEngine` (comparable retrieval, Milestone 3).

Composes a fake `HybridSearchService` so the retrieve -> normalize ->
estimate flow is tested without a real vector store or model.
"""

from uuid import UUID, uuid4

import pytest

from app.core.constants import PricingStrategy
from app.exceptions.errors import PricingException, ResourceNotFoundException
from app.models.search import HybridSearchResult, ProductFilters, SearchModality
from app.schemas.product import ProductImage
from app.services.pricing.price_estimator import PriceEstimator
from app.services.pricing.pricing_engine import PricingEngine
from app.services.vectorstore.hybrid_search_service import HybridSearchService


class _FakeHybridSearchService(HybridSearchService):
    def __init__(
        self,
        *,
        results: list[HybridSearchResult] | None = None,
        by_id_results: list[HybridSearchResult] | None = None,
        search_error: Exception | None = None,
        by_id_error: Exception | None = None,
    ) -> None:
        self._results = results if results is not None else []
        self._by_id_results = by_id_results if by_id_results is not None else []
        self._search_error = search_error
        self._by_id_error = by_id_error
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
        if self._search_error is not None:
            raise self._search_error
        return self._results

    async def search_by_product_id(
        self,
        product_id: UUID,
        *,
        top_k: int | None = None,
        filters: ProductFilters | None = None,
        modality: SearchModality | None = None,
    ) -> list[HybridSearchResult]:
        if self._by_id_error is not None:
            raise self._by_id_error
        return self._by_id_results


def _priced(price: float, *, score: float = 0.9) -> HybridSearchResult:
    return HybridSearchResult(
        product_id=uuid4(),
        score=score,
        metadata={"price": price, "brand": "Nike"},
        matched_modalities=[SearchModality.TEXT],
    )


def _engine(
    hybrid: HybridSearchService, *, strategy: PricingStrategy = PricingStrategy.MEDIAN
) -> PricingEngine:
    return PricingEngine(
        hybrid_search_service=hybrid,
        estimator=PriceEstimator(strategy=strategy, min_comparables=1),
        top_k=10,
    )


class TestEstimateForRequest:
    async def test_estimates_from_retrieved_comparables(self) -> None:
        hybrid = _FakeHybridSearchService(results=[_priced(10.0), _priced(20.0), _priced(300.0)])
        engine = _engine(hybrid)

        estimate = await engine.estimate_for_request(
            name="Widget", brand="Nike", category=None, description=None
        )

        assert estimate.estimated_price == 20.0  # median
        assert estimate.comparable_count == 3

    async def test_builds_a_text_query_and_passes_top_k(self) -> None:
        hybrid = _FakeHybridSearchService(results=[_priced(10.0)])
        engine = _engine(hybrid)

        await engine.estimate_for_request(
            name="Widget", brand="Nike", category="Shoes", description=None, top_k=5
        )

        assert hybrid.calls[0]["top_k"] == 5
        assert "Widget" in str(hybrid.calls[0]["text"])

    async def test_no_priced_comparables_yields_a_zero_estimate(self) -> None:
        hybrid = _FakeHybridSearchService(
            results=[
                HybridSearchResult(
                    product_id=uuid4(),
                    score=0.9,
                    metadata={},
                    matched_modalities=[SearchModality.TEXT],
                )
            ]
        )
        engine = _engine(hybrid)

        estimate = await engine.estimate_for_request(
            name="Widget", brand=None, category=None, description=None
        )

        assert estimate.estimated_price == 0.0
        assert estimate.comparable_count == 0

    async def test_wraps_an_unexpected_search_failure(self) -> None:
        hybrid = _FakeHybridSearchService(search_error=RuntimeError("boom"))
        engine = _engine(hybrid)

        with pytest.raises(PricingException):
            await engine.estimate_for_request(
                name="Widget", brand=None, category=None, description=None
            )

    async def test_propagates_an_app_exception_from_search(self) -> None:
        hybrid = _FakeHybridSearchService(
            search_error=ResourceNotFoundException("gone", resource="product")
        )
        engine = _engine(hybrid)

        with pytest.raises(ResourceNotFoundException):
            await engine.estimate_for_request(
                name="Widget", brand=None, category=None, description=None
            )


class TestMetrics:
    async def test_records_a_pricing_metric(self) -> None:
        from prometheus_client import CollectorRegistry

        from app.metrics.metrics_registry import MetricsRegistry

        metrics = MetricsRegistry(registry=CollectorRegistry())
        hybrid = _FakeHybridSearchService(results=[_priced(10.0), _priced(20.0)])
        engine = PricingEngine(
            hybrid_search_service=hybrid,
            estimator=PriceEstimator(strategy=PricingStrategy.MEDIAN, min_comparables=1),
            top_k=10,
            metrics_registry=metrics,
        )

        estimate = await engine.estimate_for_request(
            name="Widget", brand=None, category=None, description=None
        )

        assert (
            metrics._registry.get_sample_value(
                "product_intelligence_pricing_estimates_total",
                {"confidence": estimate.confidence.value},
            )
            == 1.0
        )
        assert (
            metrics._registry.get_sample_value("product_intelligence_pricing_seconds_count") == 1.0
        )


class TestEstimateForProduct:
    async def test_estimates_from_by_id_comparables(self) -> None:
        hybrid = _FakeHybridSearchService(by_id_results=[_priced(50.0), _priced(70.0)])
        engine = _engine(hybrid)

        estimate = await engine.estimate_for_product(uuid4())

        assert estimate.estimated_price == 60.0  # median of 50, 70
        assert estimate.comparable_count == 2

    async def test_propagates_resource_not_found(self) -> None:
        hybrid = _FakeHybridSearchService(
            by_id_error=ResourceNotFoundException("not indexed", resource="product")
        )
        engine = _engine(hybrid)

        with pytest.raises(ResourceNotFoundException):
            await engine.estimate_for_product(uuid4())

    async def test_wraps_an_unexpected_by_id_failure(self) -> None:
        hybrid = _FakeHybridSearchService(by_id_error=RuntimeError("boom"))
        engine = _engine(hybrid)

        with pytest.raises(PricingException):
            await engine.estimate_for_product(uuid4())
