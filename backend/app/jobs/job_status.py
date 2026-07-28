"""`JobStatus`: the lifecycle states of one background job (Phase 12).

A job moves `PENDING` (queued, not yet dequeued) -> `RUNNING` (a worker
has it) -> `COMPLETED`, or, on failure, `RETRYING` (a worker will attempt
it again after a backoff delay) -> ... -> either `RUNNING` again or
`FAILED` (retries exhausted, moved to the dead-letter queue). There is no
"cancelled" state — cancellation isn't a requirement this phase asks for,
and inventing one unused would be speculative.
"""

from enum import StrEnum


class JobStatus(StrEnum):
    """Where a job currently stands in its processing lifecycle."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
