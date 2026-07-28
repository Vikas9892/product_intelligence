"""Job status and dead-letter-queue endpoints (Phase 12).

`GET /jobs/{job_id}` (mounted under `settings.application.api_prefix` by
`app/application.py`, so `/api/v1/jobs/{job_id}`) looks up a background
job's current status/progress/current_stage directly by ID — the
counterpart to `GET /products/{id}/status` (`app/api/products.py`),
which looks the same record up by `product_id` instead. Both return the
identical `JobStatusResponse` shape (see that module's own docstring for
why). `GET /jobs/dead-letter` (Milestone 5's own "never lose a job"
requirement) lists every job that exhausted its retries, so an operator
can inspect *what* failed and *why* (`JobStatusResponse.error`) rather
than it silently disappearing — registered *before* `/{job_id}` so
`"dead-letter"` is never mistaken for a job ID (Starlette matches routes
in registration order; a later `/{job_id}` would otherwise 422 on it
first).

Both routes stay thin adapters, same as every other route in this
codebase: parse the request, delegate to `QueueManager`, shape the
response.
"""

import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.core.logging import get_logger
from app.dependencies.queue import get_queue_manager
from app.exceptions.errors import ResourceNotFoundException
from app.queue.queue_manager import QueueManager
from app.schemas.job import JobStatusResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get(
    "/dead-letter",
    response_model=list[JobStatusResponse],
    status_code=status.HTTP_200_OK,
    summary="List every job that exhausted its retries",
    description="Returns the current status of every job in the dead-letter queue — "
    "jobs that failed enough times to stop being retried automatically.",
)
async def get_dead_letter_jobs(
    queue_manager: Annotated[QueueManager, Depends(get_queue_manager)],
) -> list[JobStatusResponse]:
    """List every dead-lettered job's current record, oldest first."""
    job_ids = await queue_manager.get_dead_letter_job_ids()
    jobs = await asyncio.gather(*(queue_manager.get(job_id) for job_id in job_ids))

    logger.info("Dead-letter queue listed: count=%d", len(job_ids))
    return [JobStatusResponse.from_job(job) for job in jobs if job is not None]


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a background job's current status",
    description="Returns a queued/running/completed/failed background job's current "
    "status, progress, and current stage.",
)
async def get_job(
    job_id: UUID, queue_manager: Annotated[QueueManager, Depends(get_queue_manager)]
) -> JobStatusResponse:
    """Look up `job_id`'s current record.

    Raises `ResourceNotFoundException` (404) if no job with `job_id` was
    ever queued.
    """
    job = await queue_manager.get(job_id)
    if job is None:
        raise ResourceNotFoundException(f"Job '{job_id}' was not found.", resource="job")

    logger.info("Job status requested: job_id=%s, status=%s", job_id, job.status.value)
    return JobStatusResponse.from_job(job)
