"""Unit tests for `ModelRegistry`.

Most tests construct with `seed_from_settings=False` so they start from a
known-empty registry and control exactly what's registered; a dedicated
`TestSeeding` class covers the real settings-driven seeding path.
"""

import pytest

from app.core.config import settings
from app.exceptions.errors import (
    ConflictException,
    ModelRegistryException,
    ResourceNotFoundException,
)
from app.models.model_info import ModelInfo
from app.models.model_status import ModelStatus
from app.models.model_type import ModelType
from app.services.model_registry import ModelRegistry


def _model_info(
    *,
    model_type: ModelType = ModelType.IMAGE_EMBEDDING,
    version: str = "1.0.0",
    status: ModelStatus = ModelStatus.ACTIVE,
    model_name: str = "openai/clip-vit-base-patch32",
    dimension: int = 512,
) -> ModelInfo:
    return ModelInfo(
        model_name=model_name,
        version=version,
        model_type=model_type,
        dimension=dimension,
        status=status,
    )


class TestRegister:
    def test_registers_a_new_model(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)
        info = _model_info()

        registered = registry.register(info)

        assert registered == info
        assert registry.get_model(ModelType.IMAGE_EMBEDDING, "1.0.0") == info

    def test_rejects_a_duplicate_version_for_the_same_type(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)
        registry.register(_model_info(version="1.0.0"))

        with pytest.raises(ConflictException):
            registry.register(_model_info(version="1.0.0"))

    def test_the_same_version_is_allowed_across_different_types(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)
        registry.register(_model_info(model_type=ModelType.IMAGE_EMBEDDING, version="1.0.0"))

        # Should not raise - different model_type, so not a duplicate.
        registry.register(
            _model_info(
                model_type=ModelType.TEXT_EMBEDDING,
                version="1.0.0",
                model_name="BAAI/bge-small-en-v1.5",
                dimension=384,
            )
        )

    def test_registering_a_second_active_model_deactivates_the_first(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)
        registry.register(_model_info(version="1.0.0", status=ModelStatus.ACTIVE))

        registry.register(
            _model_info(
                version="1.1.0",
                model_name="openai/clip-vit-large-patch14",
                status=ModelStatus.ACTIVE,
            )
        )

        first = registry.get_model(ModelType.IMAGE_EMBEDDING, "1.0.0")
        second = registry.get_model(ModelType.IMAGE_EMBEDDING, "1.1.0")
        assert first.status is ModelStatus.INACTIVE
        assert second.status is ModelStatus.ACTIVE

    def test_registering_a_non_active_model_does_not_disturb_the_active_one(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)
        registry.register(_model_info(version="1.0.0", status=ModelStatus.ACTIVE))

        registry.register(
            _model_info(
                version="2.0.0",
                model_name="openai/clip-vit-large-patch14",
                status=ModelStatus.EXPERIMENTAL,
            )
        )

        assert registry.get_model(ModelType.IMAGE_EMBEDDING, "1.0.0").status is ModelStatus.ACTIVE
        assert (
            registry.get_model(ModelType.IMAGE_EMBEDDING, "2.0.0").status
            is ModelStatus.EXPERIMENTAL
        )


class TestGetActiveModel:
    def test_returns_the_active_model(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)
        info = _model_info()
        registry.register(info)

        assert registry.get_active_model(ModelType.IMAGE_EMBEDDING) == info

    def test_raises_when_no_model_is_registered_at_all(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)

        with pytest.raises(ResourceNotFoundException):
            registry.get_active_model(ModelType.IMAGE_EMBEDDING)

    def test_raises_when_every_registered_model_is_inactive(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)
        registry.register(_model_info(status=ModelStatus.INACTIVE))

        with pytest.raises(ResourceNotFoundException):
            registry.get_active_model(ModelType.IMAGE_EMBEDDING)


class TestGetModel:
    def test_raises_for_an_unregistered_version(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)

        with pytest.raises(ResourceNotFoundException):
            registry.get_model(ModelType.IMAGE_EMBEDDING, "9.9.9")


