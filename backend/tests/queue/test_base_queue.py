"""Unit tests for `BaseQueue`."""

import pytest

from app.queue.base_queue import BaseQueue


class TestBaseQueue:
    def test_cannot_be_instantiated_directly(self) -> None:
        with pytest.raises(TypeError):
            BaseQueue()  # type: ignore[abstract]
