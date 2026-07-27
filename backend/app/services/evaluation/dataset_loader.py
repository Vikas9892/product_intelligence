"""`DatasetLoader`: reads an evaluation dataset file into validated `EvaluationQuery` objects.

The on-disk dataset (`evaluation/dataset.json` by default — a top-level
resource directory, not part of the importable `app` package; see
`app.core.paths.EVALUATION_DIR`'s own docstring) stays deliberately
minimal, per the phase spec's own literal example:

    {"query": "red running shoes", "expected_products": ["<uuid>", ...]}

Every other field (`task_type`, `product_id`, `is_duplicate`, `query_id`,
`top_k`) is optional per entry — a plain `{"query": ..., "expected_products":
[...]}` entry is a `RETRIEVAL` query by default; `RECOMMENDATION`/
`DUPLICATE` entries add `"task_type"` and `"product_id"` (see
`EvaluationQuery`'s own validation for what each task type requires).
This lets the same flat JSON array describe all three evaluation tasks
Milestone 3 supports, matching the phase spec's "Support: text queries,
image queries (future-ready), recommendation evaluation, duplicate
evaluation" requirement without needing three separate dataset files.
"""

import json
from pathlib import Path

from pydantic import ValidationError

from app.core.logging import get_logger
from app.core.paths import DEFAULT_DATASET_PATH
from app.exceptions.errors import EvaluationException
from app.models.evaluation_query import EvaluationQuery, GroundTruth

logger = get_logger(__name__)


class DatasetLoader:
    """Loads and validates an evaluation dataset file."""

    def __init__(self, *, dataset_path: Path | None = None) -> None:
        self._dataset_path = dataset_path if dataset_path is not None else DEFAULT_DATASET_PATH

    def load(self) -> list[EvaluationQuery]:
        """Load and validate every entry in the configured dataset file.

        Raises `EvaluationException` if the file doesn't exist, isn't
        valid JSON, isn't a JSON array of objects, or any entry fails
        `EvaluationQuery` validation — a malformed dataset fails loudly
        and specifically (naming the offending entry's index/ID) rather
        than silently skipping bad data or failing deep inside whichever
        system later tries to evaluate it.
        """
        if not self._dataset_path.exists():
            raise EvaluationException(f"Evaluation dataset not found at '{self._dataset_path}'.")

        try:
            raw = json.loads(self._dataset_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvaluationException(
                f"Evaluation dataset at '{self._dataset_path}' is not valid JSON."
            ) from exc

        if not isinstance(raw, list):
            raise EvaluationException(
                f"Evaluation dataset at '{self._dataset_path}' must be a JSON array of query objects."
            )

        queries = [self._parse_entry(index, entry) for index, entry in enumerate(raw)]
        logger.info(
            "Evaluation dataset loaded: path=%s, queries=%d", self._dataset_path, len(queries)
        )
        return queries

    def _parse_entry(self, index: int, entry: object) -> EvaluationQuery:
        if not isinstance(entry, dict):
            raise EvaluationException(
                f"Evaluation dataset entry #{index} must be a JSON object, "
                f"got {type(entry).__name__}."
            )

        query_id = entry.get("query_id") or f"query-{index}"
        ground_truth = GroundTruth(
            expected_products=entry.get("expected_products", []),
            is_duplicate=entry.get("is_duplicate"),
        )

        try:
            return EvaluationQuery(
                query_id=str(query_id),
                task_type=entry.get("task_type", "retrieval"),
                text=entry.get("query", entry.get("text")),
                image_path=entry.get("image_path"),
                product_id=entry.get("product_id"),
                ground_truth=ground_truth,
                top_k=entry.get("top_k"),
            )
        except ValidationError as exc:
            raise EvaluationException(
                f"Evaluation dataset entry #{index} ('{query_id}') is invalid: {exc}"
            ) from exc
