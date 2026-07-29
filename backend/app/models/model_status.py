"""`ModelStatus`: the lifecycle state of one registered model version (Phase 13).

At most one registered version per `ModelType` is ever `ACTIVE` at a
time (`ModelRegistry.register`/`.activate` enforce this by deactivating
any previously-active version of the same type) — this is the "which
model is active" question the phase's own objective names. `DEPRECATED`
and `EXPERIMENTAL` are recorded but carry no special registry behavior
beyond their label — a deprecated model can still be looked up by
version, an experimental one can still be promoted to `ACTIVE` via
`activate()`; the registry doesn't police *when* a status transition is
appropriate, only *that* at most one `ACTIVE` version exists per type.
"""

from enum import StrEnum


class ModelStatus(StrEnum):
    """Where a registered model version stands in its lifecycle."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"
    EXPERIMENTAL = "experimental"
