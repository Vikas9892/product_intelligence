"""Response schemas for the system/health endpoints (`app/api/health.py`).

Kept in `app/schemas/` — not inline in the router module — so the API
*contract* (what a client can rely on) lives in one place independent of
routing/handler logic, matching how every later milestone's request/response
schemas will be organized.
"""

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness probe response: "is the process alive at all?"

    Deliberately minimal — a liveness probe should never do real work (no
    dependency checks); it just proves the ASGI server is accepting
    requests and running application code. See `ReadinessResponse` for the
    "can this instance actually serve traffic?" question.
    """

    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    """Readiness probe response: "can this instance currently serve traffic?"

    `checks` is an empty dict for now — there are no dependencies (database,
    vector store, cache) to check yet. The shape is deliberately a mapping
    of check-name to boolean so later milestones can add entries
    (`{"database": True, "vector_store": False}`) without changing the
    response's shape or breaking existing clients.
    """

    status: Literal["ready"] = "ready"
    checks: dict[str, bool] = Field(default_factory=dict)


class VersionResponse(BaseModel):
    """Build/version metadata: what's actually deployed, and where."""

    name: str
    version: str
    environment: str
