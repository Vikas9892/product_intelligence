"""Internal domain model: `AnalyticsEvent`, the operational events analytics counts (Phase 18).

The fixed vocabulary of business events the analytics layer tallies into
daily buckets — one product upload, one duplicate check, one
recommendation request, one search. A `StrEnum` (like `PricingStrategy`/
`DuplicateDetectionMode`) so the value is both the code and the Redis
bucket key segment, and adding an event type is a one-line change every
reader picks up.
"""

from enum import StrEnum


class AnalyticsEvent(StrEnum):
    """A countable operational event, tallied per day by the analytics layer."""

    UPLOAD = "upload"
    DUPLICATE_CHECK = "duplicate_check"
    RECOMMENDATION = "recommendation"
    SEARCH = "search"
