"""`ModelVersion`: the semantic-version type every `ModelInfo.version` uses (Phase 13).

A plain `major.minor.patch` string (e.g. `"1.0.0"`), validated once here
rather than duplicating the same pattern on `ModelInfo` and anywhere else
that might need a model version — `ModelRegistry` assigns `"1.0.0"` to
the first version it registers for a given `ModelType`, but a caller
registering a candidate replacement model (before promoting it via
`activate()`) supplies its own, e.g. `"1.1.0"`.

A plain `Annotated[str, ...]` type alias (not a dedicated class) — a
version string doesn't need methods or identity beyond being "a
correctly-shaped string," so a class would be indirection without
benefit, the same reasoning this codebase already applies elsewhere
(see `RecommendationCandidate`'s own docstring on not inventing a type
that mirrors another phase's shape without a genuine need).
"""

from typing import Annotated

from pydantic import Field

ModelVersion = Annotated[
    str,
    Field(
        pattern=r"^\d+\.\d+\.\d+$",
        description="A semantic version string, e.g. '1.0.0'.",
    ),
]
