"""Job schemas: the API contract for `GET /jobs/{job_id}`/`GET /products/{id}/status` (Phase 12).

Deliberately separate from `app.jobs.base_job.Job` (the internal domain
model `QueueManager`/`RedisQueue` persist and mutate) for the same reason
`app.schemas.product` is kept separate from `app.models.product` — see
that module's docstring. Never exposes `Job.payload` (the raw submitted
product fields/image metadata a retry needs, not something an API
consumer needs to see) or `Job.job_type` (an internal routing detail).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.jobs.base_job import Job


class JobStatusResponse(BaseModel):
    """Response body for `GET /jobs/{job_id}` and `GET /products/{id}/status`.

    The two routes return the exact same shape — a client that started
    with a `job_id` (from `UploadAcceptedResponse`) or a `product_id`
    (already known from its own upload request) can poll whichever it
    has on hand.
    """

    job_id: UUID
    product_id: UUID
    status: str
    progress: int
    current_stage: str
    retry_count: int
    max_retries: int
    error: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_job(cls, job: Job) -> "JobStatusResponse":
        """Build the API-safe view of `job`."""
        return cls(
            job_id=job.job_id,
            product_id=job.product_id,
            status=job.status.value,
            progress=job.progress,
            current_stage=job.current_stage,
            retry_count=job.retry_count,
            max_retries=job.max_retries,
            error=job.error,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
