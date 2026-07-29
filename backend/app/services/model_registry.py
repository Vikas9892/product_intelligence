"""`ModelRegistry`: tracks which AI model version is active per `ModelType` (Phase 13).

Pure metadata bookkeeping — this class never loads a model, never calls
Hugging Face, never touches `ModelManager`/`TextModelManager`/
`ModelManagerCrossEncoder` at all. Those managers still own *loading*;
this registry owns *which model name a caller should ask them to load*
(see the phase's own architecture diagram: "The registry will manage
which model should be loaded"). `CLIPEmbeddingService`/
`SentenceTransformerEmbeddingService`/`CrossEncoderService` (Milestone 3)
resolve their default model name through `get_active_model` instead of
reading `settings.ai_models.*`/`settings.reranker.model_name` directly.

**Seeding.** At construction, the registry registers exactly one version
(`"1.0.0"`, `status=ACTIVE`) per `ModelType`, using this project's
*existing* settings (`AIModelSettings.clip_model_name`/`text_model_name`,
`RerankerSettings.model_name`) — not new, separate `IMAGE_MODEL`/
`TEXT_MODEL`/`RERANK_MODEL` env vars, since those settings already are
the single source of truth every model-loading service already reads
from; adding parallel flat env vars for the same three values would just
be a second, disagreeing way to configure them. "Registry validates
these on startup" (the phase's own requirement) means exactly this
seeding step: a blank configured model name raises `ModelRegistryException`
immediately, rather than deferring the failure to whenever a model is
first actually loaded.

**Concurrency.** Every method here is synchronous, in-memory, and has no
`await` point — in this codebase's single-threaded-event-loop model that
makes each call atomic with respect to every other coroutine (no
interleaving is possible without an `await`), the same reasoning
`DuplicateDetectionService`/`HybridSearchService` already document for
why *they* need no explicit lock either. This is unlike
`TextModelManager`/`ModelManagerCrossEncoder`, which really do need a
lock, because their loads run inside `run_in_threadpool` — genuine
OS-thread parallelism this registry's callers never trigger.
"""

from app.core.config import settings
from app.core.logging import get_logger
from app.exceptions.errors import (
    ConflictException,
    ModelRegistryException,
    ResourceNotFoundException,
)
from app.models.model_info import ModelInfo
from app.models.model_status import ModelStatus
from app.models.model_type import ModelType

logger = get_logger(__name__)

#: Every model type seeds at this version — the "first" registered
#: version of each type, per the phase's own "1.0.0"-style versioning.
_INITIAL_VERSION = "1.0.0"

#: A cross-encoder scores a query-document pair; it has no fixed-size
#: embedding output. `1` documents "a single scalar relevance score"
#: rather than leaving `ModelInfo.dimension` mysteriously set to some
#: unrelated number for `RERANKER` entries.
_RERANKER_DIMENSION = 1


