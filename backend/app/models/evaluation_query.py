"""Internal domain models: one evaluation case (a query/product reference plus its ground truth).

`EvaluationQuery` is the internal, validated shape `DatasetLoader`
(`app/services/evaluation/dataset_loader.py`) produces from the raw
`evaluation/dataset.json` file — deliberately separate from that on-disk
JSON shape (which stays minimal, per the phase spec's own literal
example: `{"query": "...", "expected_products": [...]}`) for the same
reason `ProductCreate` (raw submitted fields) is kept separate from
`Product` (`app/models/product.py`, the internal domain object) — see
that module's docstring.
"""

from enum import StrEnum
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class EvaluationTaskType(StrEnum):
    """Which system one `EvaluationQuery` measures.

    A domain value that travels with the query/result (selected by the
    dataset itself), not a configuration knob — the same "lives in
    `app/models/`, not `app/core/constants.py`" reasoning
    `RecommendationType` (Phase 9) already established.
    """

    RETRIEVAL = "retrieval"
    RECOMMENDATION = "recommendation"
    DUPLICATE = "duplicate"


class GroundTruth(BaseModel):
    """The expected correct outcome for one evaluation query.

    `expected_products` is what `RETRIEVAL`/`RECOMMENDATION` queries are
    scored against (precision/recall/MRR/NDCG all compare retrieved
    products to this set). `is_duplicate` is `DUPLICATE` queries' own
    ground truth instead — whether the referenced `product_id` *should*
    be flagged a duplicate of something in `expected_products` — since
    "was it (in)correctly flagged" isn't a ranking question the way
    retrieval/recommendation are.
    """

    expected_products: list[UUID] = Field(default_factory=list)
    is_duplicate: bool | None = None


class EvaluationQuery(BaseModel):
    """One evaluation case: what to query/check, and what the correct answer is.

    Exactly one of `text`/`image_path`/`product_id` is required,
    depending on `task_type` — validated below so a malformed dataset
    entry fails loudly, at load time, rather than surfacing as a
    confusing failure deep inside whichever system tries to evaluate it.
    """

    query_id: str
    task_type: EvaluationTaskType = EvaluationTaskType.RETRIEVAL
    text: str | None = None
    #: Future-ready (per the phase spec) — image-query evaluation isn't
    #: implemented by `RetrievalEvaluator` yet, but the field exists now
    #: so a dataset can already describe one without a later breaking change.
    image_path: Path | None = None
    product_id: UUID | None = None
    ground_truth: GroundTruth
    #: Overrides `EvaluationSettings.top_k` for this query only.
    top_k: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _validate_required_fields(self) -> "EvaluationQuery":
        if self.task_type is EvaluationTaskType.RETRIEVAL:
            if not (self.text and self.text.strip()) and self.image_path is None:
                raise ValueError(
                    f"query '{self.query_id}': a retrieval query needs 'text' and/or 'image_path'."
                )
        elif self.product_id is None:
            raise ValueError(
                f"query '{self.query_id}': a {self.task_type.value} query needs 'product_id'."
            )
        return self
