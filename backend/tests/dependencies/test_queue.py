"""Unit tests for the `get_queue_manager` dependency provider."""

from app.dependencies.queue import get_queue_manager
from app.queue.queue_manager import QueueManager


class TestGetQueueManager:
    def test_returns_a_queue_manager_instance(self) -> None:
        get_queue_manager.cache_clear()

        manager = get_queue_manager()

        assert isinstance(manager, QueueManager)

    def test_returns_a_cached_singleton(self) -> None:
        get_queue_manager.cache_clear()

        first = get_queue_manager()
        second = get_queue_manager()

        assert first is second

    def test_cache_clear_forces_a_fresh_instance(self) -> None:
        get_queue_manager.cache_clear()
        first = get_queue_manager()

        get_queue_manager.cache_clear()
        second = get_queue_manager()

        assert first is not second
