"""Model schemas: the API contract for `GET /models` (Phase 13).

Deliberately separate from `app.models.model_info.ModelInfo` (the internal
domain model `ModelRegistry` stores) for the same reason `app.schemas.product`
is kept separate from `app.models.product` — see that module's docstring.
"""

from datetime import datetime

from pydantic import BaseModel

from app.models.model_info import ModelInfo


class ModelInfoResponse(BaseModel):
    """API-safe view of `ModelInfo` — metadata only, no runtime inference."""

    model_name: str
    version: str
    model_type: str
    status: str
    dimension: int
    description: str
    provider: str
    created_at: datetime

    @classmethod
    def from_model_info(cls, model_info: ModelInfo) -> "ModelInfoResponse":
        """Build the API-safe view of `model_info`."""
        return cls(
            model_name=model_info.model_name,
            version=model_info.version,
            model_type=model_info.model_type.value,
            status=model_info.status.value,
            dimension=model_info.dimension,
            description=model_info.description,
            provider=model_info.provider,
            created_at=model_info.created_at,
        )