class ModelRegistry:
    """Tracks registered model versions and which one is active, per `ModelType`."""

    def __init__(self, *, seed_from_settings: bool = True) -> None:
        self._models: dict[ModelType, dict[str, ModelInfo]] = {
            model_type: {} for model_type in ModelType
        }
        if seed_from_settings:
            self._seed_from_settings()

    def register(self, model_info: ModelInfo) -> ModelInfo:
        """Register `model_info` as a new version of its `model_type`.

        Raises `ConflictException` (409) if that exact `(model_type,
        version)` pair is already registered. If `model_info.status` is
        `ACTIVE`, any previously-active version of the same type is
        demoted to `INACTIVE` first — at most one `ACTIVE` version exists
        per type at any time.
        """
        by_version = self._models[model_info.model_type]
        if model_info.version in by_version:
            raise ConflictException(
                f"Model '{model_info.model_name}' version '{model_info.version}' is "
                f"already registered for '{model_info.model_type.value}'.",
                details={"model_type": model_info.model_type.value, "version": model_info.version},
            )

        if model_info.status is ModelStatus.ACTIVE:
            self._deactivate_all(model_info.model_type)
        by_version[model_info.version] = model_info

        logger.info(
            "Model registered: type=%s, name=%s, version=%s, status=%s",
            model_info.model_type.value,
            model_info.model_name,
            model_info.version,
            model_info.status.value,
        )
        return model_info

    def get_active_model(self, model_type: ModelType) -> ModelInfo:
        """Return the currently-`ACTIVE` model for `model_type`.

        Raises `ResourceNotFoundException` (404) if none is active
        (every type has one after seeding, but all of a type's versions
        could have been explicitly `deactivate()`d).
        """
        active = [
            info for info in self._models[model_type].values() if info.status is ModelStatus.ACTIVE
        ]
        if not active:
            raise ResourceNotFoundException(
                f"No active model registered for '{model_type.value}'.", resource="model"
            )
        return active[0]

    def get_model(self, model_type: ModelType, version: str) -> ModelInfo:
        """Return the registered `model_type` model at `version`.

        Raises `ResourceNotFoundException` (404) if no such version was
        ever registered.
        """
        model_info = self._models[model_type].get(version)
        if model_info is None:
            raise ResourceNotFoundException(
                f"No '{model_type.value}' model registered with version '{version}'.",
                resource="model",
            )
        return model_info

    def list_models(self, model_type: ModelType | None = None) -> list[ModelInfo]:
        """Return every registered model, optionally restricted to one `model_type`."""
        if model_type is not None:
            return list(self._models[model_type].values())
        return [info for by_version in self._models.values() for info in by_version.values()]

    def activate(self, model_type: ModelType, version: str) -> ModelInfo:
        """Promote `version` of `model_type` to `ACTIVE`, demoting any previously-active version.

        Raises `ResourceNotFoundException` (404) if `version` was never
        registered.
        """
        model_info = self.get_model(model_type, version)
        self._deactivate_all(model_type)
        activated = model_info.model_copy(update={"status": ModelStatus.ACTIVE})
        self._models[model_type][version] = activated
        logger.info(
            "Model activated: type=%s, name=%s, version=%s",
            model_type.value,
            activated.model_name,
            version,
        )
        return activated

    def deactivate(self, model_type: ModelType, version: str) -> ModelInfo:
        """Mark `version` of `model_type` as `INACTIVE`.

        Raises `ResourceNotFoundException` (404) if `version` was never
        registered.
        """
        model_info = self.get_model(model_type, version)
        deactivated = model_info.model_copy(update={"status": ModelStatus.INACTIVE})
        self._models[model_type][version] = deactivated
        logger.info(
            "Model deactivated: type=%s, name=%s, version=%s",
            model_type.value,
            deactivated.model_name,
            version,
        )
        return deactivated

    def _deactivate_all(self, model_type: ModelType) -> None:
        by_version = self._models[model_type]
        for version, info in list(by_version.items()):
            if info.status is ModelStatus.ACTIVE:
                by_version[version] = info.model_copy(update={"status": ModelStatus.INACTIVE})

    def _seed_from_settings(self) -> None:
        seeds = (
            (
                ModelType.IMAGE_EMBEDDING,
                settings.ai_models.clip_model_name,
                settings.vector_store.image_vector_size,
            ),
            (
                ModelType.TEXT_EMBEDDING,
                settings.ai_models.text_model_name,
                settings.vector_store.text_vector_size,
            ),
            (ModelType.RERANKER, settings.reranker.model_name, _RERANKER_DIMENSION),
        )
        for model_type, model_name, dimension in seeds:
            if not model_name or not model_name.strip():
                raise ModelRegistryException(
                    f"No model name configured for '{model_type.value}' — startup "
                    "validation failed."
                )
            self.register(
                ModelInfo(
                    model_name=model_name,
                    version=_INITIAL_VERSION,
                    model_type=model_type,
                    dimension=dimension,
                )
            )
