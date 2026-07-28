"""`Job`: the canonical background-job record (Phase 12).

Named `base_job.py` (matching this codebase's `base_*.py` convention for
a foundational, depended-upon type) even though `Job` is a concrete
Pydantic model, not an abstract interface — there is exactly one job
*shape* today (`JobType.PRODUCT_PROCESSING`, see `job_types.py`'s own
docstring for why), so a class hierarchy of job subtypes would be
speculative. `payload` (a generic, JSON-serializable `dict`) is what
lets a future job type reuse this same record without a new subclass:
only its *contents* differ, not the surrounding lifecycle bookkeeping.

This is the record `BaseQueue`/`RedisQueue` (`app/queue/`) persist and
move between pending/processing/delayed/dead-letter, and that
`ProductWorker` (`app/workers/`) dequeues, updates, and re-enqueues on
retry. Every field Milestone 1 asks for (`job_id`, `product_id`,
`created_at`, `updated_at`, `retry_count`, `status`) is here, plus
`progress`/`current_stage` (Milestone 4's status-endpoint payload) and
`retry_history` (Milestone 5).
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.jobs.job_result import JobResult
from app.jobs.job_status import JobStatus
from app.jobs.job_types import JobType


class Job(BaseModel):
    """A background job's identity, payload, and current lifecycle state."""

    job_id: UUID
    product_id: UUID
    job_type: JobType = JobType.PRODUCT_PROCESSING
    status: JobStatus = JobStatus.PENDING
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    retry_count: int = Field(default=0, ge=0)
    max_retries: int = Field(default=5, ge=0)
    #: `0`-`100`; see `ProductWorker`'s own docstring for why this is
    #: coarse-grained (a handful of checkpoints) rather than tracking
    #: every sub-step inside `ProductService.process_upload` — that
    #: pipeline stays a single, encapsulated call from the worker's
    #: point of view, per this phase's "without modifying existing
    #: business services" requirement.
    progress: int = Field(default=0, ge=0, le=100)
    current_stage: str = ""
    error: str | None = None
    retry_history: list[JobResult] = Field(default_factory=list)
