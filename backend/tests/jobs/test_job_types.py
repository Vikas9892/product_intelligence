"""Unit tests for `JobType`."""

from app.jobs.job_types import JobType


class TestJobType:
    def test_has_product_processing(self) -> None:
        assert JobType.PRODUCT_PROCESSING.value == "product_processing"
