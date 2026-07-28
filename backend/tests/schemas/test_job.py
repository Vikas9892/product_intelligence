"""Unit tests for the job schemas."""

from datetime import UTC, datetime
from uuid import uuid4

from app.jobs.base_job import Job
from app.jobs.job_status import JobStatus
from app.schemas.job import JobStatusResponse


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


class TestJobStatusResponseFromJob:
    def test_maps_every_field(self) -> None:
        job = _job(
            status=JobStatus.RUNNING,
            progress=60,
            current_stage="Generating Embeddings",
            retry_count=1,
            max_retries=5,
            error="transient failure",
        )

        response = JobStatusResponse.from_job(job)

        assert response.job_id == job.job_id
        assert response.product_id == job.product_id
        assert response.status == "running"
        assert response.progress == 60
        assert response.current_stage == "Generating Embeddings"
        assert response.retry_count == 1
        assert response.max_retries == 5
        assert response.error == "transient failure"
        assert response.created_at == job.created_at
        assert response.updated_at == job.updated_at

    def test_never_exposes_payload_or_job_type(self) -> None:
        job = _job(payload={"product": {"name": "Widget"}})

        response = JobStatusResponse.from_job(job)

        assert "payload" not in response.model_dump()
        assert "job_type" not in response.model_dump()

    def test_round_trips_through_model_dump_and_validate(self) -> None:
        response = JobStatusResponse.from_job(_job())

        dumped = response.model_dump(mode="json")
        restored = JobStatusResponse.model_validate(dumped)

        assert restored == response
