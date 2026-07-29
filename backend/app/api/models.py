"""Model registry metadata endpoints (Phase 13).

`GET /models` (mounted under `settings.application.api_prefix` by
`app/application.py`, so `/api/v1/models`) lists every registered model
across every `ModelType`. `GET /models/{type}` narrows that list to one
type; `GET /models/{type}/active` returns just that type's currently
active model. All three are metadata-only reads against `ModelRegistry` —
no model is ever loaded to answer them (see that service's own docstring:
"This service never loads models").

Thin adapters, same as every other route in this codebase: parse the
request, delegate to `ModelRegistry`, shape the response.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.logging import get_logger
from app.dependencies.model_registry import get_model_registry
from app.models.model_type import ModelType
from app.schemas.model import ModelInfoResponse
from app.services.model_registry import ModelRegistry

logger = get_logger(__name__)

router = APIRouter(prefix="/models", tags=["models"])


@router.get(
    "",
    response_model=list[ModelInfoResponse],
    status_code=status.HTTP_200_OK,
    summary="List every registered model",
    description="Returns every registered model version across every model type.",
)
async def list_models(
    registry: Annotated[ModelRegistry, Depends(get_model_registry)],
) -> list[ModelInfoResponse]:
    """List every registered model, across all types."""
    models = registry.list_models()

    logger.info("Models listed: count=%d", len(models))
    return [ModelInfoResponse.from_model_info(model_info) for model_info in models]


@router.get(
    "/{type}",
    response_model=list[ModelInfoResponse],
    status_code=status.HTTP_200_OK,
    summary="List every registered model of one type",
    description="Returns every registered model version for the given model type.",
)
async def list_models_by_type(
    type: ModelType, registry: Annotated[ModelRegistry, Depends(get_model_registry)]
) -> list[ModelInfoResponse]:
    """List every registered model of `type`."""
    models = registry.list_models(type)

    logger.info("Models listed: type=%s, count=%d", type.value, len(models))
    return [ModelInfoResponse.from_model_info(model_info) for model_info in models]


@router.get(
    "/{type}/active",
    response_model=ModelInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the active model for one type",
    description="Returns the currently active model for the given model type.",
)
async def get_active_model(
    type: ModelType, registry: Annotated[ModelRegistry, Depends(get_model_registry)]
) -> ModelInfoResponse:
    """Return the currently active model for `type`.

    Raises `ResourceNotFoundException` (404) if none is active.
    """
    model_info = registry.get_active_model(type)

    logger.info("Active model requested: type=%s, version=%s", type.value, model_info.version)
    return ModelInfoResponse.from_model_info(model_info)
