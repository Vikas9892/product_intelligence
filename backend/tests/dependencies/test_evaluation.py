"""Unit tests for the evaluation dependency providers."""

from app.dependencies.evaluation import get_dataset_loader, get_retrieval_evaluator
from app.services.evaluation.dataset_loader import DatasetLoader
from app.services.evaluation.retrieval_evaluator import RetrievalEvaluator


class TestGetDatasetLoader:
    def test_returns_a_dataset_loader_instance(self) -> None:
        get_dataset_loader.cache_clear()

        loader = get_dataset_loader()

        assert isinstance(loader, DatasetLoader)

    def test_returns_a_cached_singleton(self) -> None:
        get_dataset_loader.cache_clear()

        first = get_dataset_loader()
        second = get_dataset_loader()

        assert first is second


class TestGetRetrievalEvaluator:
    def test_returns_a_retrieval_evaluator_instance(self) -> None:
        get_retrieval_evaluator.cache_clear()

        evaluator = get_retrieval_evaluator()

        assert isinstance(evaluator, RetrievalEvaluator)

    def test_returns_a_cached_singleton(self) -> None:
        get_retrieval_evaluator.cache_clear()

        first = get_retrieval_evaluator()
        second = get_retrieval_evaluator()

        assert first is second

    def test_cache_clear_forces_a_fresh_instance(self) -> None:
        get_retrieval_evaluator.cache_clear()
        first = get_retrieval_evaluator()

        get_retrieval_evaluator.cache_clear()
        second = get_retrieval_evaluator()

        assert first is not second
