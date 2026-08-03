"""Seeds the demo catalog and records what was seeded.

Uploads happen here; waiting for the pipeline to finish them is the pipeline
stage's job. Splitting it that way means all eight uploads are in flight
before anything is awaited, so the worker pool's concurrency is actually used
instead of the suite serialising itself.
"""

from __future__ import annotations

import assertions as a
import seeding
from context import SmokeContext
from dataset import CATALOG


def check_seed_catalog(ctx: SmokeContext) -> str:
    """Ensure all eight demo products exist, reusing any already indexed."""
    seeded = seeding.seed_catalog(
        ctx.client, reuse=not ctx.notes.get("force_reseed", False)
    )

    a.require(
        len(seeded) == len(CATALOG),
        f"expected to seed {len(CATALOG)} products, got {len(seeded)}",
    )

    for product in seeded:
        ctx.seeded[product.key] = product

    created = [p for p in seeded if p.created]
    reused = [p for p in seeded if not p.created]
    ctx.notes["seed_created"] = len(created)
    ctx.notes["seed_reused"] = len(reused)

    if not created:
        return f"{len(reused)} products already present, reused (nothing uploaded)"
    if not reused:
        return f"{len(created)} products uploaded"
    return f"{len(created)} uploaded, {len(reused)} reused"
