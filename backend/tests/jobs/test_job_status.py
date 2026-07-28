"""Unit tests for `JobStatus`."""

from app.jobs.job_status import JobStatus


class TestJobStatus:
    def test_has_the_five_lifecycle_states(self) -> None:
        assert {status.value for status in JobStatus} == {
            "pending",
            "running",
            "completed",
            "failed",
            "retrying",
        }
