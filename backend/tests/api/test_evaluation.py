"""Integration tests for `POST /api/v1/evaluation/run`.

Builds the *real* `create_app()` application, overriding
`get_dataset_loader`/`get_retrieval_evaluator` with fakes — the real
dispatch/metric-computation logic is `test_retrieval_evaluator.py`'s job
(already covered there in isolation); this suite only proves the router
itself is wired correctly: request parsing, subset filtering
(`query_ids`/`limit`), and response shaping.
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.application import create_app
from app.core.config import settings
from app.dependencies.evaluation import get_dataset_loader, get_retrieval_evaluator
from app.models.benchmark_report import BenchmarkReport
from app.models.evaluation_query import EvaluationQuery, GroundTruth
from app.models.evaluation_result import EvaluationQueryResult
from app.models.model_info import ModelInfo
from app.models.model_type import ModelType
from app.models.rerank_comparison_report import RerankComparisonReport
from app.models.retrieval_metrics import RetrievalMetrics
from app.services.evaluation.dataset_loader import DatasetLoader
from app.services.evaluation.retrieval_evaluator import RetrievalEvaluator

_RUN_URL = f"{settings.application.api_prefix}/evaluation/run"
_COMPARE_URL = f"{settings.application.api_prefix}/evaluation/compare-reranking"


def _query(query_id: str) -> EvaluationQuery:
    return EvaluationQuery(query_id=query_id, text="shoes", ground_truth=GroundTruth())


class _FakeDatasetLoader(DatasetLoader):
    def __init__(self, *, queries: list[EvaluationQuery]) -> None:
        self._queries = queries

    def load(self) -> list[EvaluationQuery]:
        return self._queries


class _EchoingFakeRetrievalEvaluator(RetrievalEvaluator):
    """Echoes back which queries it actually received, so tests can verify
    subset filtering (query_ids/limit) happened before reaching the evaluator."""

    def __init__(self) -> None:
        self.received: list[EvaluationQuery] | None = None
        self.compare_received: list[EvaluationQuery] | None = None

    async def evaluate(
        self,
        queries: list[EvaluationQuery] | None = None,
        *,
        reranking_enabled: bool | None = None,
    ) -> BenchmarkReport:
        self.received = queries
        resolved = queries if queries is not None else []
        mrr = 0.90 if reranking_enabled else 0.81
        return BenchmarkReport(
            generated_at=datetime.now(UTC),
            dataset_size=len(resolved),
            overall_metrics=(
                {"retrieval": RetrievalMetrics(mrr=mrr, query_count=len(resolved))}
                if resolved
                else {}
            ),
            query_results=[
                EvaluationQueryResult(
                    query_id=query.query_id,
                    task_type=query.task_type,
                    reciprocal_rank=1.0,
                    latency_seconds=0.01,
                )
                for query in resolved
            ],
            total_duration_seconds=0.02,
            failure_count=0,
            models=[
                ModelInfo(
                    model_name="openai/clip-vit-base-patch32",
                    version="1.0.0",
                    model_type=ModelType.IMAGE_EMBEDDING,
                    dimension=512,
                )
            ],
        )

    async def compare_reranking(
        self, queries: list[EvaluationQuery] | None = None
    ) -> RerankComparisonReport:
        self.compare_received = queries
        without_reranking = await self.evaluate(queries, reranking_enabled=False)
        with_reranking = await self.evaluate(queries, reranking_enabled=True)
        improvement = (
            {
                "retrieval": {
                    "mrr": (
                        with_reranking.overall_metrics["retrieval"].mrr
                        - without_reranking.overall_metrics["retrieval"].mrr
                    )
                }
            }
            if without_reranking.overall_metrics
            else {}
        )
        return RerankComparisonReport(
            without_reranking=without_reranking,
            with_reranking=with_reranking,
            improvement=improvement,
        )


def _override(app: FastAPI, *, queries: list[EvaluationQuery]) -> _EchoingFakeRetrievalEvaluator:
    evaluator = _EchoingFakeRetrievalEvaluator()
    app.dependency_overrides[get_dataset_loader] = lambda: _FakeDatasetLoader(queries=queries)
    app.dependency_overrides[get_retrieval_evaluator] = lambda: evaluator
    return evaluator


@pytest.fixture
def evaluation_client() -> Iterator[tuple[TestClient, _EchoingFakeRetrievalEvaluator]]:
    app = create_app()
    evaluator = _override(app, queries=[_query("q1"), _query("q2"), _query("q3")])
    with TestClient(app) as client:
        yield client, evaluator


class TestRunEvaluation:
    def test_an_empty_body_runs_the_full_dataset(
        self, evaluation_client: tuple[TestClient, _EchoingFakeRetrievalEvaluator]
    ) -> None:
        client, evaluator = evaluation_client

        response = client.post(_RUN_URL)

        assert response.status_code == 200
        assert evaluator.received is not None
        assert len(evaluator.received) == 3

    def test_query_ids_filters_to_a_subset(
        self, evaluation_client: tuple[TestClient, _EchoingFakeRetrievalEvaluator]
    ) -> None:
        client, evaluator = evaluation_client

        response = client.post(_RUN_URL, json={"query_ids": ["q1", "q3"]})

        assert response.status_code == 200
        assert evaluator.received is not None
        assert {q.query_id for q in evaluator.received} == {"q1", "q3"}

    def test_limit_caps_the_number_of_queries_run(
        self, evaluation_client: tuple[TestClient, _EchoingFakeRetrievalEvaluator]
    ) -> None:
        client, evaluator = evaluation_client

        response = client.post(_RUN_URL, json={"limit": 1})

        assert response.status_code == 200
        assert evaluator.received is not None
        assert len(evaluator.received) == 1

    def test_query_ids_and_limit_combine(
        self, evaluation_client: tuple[TestClient, _EchoingFakeRetrievalEvaluator]
    ) -> None:
        client, evaluator = evaluation_client

        response = client.post(_RUN_URL, json={"query_ids": ["q1", "q2", "q3"], "limit": 2})

        assert response.status_code == 200
        assert evaluator.received is not None
        assert len(evaluator.received) == 2

    def test_an_unmatched_query_id_yields_an_empty_but_valid_run(
        self, evaluation_client: tuple[TestClient, _EchoingFakeRetrievalEvaluator]
    ) -> None:
        client, _evaluator = evaluation_client

        response = client.post(_RUN_URL, json={"query_ids": ["does-not-exist"]})

        assert response.status_code == 200
        body = response.json()
        assert body["dataset_size"] == 0
        assert body["query_results"] == []

    def test_response_includes_summary_and_metrics(
        self, evaluation_client: tuple[TestClient, _EchoingFakeRetrievalEvaluator]
    ) -> None:
        client, _evaluator = evaluation_client

        response = client.post(_RUN_URL)

        body = response.json()
        assert "queries evaluated" in body["summary"]
        assert body["overall_metrics"]["retrieval"]["mrr"] == pytest.approx(0.81)
        assert body["average_latency_seconds"] == pytest.approx(0.01)
        assert len(body["query_results"]) == 3

    def test_response_includes_the_active_model_snapshot(
        self, evaluation_client: tuple[TestClient, _EchoingFakeRetrievalEvaluator]
    ) -> None:
        client, _evaluator = evaluation_client

        response = client.post(_RUN_URL)

        body = response.json()
        assert len(body["models"]) == 1
        assert body["models"][0]["model_name"] == "openai/clip-vit-base-patch32"
        assert body["models"][0]["model_type"] == "image_embedding"
        assert body["models"][0]["version"] == "1.0.0"

    def test_never_returns_a_raw_vector_or_embedding(
        self, evaluation_client: tuple[TestClient, _EchoingFakeRetrievalEvaluator]
    ) -> None:
        client, _evaluator = evaluation_client

        response = client.post(_RUN_URL)

        # "embedding" alone now legitimately appears in `models[].model_type`
        # (e.g. "image_embedding") — Phase 13 metadata, not a raw vector.
        # `"vector"`/`"embedding_vector"` would only appear if an actual
        # embedding array leaked into the response.
        assert "vector" not in response.text
        assert "embedding_vector" not in response.text


class TestCompareReranking:
    def test_an_empty_body_runs_the_full_dataset(
        self, evaluation_client: tuple[TestClient, _EchoingFakeRetrievalEvaluator]
    ) -> None:
        client, evaluator = evaluation_client

        response = client.post(_COMPARE_URL)

        assert response.status_code == 200
        assert evaluator.compare_received is not None
        assert len(evaluator.compare_received) == 3

    def test_query_ids_filters_to_a_subset(
        self, evaluation_client: tuple[TestClient, _EchoingFakeRetrievalEvaluator]
    ) -> None:
        client, evaluator = evaluation_client

        response = client.post(_COMPARE_URL, json={"query_ids": ["q1", "q3"]})

        assert response.status_code == 200
        assert evaluator.compare_received is not None
        assert {q.query_id for q in evaluator.compare_received} == {"q1", "q3"}

    def test_response_includes_both_reports_and_the_improvement(
        self, evaluation_client: tuple[TestClient, _EchoingFakeRetrievalEvaluator]
    ) -> None:
        client, _evaluator = evaluation_client

        response = client.post(_COMPARE_URL)

        body = response.json()
        assert body["without_reranking"]["overall_metrics"]["retrieval"]["mrr"] == pytest.approx(
            0.81
        )
        assert body["with_reranking"]["overall_metrics"]["retrieval"]["mrr"] == pytest.approx(0.90)
        assert body["improvement"]["retrieval"]["mrr"] == pytest.approx(0.09)

    def test_never_returns_a_raw_vector_or_embedding(
        self, evaluation_client: tuple[TestClient, _EchoingFakeRetrievalEvaluator]
    ) -> None:
        client, _evaluator = evaluation_client

        response = client.post(_COMPARE_URL)

        # "embedding" alone now legitimately appears in `models[].model_type`
        # (e.g. "image_embedding") — Phase 13 metadata, not a raw vector.
        # `"vector"`/`"embedding_vector"` would only appear if an actual
        # embedding array leaked into the response.
        assert "vector" not in response.text
        assert "embedding_vector" not in response.text
