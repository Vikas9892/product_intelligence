"""Unit tests for the configuration schema in app.core.settings."""

import pytest
from pydantic import ValidationError

from app.core import paths
from app.core.constants import DuplicateDetectionMode, Environment, LogLevel
from app.core.settings import (
    AIModelSettings,
    ApplicationSettings,
    CatalogIntelligenceSettings,
    DuplicateDetectionSettings,
    HybridSearchSettings,
    RecommendationSettings,
    SecuritySettings,
    Settings,
    StorageSettings,
    VectorStoreSettings,
)


class TestApplicationSettings:
    def test_defaults(self) -> None:
        settings = ApplicationSettings()
        assert settings.environment is Environment.LOCAL
        assert settings.debug is True
        assert settings.port == 8000
        assert settings.trusted_hosts == ["*"]
        assert settings.cors_allowed_origins == []

    def test_rejects_out_of_range_port(self) -> None:
        with pytest.raises(ValidationError):
            ApplicationSettings(port=70000)


class TestStorageSettings:
    def test_defaults(self) -> None:
        settings = StorageSettings()

        assert settings.upload_dir == paths.UPLOAD_DIR
        assert settings.processed_dir == paths.PROCESSED_DIR
        assert settings.max_upload_size_mb == 10
        assert settings.max_image_dimension_px == 8000
        assert settings.processed_image_size_px == 1024

    def test_rejects_a_non_positive_max_image_dimension(self) -> None:
        with pytest.raises(ValidationError):
            StorageSettings(max_image_dimension_px=0)

    def test_rejects_a_non_positive_processed_image_size(self) -> None:
        with pytest.raises(ValidationError):
            StorageSettings(processed_image_size_px=0)


class TestAIModelSettings:
    def test_defaults(self) -> None:
        settings = AIModelSettings()

        assert settings.clip_model_name == "openai/clip-vit-base-patch32"
        assert settings.embedding_device == "auto"
        assert settings.embedding_batch_size == 8
        assert settings.text_model_name == "BAAI/bge-small-en-v1.5"
        assert settings.text_device == "auto"
        assert settings.text_batch_size == 32
        assert settings.text_normalize is True

    def test_rejects_a_non_positive_batch_size(self) -> None:
        with pytest.raises(ValidationError):
            AIModelSettings(embedding_batch_size=0)

    def test_rejects_a_non_positive_text_batch_size(self) -> None:
        with pytest.raises(ValidationError):
            AIModelSettings(text_batch_size=0)


class TestVectorStoreSettings:
    def test_defaults(self) -> None:
        settings = VectorStoreSettings()

        assert settings.url == "http://localhost:6333"
        assert settings.image_collection_name == "product_images"
        assert settings.image_vector_size == 512
        assert settings.text_collection_name == "product_text"
        assert settings.text_vector_size == 384
        assert settings.default_top_k == 10

    def test_rejects_a_non_positive_image_vector_size(self) -> None:
        with pytest.raises(ValidationError):
            VectorStoreSettings(image_vector_size=0)

    def test_rejects_a_non_positive_text_vector_size(self) -> None:
        with pytest.raises(ValidationError):
            VectorStoreSettings(text_vector_size=0)

    def test_rejects_a_non_positive_default_top_k(self) -> None:
        with pytest.raises(ValidationError):
            VectorStoreSettings(default_top_k=0)


class TestHybridSearchSettings:
    def test_defaults(self) -> None:
        settings = HybridSearchSettings()

        assert settings.image_weight == 0.7
        assert settings.text_weight == 0.3

    def test_rejects_a_negative_image_weight(self) -> None:
        with pytest.raises(ValidationError):
            HybridSearchSettings(image_weight=-0.1)

    def test_rejects_a_negative_text_weight(self) -> None:
        with pytest.raises(ValidationError):
            HybridSearchSettings(text_weight=-0.1)


class TestCatalogIntelligenceSettings:
    def test_defaults(self) -> None:
        settings = CatalogIntelligenceSettings()

        assert settings.enabled is True
        assert settings.enable_text_attributes is True
        assert settings.enable_image_attributes is True
        assert settings.attribute_confidence_threshold == 0.60
        assert settings.max_generated_tags == 20
        assert settings.quality_completeness_weight == 0.50
        assert settings.quality_confidence_weight == 0.30
        assert settings.quality_consistency_weight == 0.20

    def test_rejects_a_confidence_threshold_above_one(self) -> None:
        with pytest.raises(ValidationError):
            CatalogIntelligenceSettings(attribute_confidence_threshold=1.1)

    def test_rejects_a_negative_confidence_threshold(self) -> None:
        with pytest.raises(ValidationError):
            CatalogIntelligenceSettings(attribute_confidence_threshold=-0.1)

    def test_rejects_a_non_positive_max_generated_tags(self) -> None:
        with pytest.raises(ValidationError):
            CatalogIntelligenceSettings(max_generated_tags=0)

    def test_rejects_a_negative_quality_weight(self) -> None:
        with pytest.raises(ValidationError):
            CatalogIntelligenceSettings(quality_completeness_weight=-0.1)