class TestListModels:
    def test_lists_every_model_when_no_type_is_given(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)
        registry.register(_model_info(model_type=ModelType.IMAGE_EMBEDDING))
        registry.register(
            _model_info(
                model_type=ModelType.TEXT_EMBEDDING,
                model_name="BAAI/bge-small-en-v1.5",
                dimension=384,
            )
        )

        assert len(registry.list_models()) == 2

    def test_lists_only_the_requested_type(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)
        registry.register(_model_info(model_type=ModelType.IMAGE_EMBEDDING, version="1.0.0"))
        registry.register(
            _model_info(
                model_type=ModelType.IMAGE_EMBEDDING,
                version="1.1.0",
                status=ModelStatus.EXPERIMENTAL,
            )
        )
        registry.register(
            _model_info(
                model_type=ModelType.TEXT_EMBEDDING,
                model_name="BAAI/bge-small-en-v1.5",
                dimension=384,
            )
        )

        image_models = registry.list_models(ModelType.IMAGE_EMBEDDING)

        assert len(image_models) == 2
        assert all(info.model_type is ModelType.IMAGE_EMBEDDING for info in image_models)

    def test_returns_an_empty_list_for_a_type_with_nothing_registered(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)

        assert registry.list_models(ModelType.RERANKER) == []


class TestActivate:
    def test_promotes_the_given_version_to_active(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)
        registry.register(_model_info(version="1.0.0", status=ModelStatus.ACTIVE))
        registry.register(_model_info(version="1.1.0", status=ModelStatus.EXPERIMENTAL))

        activated = registry.activate(ModelType.IMAGE_EMBEDDING, "1.1.0")

        assert activated.status is ModelStatus.ACTIVE
        assert registry.get_active_model(ModelType.IMAGE_EMBEDDING).version == "1.1.0"
        assert registry.get_model(ModelType.IMAGE_EMBEDDING, "1.0.0").status is ModelStatus.INACTIVE

    def test_raises_for_an_unregistered_version(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)

        with pytest.raises(ResourceNotFoundException):
            registry.activate(ModelType.IMAGE_EMBEDDING, "9.9.9")


class TestDeactivate:
    def test_marks_the_version_inactive(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)
        registry.register(_model_info(status=ModelStatus.ACTIVE))

        deactivated = registry.deactivate(ModelType.IMAGE_EMBEDDING, "1.0.0")

        assert deactivated.status is ModelStatus.INACTIVE
        with pytest.raises(ResourceNotFoundException):
            registry.get_active_model(ModelType.IMAGE_EMBEDDING)

    def test_raises_for_an_unregistered_version(self) -> None:
        registry = ModelRegistry(seed_from_settings=False)

        with pytest.raises(ResourceNotFoundException):
            registry.deactivate(ModelType.IMAGE_EMBEDDING, "9.9.9")


class TestSeeding:
    def test_seeds_exactly_one_active_model_per_type(self) -> None:
        registry = ModelRegistry()

        for model_type in ModelType:
            active = registry.get_active_model(model_type)
            assert active.version == "1.0.0"
            assert active.status is ModelStatus.ACTIVE

    def test_seeds_from_the_existing_ai_model_and_reranker_settings(self) -> None:
        registry = ModelRegistry()

        assert registry.get_active_model(ModelType.IMAGE_EMBEDDING).model_name == (
            settings.ai_models.clip_model_name
        )
        assert registry.get_active_model(ModelType.TEXT_EMBEDDING).model_name == (
            settings.ai_models.text_model_name
        )
        assert (
            registry.get_active_model(ModelType.RERANKER).model_name == settings.reranker.model_name
        )

    def test_reranker_dimension_is_one(self) -> None:
        registry = ModelRegistry()

        assert registry.get_active_model(ModelType.RERANKER).dimension == 1

    def test_raises_when_a_configured_model_name_is_blank(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings.ai_models, "clip_model_name", "   ")

        with pytest.raises(ModelRegistryException):
            ModelRegistry()
