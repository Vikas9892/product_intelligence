"""`JobType`: which background pipeline a job runs (Phase 12).

Only `PRODUCT_PROCESSING` is implemented this phase (the upload pipeline
— image processing, embeddings, catalog intelligence, vector indexing,
duplicate detection, recommendation cache warm-up); `Job.payload` is a
generic `dict`, not a `PRODUCT_PROCESSING`-specific shape, specifically
so a future job type can be added here without changing `Job` itself —
the "future extensibility" this phase's own spec asks for, the same
"one implemented, room for more" reasoning `RecommendationType` (Phase 9)
already established for `COMPLEMENTARY`.
"""

from enum import StrEnum


class JobType(StrEnum):
    """Which background pipeline a queued job should run."""

    PRODUCT_PROCESSING = "product_processing"
