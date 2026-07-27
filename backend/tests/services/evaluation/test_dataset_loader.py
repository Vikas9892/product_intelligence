"""Unit tests for `DatasetLoader`."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.exceptions.errors import EvaluationException
from app.models.evaluation_query import EvaluationTaskType
from app.services.evaluation.dataset_loader import DatasetLoader


def _write_dataset(tmp_path: Path, entries: object) -> Path:
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


class TestLoadValidDatasets:
    def test_loads_a_plain_retrieval_entry(self, tmp_path: Path) -> None:
        path = _write_dataset(tmp_path, [{"query": "red running shoes", "expected_products": []}])
        loader = DatasetLoader(dataset_path=path)

        queries = loader.load()

        assert len(queries) == 1
        assert queries[0].task_type is EvaluationTaskType.RETRIEVAL
        assert queries[0].text == "red running shoes"

    def test_loads_a_recommendation_entry(self, tmp_path: Path) -> None:
        product_id = uuid4()
        path = _write_dataset(
            tmp_path,
            [
                {
                    "task_type": "recommendation",
                    "product_id": str(product_id),
                    "expected_products": [str(uuid4())],
                }
            ],
        )
        loader = DatasetLoader(dataset_path=path)

        queries = loader.load()

        assert queries[0].task_type is EvaluationTaskType.RECOMMENDATION
        assert queries[0].product_id == product_id

    def test_loads_a_duplicate_entry(self, tmp_path: Path) -> None:
        product_id = uuid4()
        path = _write_dataset(
            tmp_path,
            [
                {
                    "task_type": "duplicate",
                    "product_id": str(product_id),
                    "expected_products": [],
                    "is_duplicate": True,
                }
            ],
        )
        loader = DatasetLoader(dataset_path=path)

        queries = loader.load()

        assert queries[0].task_type is EvaluationTaskType.DUPLICATE
        assert queries[0].ground_truth.is_duplicate is True

    def test_an_empty_dataset_loads_to_an_empty_list(self, tmp_path: Path) -> None:
        path = _write_dataset(tmp_path, [])
        loader = DatasetLoader(dataset_path=path)

        assert loader.load() == []

    def test_query_id_defaults_to_query_dash_index_when_omitted(self, tmp_path: Path) -> None:
        path = _write_dataset(
            tmp_path,
            [
                {"query": "a", "expected_products": []},
                {"query": "b", "expected_products": []},
            ],
        )
        loader = DatasetLoader(dataset_path=path)

        queries = loader.load()

        assert [q.query_id for q in queries] == ["query-0", "query-1"]

    def test_an_explicit_query_id_is_preserved(self, tmp_path: Path) -> None:
        path = _write_dataset(
            tmp_path, [{"query_id": "custom-id", "query": "a", "expected_products": []}]
        )
        loader = DatasetLoader(dataset_path=path)

        queries = loader.load()

        assert queries[0].query_id == "custom-id"

    def test_top_k_override_is_read_when_present(self, tmp_path: Path) -> None:
        path = _write_dataset(tmp_path, [{"query": "a", "expected_products": [], "top_k": 3}])
        loader = DatasetLoader(dataset_path=path)

        queries = loader.load()

        assert queries[0].top_k == 3


class TestMalformedDatasets:
    def test_a_missing_file_raises_evaluation_exception(self, tmp_path: Path) -> None:
        loader = DatasetLoader(dataset_path=tmp_path / "does-not-exist.json")

        with pytest.raises(EvaluationException, match="not found"):
            loader.load()

    def test_invalid_json_raises_evaluation_exception(self, tmp_path: Path) -> None:
        path = tmp_path / "dataset.json"
        path.write_text("{not valid json", encoding="utf-8")
        loader = DatasetLoader(dataset_path=path)

        with pytest.raises(EvaluationException, match="not valid JSON"):
            loader.load()

    def test_a_top_level_object_instead_of_an_array_raises_evaluation_exception(
        self, tmp_path: Path
    ) -> None:
        path = _write_dataset(tmp_path, {"query": "a", "expected_products": []})
        loader = DatasetLoader(dataset_path=path)

        with pytest.raises(EvaluationException, match="must be a JSON array"):
            loader.load()

    def test_a_non_object_entry_raises_evaluation_exception(self, tmp_path: Path) -> None:
        path = _write_dataset(tmp_path, ["not-an-object"])
        loader = DatasetLoader(dataset_path=path)

        with pytest.raises(EvaluationException, match="must be a JSON object"):
            loader.load()

    def test_a_recommendation_entry_missing_product_id_raises_evaluation_exception(
        self, tmp_path: Path
    ) -> None:
        path = _write_dataset(tmp_path, [{"task_type": "recommendation", "expected_products": []}])
        loader = DatasetLoader(dataset_path=path)

        with pytest.raises(EvaluationException, match="is invalid"):
            loader.load()

    def test_a_retrieval_entry_missing_text_raises_evaluation_exception(
        self, tmp_path: Path
    ) -> None:
        path = _write_dataset(tmp_path, [{"expected_products": []}])
        loader = DatasetLoader(dataset_path=path)

        with pytest.raises(EvaluationException, match="is invalid"):
            loader.load()


class TestDefaultDatasetPath:
    def test_uses_the_default_dataset_path_when_none_is_given(self) -> None:
        loader = DatasetLoader()

        queries = loader.load()

        # The checked-in evaluation/dataset.json ships with exactly these
        # three example entries (one per task type) — see that file.
        assert len(queries) == 3