class TestDuplicateDetectionSettings:
    def test_defaults(self) -> None:
        settings = DuplicateDetectionSettings()

        assert settings.mode is DuplicateDetectionMode.WARN
        assert settings.threshold == 0.90
        assert settings.top_k == 10
        assert settings.image_weight == 0.35
        assert settings.text_weight == 0.25
        assert settings.metadata_weight == 0.20
        assert settings.attribute_weight == 0.20

    def test_rejects_weights_that_do_not_sum_to_one(self) -> None:
        with pytest.raises(ValidationError, match=r"must sum to 1\.0"):
            DuplicateDetectionSettings(
                image_weight=0.5, text_weight=0.5, metadata_weight=0.5, attribute_weight=0.5
            )

    def test_accepts_custom_weights_that_sum_to_one(self) -> None:
        settings = DuplicateDetectionSettings(
            image_weight=0.4, text_weight=0.3, metadata_weight=0.2, attribute_weight=0.1
        )

        assert settings.image_weight == 0.4

    def test_rejects_a_threshold_above_one(self) -> None:
        with pytest.raises(ValidationError):
            DuplicateDetectionSettings(threshold=1.1)

    def test_rejects_a_non_positive_top_k(self) -> None:
        with pytest.raises(ValidationError):
            DuplicateDetectionSettings(top_k=0)


class TestRecommendationSettings:
    def test_defaults(self) -> None:
        settings = RecommendationSettings()

        assert settings.enabled is True
        assert settings.top_k == 10
        assert settings.diversity_enabled is True
        assert settings.similarity_weight == 0.55
        assert settings.attribute_weight == 0.20
        assert settings.tag_weight == 0.15
        assert settings.quality_weight == 0.10

    def test_rejects_weights_that_do_not_sum_to_one(self) -> None:
        with pytest.raises(ValidationError, match=r"must sum to 1\.0"):
            RecommendationSettings(
                similarity_weight=0.5, attribute_weight=0.5, tag_weight=0.5, quality_weight=0.5
            )

    def test_accepts_custom_weights_that_sum_to_one(self) -> None:
        settings = RecommendationSettings(
            similarity_weight=0.4, attribute_weight=0.3, tag_weight=0.2, quality_weight=0.1
        )

        assert settings.similarity_weight == 0.4

    def test_rejects_a_non_positive_top_k(self) -> None:
        with pytest.raises(ValidationError):
            RecommendationSettings(top_k=0)


class TestSecuritySettings:
    def test_rejects_short_secret_key(self) -> None:
        with pytest.raises(ValidationError, match="at least 16 characters"):
            SecuritySettings(secret_key="too-short")

    def test_accepts_sufficiently_long_secret_key(self) -> None:
        key = "a" * 32
        settings = SecuritySettings(secret_key=key)
        assert settings.secret_key.get_secret_value() == key

    def test_secret_key_is_not_exposed_in_repr(self) -> None:
        settings = SecuritySettings(secret_key="a" * 32)
        assert "a" * 32 not in repr(settings)
        assert "**********" in repr(settings)


class TestSettingsComposition:
    def test_default_local_settings_are_valid(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.application.environment is Environment.LOCAL
        assert settings.application.debug is True
        assert settings.logging.level is LogLevel.INFO
        assert settings.database.url.startswith("sqlite")

    def test_env_vars_override_nested_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APPLICATION__PORT", "9999")
        monkeypatch.setenv("LOGGING__LEVEL", "DEBUG")

        settings = Settings(_env_file=None)

        assert settings.application.port == 9999
        assert settings.logging.level is LogLevel.DEBUG

    def test_production_requires_overridden_secret_key(self) -> None:
        with pytest.raises(ValidationError, match="secret_key must be overridden"):
            Settings(
                _env_file=None,
                application={"environment": "production", "debug": False},
                database={"url": "postgresql://user:pass@host/db"},
            )

    def test_production_rejects_debug_true(self) -> None:
        with pytest.raises(ValidationError, match="debug must be false"):
            Settings(
                _env_file=None,
                application={"environment": "production", "debug": True},
                database={"url": "postgresql://user:pass@host/db"},
                security={"secret_key": "a-properly-long-production-secret-key"},
            )

    def test_production_rejects_sqlite_database(self) -> None:
        with pytest.raises(ValidationError, match="must not be SQLite"):
            Settings(
                _env_file=None,
                application={"environment": "production", "debug": False},
                security={"secret_key": "a-properly-long-production-secret-key"},
            )

    def test_production_rejects_wildcard_trusted_hosts(self) -> None:
        with pytest.raises(ValidationError, match="trusted_hosts must not be the wildcard"):
            Settings(
                _env_file=None,
                application={"environment": "production", "debug": False},
                database={"url": "postgresql://user:pass@host/db"},
                security={"secret_key": "a-properly-long-production-secret-key"},
            )

    def test_production_accepts_a_fully_overridden_config(self) -> None:
        settings = Settings(
            _env_file=None,
            application={
                "environment": "production",
                "debug": False,
                "trusted_hosts": ["api.example.com"],
            },
            database={"url": "postgresql://user:pass@host/db"},
            security={"secret_key": "a-properly-long-production-secret-key"},
        )

        assert settings.application.environment is Environment.PRODUCTION
        assert settings.application.debug is False
