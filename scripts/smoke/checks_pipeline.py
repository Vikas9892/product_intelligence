"""Verifies the asynchronous product pipeline end to end.

The path under test is the real one:

    upload -> 202 + job id -> queued -> worker -> model inference -> completed
           -> product is searchable

Every step is observed through public endpoints. Nothing here inspects Redis
or Qdrant, so the same checks run unchanged against a deployment where those
are not reachable.

Two things this deliberately does not do. It never sleeps for a fixed period
and then assumes success -- job status is pollable, so it is polled, and the
suite finishes as soon as the work does rather than on a timer someone tuned
once. And it asserts nothing about *how* the work happened: not the stage
names, not the retry count, not which worker took it. Those are
implementation details that would make this fail on a refactor that broke
nothing.
"""

from __future__ import annotations

import time

import assertions as a
import seeding
from client import SmokeClient
from context import SmokeContext
from dataset import BY_KEY

#: Polling interval bounds. Starts tight so a fast deployment finishes fast,
#: then eases off so a slow one (a cold model download can take minutes) is
#: not hammered with hundreds of requests while it works.
_POLL_START_SECONDS = 1.0
_POLL_MAX_SECONDS = 5.0
_POLL_GROWTH = 1.5

#: Terminal states reported by GET /products/{id}/status.
_DONE = "completed"
_FAILED = "failed"


def _status(client: SmokeClient, product_id: str) -> dict[str, object]:
    response = client.get(client.api(f"/products/{product_id}/status"))
    a.status_is(response, 200)
    payload = a.is_object(response.json(), context=f"status({product_id})")
    a.has_keys(
        payload,
        ("job_id", "product_id", "status", "progress"),
        context=f"status({product_id})",
    )
    return payload


def _describe_stuck(pending: dict[str, dict[str, object]]) -> str:
    """Render what each unfinished product was doing when time ran out.

    This is the whole value of the timeout path. "Timed out after 600s" tells
    an operator nothing; "3 products stuck at progress=0, stage=None,
    retry_count=0" says the queue is not being consumed, which is a different
    problem from "stuck at 80% in caching" and points somewhere different.
    """
    lines = []
    for key, payload in sorted(pending.items()):
        lines.append(
            f"      {key}: status={payload.get('status')} "
            f"progress={payload.get('progress')} "
            f"stage={payload.get('current_stage')} "
            f"retries={payload.get('retry_count')} "
            f"error={payload.get('error')}"
        )
    return "\n".join(lines)


def check_pipeline_completes(ctx: SmokeContext) -> str:
    """Every product uploaded this run reaches `completed` within the budget.

    Products reused from an earlier run are skipped: they have no job from
    this run to wait on, and their presence in the index already proves they
    completed.
    """
    waiting = {p.key: p for p in ctx.seeded.values() if p.created}
    if not waiting:
        return (
            f"{len(ctx.seeded)} products already processed (nothing uploaded this run)"
        )

    deadline = time.monotonic() + ctx.pipeline_timeout
    interval = _POLL_START_SECONDS
    last_seen: dict[str, dict[str, object]] = {}
    started = time.monotonic()
    completed: dict[str, float] = {}

    while waiting and time.monotonic() < deadline:
        for key in list(waiting):
            payload = _status(ctx.client, waiting[key].product_id)
            last_seen[key] = payload
            state = payload.get("status")

            if state == _DONE:
                completed[key] = time.monotonic() - started
                del waiting[key]
            elif state == _FAILED:
                # Terminal. Waiting out the remaining budget would delay the
                # report without changing it.
                a.fail(
                    f"Product {key!r} failed processing: {payload.get('error')!r} "
                    f"(retries={payload.get('retry_count')}, "
                    f"stage={payload.get('current_stage')})"
                )

        if waiting:
            time.sleep(min(interval, max(0.0, deadline - time.monotonic())))
            interval = min(interval * _POLL_GROWTH, _POLL_MAX_SECONDS)

    if waiting:
        a.fail(
            f"{len(waiting)} of {len(completed) + len(waiting)} product(s) did not finish "
            f"within {ctx.pipeline_timeout:.0f}s. Last known state:\n"
            + _describe_stuck({k: last_seen.get(k, {}) for k in waiting})
            + "\n      A first upload on a cold deployment includes the CLIP and BGE "
            "download (~730 MB); raise --pipeline-timeout if that is what this is."
        )

    slowest = max(completed.values()) if completed else 0.0
    ctx.notes["pipeline_seconds"] = round(slowest, 1)
    return f"{len(completed)} product(s) processed, slowest {slowest:.0f}s"


