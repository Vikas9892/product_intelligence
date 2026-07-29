"""Internal domain model: `ModelInfo`, one registered version of one AI model (Phase 13).

Built and stored exclusively by `ModelRegistry` (`app/services/
model_registry.py`) — never loads a model itself (that's still
`ModelManager`/`TextModelManager`/`ModelManagerCrossEncoder`'s job); this
is pure metadata, per the phase's own "provide versioning, metadata,
lifecycle management ... while remaining independent from inference
logic."

`dimension` is the embedding output size for `IMAGE_EMBEDDING`/
`TEXT_EMBEDDING` (matching `VectorStoreSettings.image_vector_size`/
`text_vector_size`); a cross-encoder (`RERANKER`) doesn't produce a
fixed-size embedding at all — it scores a query-document pair with a
single scalar — so `RERANKER` entries record `dimension=1` by
convention (documented here rather than silently ambiguous) instead of
making the field optional just for one model type.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.models.model_status import ModelStatus
from app.models.model_type import ModelType
from app.models.model_version import ModelVersion


class ModelInfo(BaseModel):
    """Metadata for one registered version of one AI model."""

    model_name: str = Field(min_length=1)
    version: ModelVersion
    model_type: ModelType
    dimension: int = Field(gt=0)
    description: str = ""
    provider: str = "Hugging Face"
    status: ModelStatus = ModelStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
