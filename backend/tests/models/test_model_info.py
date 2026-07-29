"""Unit tests for `ModelInfo`."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.model_info import ModelInfo
from app.models.model_status import ModelStatus
from app.models.model_type import ModelType


class TestModelInfoDefaults:
    def test_defaults(self) -> None:
        info = ModelInfo(
            model_name="openai/clip-vit-base-patch32",
            version="1.0.0",
            model_type=ModelType.IMAGE_EMBEDDING,
            dimension=512,
        )

        assert info.description == ""
        assert info.provider == "Hugging Face"
        assert info.status is ModelStatus.ACTIVE
        assert info.created_at is not None

    def test_rejects_a_blank_model_name(self) -> None:
        with pytest.raises(ValidationError):
            ModelInfo(
                model_name="",
                version="1.0.0",
                model_type=ModelType.IMAGE_EMBEDDING,
                dimension=512,
            )

    def test_rejects_a_non_positive_dimension(self) -> None:
        with pytest.raises(ValidationError):
            ModelInfo(
                model_name="openai/clip-vit-base-patch32",
                version="1.0.0",
                model_type=ModelType.IMAGE_EMBEDDING,
                dimension=0,
            )

    def test_rejects_a_malformed_version(self) -> None:
        with pytest.raises(ValidationError):
            ModelInfo(
                model_name="openai/clip-vit-base-patch32",
                version="not-a-version",
                model_type=ModelType.IMAGE_EMBEDDING,
                dimension=512,
            )


class TestModelInfoConstruction:
    def test_constructs_with_all_fields(self) -> None:
        created_at = datetime.now(UTC)

        info = ModelInfo(
            model_name="cross-encoder/ms-marco-MiniLM-L-6-v2",
            version="1.0.0",
            model_type=ModelType.RERANKER,
            dimension=1,
            description="MS-MARCO-tuned cross-encoder.",
            provider="Hugging Face",
            status=ModelStatus.EXPERIMENTAL,
            created_at=created_at,
        )

        assert info.model_name == "cross-encoder/ms-marco-MiniLM-L-6-v2"
        assert info.model_type is ModelType.RERANKER
        assert info.dimension == 1
        assert info.description == "MS-MARCO-tuned cross-encoder."
        assert info.status is ModelStatus.EXPERIMENTAL
        assert info.created_at == created_at

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        info = ModelInfo(
            model_name="BAAI/bge-small-en-v1.5",
            version="1.0.0",
            model_type=ModelType.TEXT_EMBEDDING,
            dimension=384,
        )

        dumped = info.model_dump(mode="json")
        restored = ModelInfo.model_validate(dumped)

        assert restored == info
