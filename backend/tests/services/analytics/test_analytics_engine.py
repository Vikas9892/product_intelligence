"""Unit tests for `AnalyticsEngine` (fakeredis repository + seeded registry)."""

from datetime import date

from fakeredis import aioredis as fake_aioredis

from app.models.analytics_event import AnalyticsEvent
from app.models.model_info import ModelInfo
from app.models.model_status import ModelStatus
from app.models.model_type import ModelType
from app.repositories.analytics_repository import AnalyticsRepository
from app.services.analytics.analytics_engine import AnalyticsEngine
from app.services.model_registry import ModelRegistry

_END = date(2026, 1, 10)


def _registry_with_active_models() -> ModelRegistry:
    registry = ModelRegistry(seed_from_settings=False)
    registry.register(
        ModelInfo(
            model_name="clip",
            version="1.0.0",
            model_type=ModelType.IMAGE_EMBEDDING,
            dimension=512,
            status=ModelStatus.ACTIVE,
        )
    )
    registry.register(
        ModelInfo(
            model_name="clip-exp",
            version="1.1.0",
            model_type=ModelType.IMAGE_EMBEDDING,
            dimension=512,
            status=ModelStatus.EXPERIMENTAL,
        )
    )
    return registry


async def _engine(*, window_days: int = 7) -> tuple[AnalyticsEngine, AnalyticsRepository]:
    repo = AnalyticsRepository(redis_client=fake_aioredis.FakeRedis(decode_responses=True))
    engine = AnalyticsEngine(
        repository=repo, model_registry=_registry_with_active_models(), window_days=window_days
    )
    return engine, repo


class TestUsage:
    async def test_sums_events_over_the_window(self) -> None:
        engine, repo = await _engine()
        await repo.record_event(AnalyticsEvent.UPLOAD, day=_END)
        await repo.record_event(AnalyticsEvent.UPLOAD, day=date(2026, 1, 9))
        await repo.record_event(AnalyticsEvent.SEARCH, day=_END)

        usage = await engine.usage(days=7, end=_END)

        assert usage.uploads == 2
        assert usage.searches == 1
        assert usage.recommendations == 0

    async def test_averages_processing_latency(self) -> None:
        engine, repo = await _engine()
        await repo.record_latency(2.0, day=_END)
        await repo.record_latency(4.0, day=_END)

        usage = await engine.usage(days=7, end=_END)

        assert usage.average_processing_seconds == 3.0

    async def test_a_day_outside_the_window_is_excluded(self) -> None:
        engine, repo = await _engine(window_days=2)
        await repo.record_event(AnalyticsEvent.UPLOAD, day=date(2026, 1, 1))  # 9 days before end

        usage = await engine.usage(days=2, end=_END)

        assert usage.uploads == 0


class TestDashboard:
    async def test_reports_today_window_and_active_models(self) -> None:
        engine, _repo = await _engine(window_days=7)

        summary = await engine.dashboard()

        assert summary.window_days == 7
        assert summary.active_models == 1  # one ACTIVE, one EXPERIMENTAL


class TestModelAnalytics:
    async def test_reports_active_versions_and_counts_per_type(self) -> None:
        engine, _repo = await _engine()

        analytics = await engine.model_analytics()

        by_type = {m.model_type: m for m in analytics.models}
        image = by_type["image_embedding"]
        assert image.active_model == "clip"
        assert image.active_version == "1.0.0"
        assert image.status == "active"
        assert image.registered_versions == 2  # one ACTIVE + one EXPERIMENTAL
        # A type with no registered model reports None.
        assert by_type["reranker"].active_model is None
        assert by_type["reranker"].registered_versions == 0


class TestReport:
    async def test_labels_the_date_range(self) -> None:
        engine, _repo = await _engine()

        report = await engine.report(days=7, period="last_7_days", end=_END)

        assert report.period == "last_7_days"
        assert report.end_date == _END
        assert report.start_date == date(2026, 1, 4)
