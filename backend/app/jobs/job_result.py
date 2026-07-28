"""`JobResult`: the outcome of one execution attempt of a job (Phase 12).

Distinct from `Job` (`base_job.py`) the same way `EvaluationQueryResult`
is distinct from `BenchmarkReport`, or `RecommendationCandidate` from
`RecommendationResult`, elsewhere in this codebase: `Job` is the queued
*unit of work* and its current lifecycle state; `JobResult` is what one
*attempt* at processing it produced. `Job.retry_history` is a list of
these — one entry per attempt, successful or not — so a job's full
retry history (attempt number, what failed, how long it took, when) is
inspectable after the fact, per this phase's own "retry history" and
"log every retry" requirements.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class JobResult(BaseModel):
    """What happened during one execution attempt of a job."""

    attempt: int = Field(ge=1)
    success: bool
    error: str | None = None
    duration_seconds: float = Field(default=0.0, ge=0)
    completed_at: datetime
