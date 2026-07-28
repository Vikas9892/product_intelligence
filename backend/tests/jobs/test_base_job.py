"""Unit tests for `Job`."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.jobs.base_job import Job
from app.jobs.job_result import JobResult
from app.jobs.job_status import JobStatus
from app.jobs.job_types import JobType


def _job(**overrides: object) -> Job:
    now = datetime.now(UTC)
    defaults: dict[str, object] = {
        "job_id": uuid4(),
        "product_id": uuid4(),
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    return Job(**defaults)


class TestJobDefaults:
    def test_defaults(self) -> None:
        job = _job()

        assert job.job_type is JobType.PRODUCT_PROCESSING
        assert job.status is JobStatus.PENDING
        assert job.payload == {}
        assert job.retry_count == 0
        assert job.max_retries == 5
        assert job.progress == 0
        assert job.current_stage == ""
        assert job.error is None
        assert job.retry_history == []

    def test_rejects_progress_above_100(self) -> None:
        with pytest.raises(ValidationError):
            _job(progress=101)

    def test_rejects_a_negative_retry_count(self) -> None:
        with pytest.raises(ValidationError):
            _job(retry_count=-1)


class TestJobConstruction:
    def test_constructs_with_all_fields(self) -> None:
        job_id, product_id = uuid4(), uuid4()
        now = datetime.now(UTC)
        result = JobResult(attempt=1, success=False, error="boom", completed_at=now)

        job = Job(
            job_id=job_id,
            product_id=product_id,
            job_type=JobType.PRODUCT_PROCESSING,
            status=JobStatus.RETRYING,
            payload={"name": "Widget"},
            created_at=now,
            updated_at=now,
            retry_count=1,
            max_retries=3,
            progress=40,
            current_stage="Generating Embeddings",
            error="boom",
            retry_history=[result],
        )

        assert job.job_id == job_id
        assert job.product_id == product_id
        assert job.status is JobStatus.RETRYING
        assert job.payload == {"name": "Widget"}
        assert job.progress == 40
        assert job.current_stage == "Generating Embeddings"
        assert job.retry_history == [result]

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        job = _job(payload={"name": "Widget"})

        dumped = job.model_dump(mode="json")
        restored = Job.model_validate(dumped)

        assert restored == job
