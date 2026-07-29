"""Integration tests for the Phase 16 decision-trace endpoints.

Builds the *real* `create_app()` app, overriding
`get_recommendation_engine_service`/`get_duplicate_detection_service` with
fakes — the explainers' own logic is covered in isolation by their unit
tests; this suite proves the routes run the inference, explain the
results, and shape the response.
"""

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application import create_app
from app.core.config import settings
from app.dependencies.duplicate import get_duplicate_detection_service
from app.dependencies.recommendation import get_recommendation_engine_service
from app.exceptions.errors import ResourceNotFoundException
from app.models.duplicate_decision import DuplicateDecision
from app.models.recommendation_candidate import RecommendationCandidate
from app.models.recommendation_reason import RecommendationReason
from app.models.recommendation_result import RecommendationResult
from app.models.recommendation_type import RecommendationType
from app.services.duplicate.duplicate_detection_service import DuplicateDetectionService
from app.services.recommendation.recommendation_engine_service import RecommendationEngineService

_PREFIX = settings.application.api_prefix
_KNOWN_ID = uuid4()
_MISSING_ID = uuid4()


class _FakeRecommendationEngineService(RecommendationEngineService):
    def __init__(self) -> None:
        pass

    async def recommend(
        self,
        *,
        product_id: UUID,
        recommendation_type: RecommendationType = RecommendationType.SIMILAR,
        top_k: int | None = None,
        reranking_enabled: bool | None = None,
    ) -> RecommendationResult:
        if product_id == _MISSING_ID:
            raise ResourceNotFoundException("not indexed", resource="product")
        return RecommendationResult(
            recommendations=[
                RecommendationCandidate(
                    product_id=uuid4(),
                    similarity_score=0.9,
                    quality_score=0.8,
                    final_score=0.88,
                    reason=RecommendationReason(shared_brand=True, shared_category=True),
                )
            ],
            recommendation_type=recommendation_type,
            processing_time=0.01,
        )


class _FakeDuplicateDetectionService(DuplicateDetectionService):
    def __init__(self) -> None:
        pass

    async def detect_by_product_id(
        self,
        product_id: UUID,
        *,
        top_k: int | None = None,
        threshold: float | None = None,
        reranking_enabled: bool | None = None,
    ) -> DuplicateDecision:
        if product_id == _MISSING_ID:
            raise ResourceNotFoundException("not indexed", resource="product")
        return DuplicateDecision(
            is_duplicate=True,
            confidence=0.93,
            reason="Overall similarity 0.93 meets or exceeds the 0.90 threshold.",
            matched_product=uuid4(),
        )


@pytest.fixture
def explanations_client() -> Iterator[TestClient]:
    app: FastAPI = create_app()
    app.dependency_overrides[get_recommendation_engine_service] = _FakeRecommendationEngineService
    app.dependency_overrides[get_duplicate_detection_service] = _FakeDuplicateDetectionService
    with TestClient(app) as client:
        yield client


class TestRecommendationTrace:
    def test_returns_one_trace_per_recommendation(self, explanations_client: TestClient) -> None:
        response = explanations_client.get(f"{_PREFIX}/recommendations/{_KNOWN_ID}/trace")

        assert response.status_code == 200
        body = response.json()
        assert body["subject_id"] == str(_KNOWN_ID)
        assert body["count"] == 1
        assert body["traces"][0]["decision_type"] == "recommendation"
        assert "the same brand" in body["traces"][0]["summary"]

    def test_404_for_an_unindexed_product(self, explanations_client: TestClient) -> None:
        response = explanations_client.get(f"{_PREFIX}/recommendations/{_MISSING_ID}/trace")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "resource_not_found"


class TestDuplicateTrace:
    def test_returns_the_duplicate_trace(self, explanations_client: TestClient) -> None:
        response = explanations_client.get(f"{_PREFIX}/duplicates/{_KNOWN_ID}/trace")

        assert response.status_code == 200
        body = response.json()
        assert body["decision_type"] == "duplicate"
        assert body["confidence"] == 0.93
        assert body["summary"].startswith("Judged a duplicate because")

    def test_404_for_an_unindexed_product(self, explanations_client: TestClient) -> None:
        response = explanations_client.get(f"{_PREFIX}/duplicates/{_MISSING_ID}/trace")

        assert response.status_code == 404


class TestProductExplanations:
    def test_combines_duplicate_and_recommendation_traces(
        self, explanations_client: TestClient
    ) -> None:
        response = explanations_client.get(f"{_PREFIX}/products/{_KNOWN_ID}/explanations")

        assert response.status_code == 200
        body = response.json()
        assert body["product_id"] == str(_KNOWN_ID)
        assert body["duplicate"]["decision_type"] == "duplicate"
        assert len(body["recommendations"]) == 1

    def test_never_returns_a_raw_vector(self, explanations_client: TestClient) -> None:
        response = explanations_client.get(f"{_PREFIX}/products/{_KNOWN_ID}/explanations")

        assert "vector" not in response.text
