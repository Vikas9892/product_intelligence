"""Unit tests for the Phase 18 model-analytics domain models."""

import pytest
from pydantic import ValidationError

from app.models.model_analytics import ModelAnalytics, ModelUsage
from app.models.usage_metrics import UsageMetrics


class TestModelUsage:
    def test_defaults(self) -> None:
        usage = ModelUsage(model_type="image_embedding")
        assert usage.active_model is None
        assert usage.registered_versions == 0

    def test_rejects_negative_versions(self) -> None:
        with pytest.raises(ValidationError):
            ModelUsage(model_type="image_embedding", registered_versions=-1)


class TestModelAnalytics:
    def test_constructs(self) -> None:
        analytics = ModelAnalytics(
            models=[
                ModelUsage(
                    model_type="reranker",
                    active_model="cross-encoder/x",
                    active_version="1.0.0",
                    status="active",
                    registered_versions=2,
                )
            ],
            window=UsageMetrics(searches=5),
            window_days=7,
        )
        assert analytics.models[0].active_version == "1.0.0"
        assert analytics.window.searches == 5
