"""FastAPI dependency providers for the evaluation framework (Phase 10).

Mirrors `app.dependencies.recommendation.get_recommendation_engine_service`'s
cached-singleton pattern. Both are provided (rather than only
`get_retrieval_evaluator`) because `POST /evaluation/run`
(`app/api/evaluation.py`) needs `DatasetLoader` directly too — to filter
the dataset down to a requested subset *before* handing the filtered
list to `RetrievalEvaluator.evaluate`, which otherwise only knows how to
run either "the whole configured dataset" or "exactly the queries it's
given."
"""

from functools import lru_cache

from app.services.evaluation.dataset_loader import DatasetLoader
from app.services.evaluation.retrieval_evaluator import RetrievalEvaluator


@lru_cache(maxsize=1)
def get_dataset_loader() -> DatasetLoader:
    """Return the process-wide DatasetLoader singleton, building it on first call."""
    return DatasetLoader()


@lru_cache(maxsize=1)
def get_retrieval_evaluator() -> RetrievalEvaluator:
    """Return the process-wide RetrievalEvaluator singleton, building it on first call."""
    return RetrievalEvaluator()
