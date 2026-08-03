"""Shared state passed to every check.

Checks are plain functions taking a `SmokeContext`. Keeping the context in its
own module avoids a cycle: check modules import this, and the runner imports
the check modules.

The context also carries state produced by earlier checks -- most importantly
the products seeded during the pipeline stage, which the AI checks then query.
That ordering dependency is real (nothing can be searched before it is
indexed), so it is modelled explicitly here rather than hidden in globals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from client import SmokeClient


@dataclass
class SeededProduct:
    """A product this run uploaded, and the demo record it came from."""

    key: str
    product_id: str
    job_id: str
    name: str
    #: True when the upload created a new product, False when a matching demo
    #: product already existed and was reused. See `dataset.py` on idempotency.
    created: bool


@dataclass
class SmokeContext:
    """Everything a check needs, and everything earlier checks produced."""

    client: SmokeClient
    #: How long to wait for the async pipeline to finish a product. Separate
    #: from the per-request HTTP timeout: the first upload on a cold
    #: deployment includes a multi-hundred-megabyte model download, which is
    #: slow without being an error.
    pipeline_timeout: float = 600.0
    verbose: bool = False

    #: Populated by the seeding/pipeline checks, consumed by the AI checks.
    seeded: dict[str, SeededProduct] = field(default_factory=dict)
    #: Free-form notes surfaced in the final summary (counts, timings).
    notes: dict[str, Any] = field(default_factory=dict)

    def product_id(self, key: str) -> str:
        """Resolve a demo key to the id it was uploaded under.

        Raises a plain `LookupError` rather than an assertion failure: a check
        asking for a product that was never seeded is a bug in the suite, not
        a finding about the deployment.
        """
        product = self.seeded.get(key)
        if product is None:
            available = ", ".join(sorted(self.seeded)) or "<none seeded>"
            raise LookupError(
                f"Demo product {key!r} was not seeded. Available: {available}"
            )
        return product.product_id
