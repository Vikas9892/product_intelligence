"""Unit tests for `JobResult`."""

from datetime import UTC, datetime

from app.jobs.job_result import JobResult


class TestJobResult:
    def test_constructs_a_successful_result(self) -> None:
        result = JobResult(
            attempt=1, success=True, duration_seconds=1.5, completed_at=datetime.now(UTC)
        )

        assert result.attempt == 1
        assert result.success is True
        assert result.error is None
        assert result.duration_seconds == 1.5

    def test_constructs_a_failed_result_with_an_error(self) -> None:
        result = JobResult(attempt=2, success=False, error="boom", completed_at=datetime.now(UTC))

        assert result.success is False
        assert result.error == "boom"

    def test_duration_defaults_to_zero(self) -> None:
        result = JobResult(attempt=1, success=True, completed_at=datetime.now(UTC))

        assert result.duration_seconds == 0.0

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        result = JobResult(
            attempt=3,
            success=False,
            error="timeout",
            duration_seconds=2.0,
            completed_at=datetime.now(UTC),
        )

        dumped = result.model_dump(mode="json")
        restored = JobResult.model_validate(dumped)

        assert restored == result