def check_job_records(ctx: SmokeContext) -> str:
    """The job endpoint agrees with the product status endpoint.

    Two public views onto the same work; a deployment where they disagree has
    a real consistency problem, and the frontend polls one of them.
    """
    checked = 0
    for product in ctx.seeded.values():
        if not product.job_id:
            continue  # reused product: no job from this run to look up

        response = ctx.client.get(ctx.client.api(f"/jobs/{product.job_id}"))
        a.status_is(response, 200)
        payload = a.is_object(response.json(), context=f"job({product.job_id})")
        a.has_keys(payload, ("job_id", "status"), context=f"job({product.job_id})")
        a.require(
            payload["job_id"] == product.job_id,
            f"GET /jobs/{product.job_id} returned job_id={payload['job_id']!r}",
        )
        a.require(
            payload["status"] == _DONE,
            f"job {product.job_id} reports status={payload['status']!r} but the product "
            f"status endpoint reported completed -- the two views disagree",
        )
        checked += 1

    if checked == 0:
        return "no jobs from this run (catalog reused)"
    return f"{checked} job record(s) consistent with product status"


def check_no_dead_letters(ctx: SmokeContext) -> str:
    """No demo product exhausted its retries.

    Scoped to this run's products rather than asserting a globally empty
    queue. The dead-letter queue is deployment-wide state: on a shared
    staging environment it may legitimately hold somebody else's failed job,
    and failing the suite for that would be a false alarm about a healthy
    deployment. Unrelated entries are reported, not asserted on.
    """
    response = ctx.client.get(ctx.client.api("/jobs/dead-letter"))
    a.status_is(response, 200)
    entries = a.is_list(response.json(), context="/jobs/dead-letter")

    ours = {p.product_id for p in ctx.seeded.values()}
    mine = [
        e for e in entries if isinstance(e, dict) and str(e.get("product_id")) in ours
    ]
    if mine:
        # Built inside the branch, not passed to `require` as an f-string:
        # the message indexes mine[0], and an eagerly-evaluated argument
        # raises IndexError on the healthy path where the list is empty.
        first = mine[0]
        a.fail(
            f"{len(mine)} demo product(s) exhausted their retries and are in the "
            f"dead-letter queue. First: product_id={first.get('product_id')} "
            f"error={first.get('error')!r} retries={first.get('retry_count')}"
        )

    others = len(entries) - len(mine)
    if others:
        return f"no demo products ({others} unrelated entr{'y' if others == 1 else 'ies'} present)"
    return "empty"


def check_products_searchable(ctx: SmokeContext) -> str:
    """Every seeded product can be found by name.

    This is the step that proves indexing actually happened. A job can report
    `completed` while the vector upsert silently did nothing, and the only
    externally visible symptom would be a product that exists but can never
    be found.
    """
    missing: list[str] = []
    for key, seeded in sorted(ctx.seeded.items()):
        product = BY_KEY[key]
        found = seeding.find_existing(ctx.client, product)
        if found is None:
            missing.append(key)
        elif found != seeded.product_id:
            # Not a failure. Re-running against an environment that was seeded
            # before will legitimately match an earlier copy of the same
            # product, and that is still proof it is indexed and findable.
            mismatched = ctx.notes.setdefault("search_id_mismatch", [])
            if isinstance(mismatched, list):
                mismatched.append(key)

    if missing:
        a.fail(
            f"{len(missing)} completed product(s) are not findable by search: "
            f"{', '.join(missing)}. Their jobs reported completed, so indexing "
            f"succeeded without the vectors becoming queryable."
        )
    return f"all {len(ctx.seeded)} products findable by name"
