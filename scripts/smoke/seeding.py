"""Seeds the demo catalog through the real upload API.

Nothing here writes to Qdrant or Redis. Products enter the system the same way
a user's would -- `POST /products/upload`, a queued job, a worker -- because a
seeding path that bypassed the pipeline would verify nothing about it.

On idempotency
--------------

The backend exposes no "list products" or "get product by name" endpoint, so
there is no direct way to ask whether a demo product already exists. What it
does expose is search, so seeding looks for an *exact* name-and-brand match
among the search results and reuses that product when it finds one.

That is idempotent as far as the public contract permits, with two honest
limits:

1. A product is only findable once its async job has completed and indexed it.
   Re-seeding while a previous run is still processing will upload again,
   because from the outside the product genuinely is not there yet.

2. Matching is exact on name and brand, not semantic. That is deliberate --
   the catalog contains a near-identical twin pair on purpose, and a fuzzy
   match would collapse them into one product and destroy the very
   relationship the duplicate checks rely on.

Both are properties of the available contract, not oversights, and the runner
reports created-vs-reused counts so the behavior is visible rather than
assumed.
"""

from __future__ import annotations

import assertions as a
from client import SmokeClient, SmokeError
from context import SeededProduct
from dataset import CATALOG, DemoProduct

#: Search depth used when looking for an existing copy. Generous enough that
#: an exact match is not pushed out of the window by an unrelated catalog, and
#: cheap because it is one request per product.
LOOKUP_TOP_K = 25


def find_existing(client: SmokeClient, product: DemoProduct) -> str | None:
    """Return the id of an already-seeded copy, or None.

    Search failures return None rather than raising: an empty or unavailable
    index is a perfectly normal state on a fresh deployment, and the caller's
    correct response either way is to upload.
    """
    try:
        response = client.post_multipart(
            client.api("/products/search"),
            fields={"query": product.name, "top_k": LOOKUP_TOP_K},
        )
    except SmokeError:
        # Most often a timeout, and on a cold deployment that is expected
        # rather than broken: the very first search makes the API download and
        # load the BGE text model (~130 MB) before it can embed the query, and
        # that can outlast any sane per-request timeout. Observed exactly that
        # against a freshly wiped model cache.
        #
        # An unanswerable "does this already exist?" must default to "no". The
        # worst case is uploading a product that was already there, which the
        # pipeline handles; the alternative -- failing the run -- would make a
        # cold but perfectly healthy deployment look broken.
        return None

    if response.status != 200:
        return None

    try:
        payload = response.json()
    except SmokeError:
        # An unparseable search response is not this function's problem to
        # report -- the health stage already asserts the API is answering
        # properly. Here it just means "no existing copy found", and the
        # caller uploads.
        return None

    for result in payload.get("results", []) if isinstance(payload, dict) else []:
        metadata = result.get("metadata") or {}
        if (
            metadata.get("name") == product.name
            and metadata.get("brand") == product.brand
        ):
            product_id = result.get("product_id")
            if isinstance(product_id, str):
                return product_id
    return None


def upload(client: SmokeClient, product: DemoProduct) -> tuple[str, str]:
    """Upload one product. Returns `(product_id, job_id)`.

    Asserts 202 specifically. A 200 would mean the deployment processed the
    upload synchronously (ASYNC_PIPELINE__ENABLED=false), which is a valid
    configuration but not the one this suite exists to verify -- so it is
    surfaced rather than silently accepted.
    """
    response = client.post_multipart(
        client.api("/products/upload"),
        fields={
            "name": product.name,
            "brand": product.brand,
            "category": product.category,
            "price": product.price,
            "description": product.description,
        },
        files={"file": (product.filename, product.image)},
    )

    if response.status == 409:
        # DUPLICATE_DETECTION__MODE=block rejects the twin by design. Say so
        # precisely, because "409 on upload" otherwise looks like a bug.
        a.fail(
            f"Upload of {product.key!r} was rejected as a duplicate (HTTP 409). "
            f"The demo catalog deliberately contains a near-identical pair, which "
            f"DUPLICATE_DETECTION__MODE=block will refuse. Seed with the default "
            f"'warn' mode to exercise duplicate detection without blocking."
        )

    if response.status == 200:
        a.fail(
            "Upload returned HTTP 200 rather than 202, meaning this deployment "
            "processes uploads synchronously (ASYNC_PIPELINE__ENABLED=false). "
            "The async pipeline cannot be verified in that configuration."
        )

    a.status_is(response, 202)
    payload = a.is_object(response.json(), context=f"upload({product.key})")
    a.has_keys(
        payload, ("product_id", "job_id", "status"), context=f"upload({product.key})"
    )
    return str(payload["product_id"]), str(payload["job_id"])


def seed_catalog(client: SmokeClient, *, reuse: bool = True) -> list[SeededProduct]:
    """Ensure every demo product exists. Returns what was seeded.

    `reuse=False` forces a fresh upload of everything, which is what a
    throwaway environment wants; the default reuses whatever is already
    indexed so repeated local runs stay fast and do not grow the catalog
    without bound.
    """
    seeded: list[SeededProduct] = []

    for product in CATALOG:
        existing = find_existing(client, product) if reuse else None
        if existing is not None:
            seeded.append(
                SeededProduct(
                    key=product.key,
                    product_id=existing,
                    job_id="",  # no job: nothing was uploaded this run
                    name=product.name,
                    created=False,
                )
            )
            continue

        product_id, job_id = upload(client, product)
        seeded.append(
            SeededProduct(
                key=product.key,
                product_id=product_id,
                job_id=job_id,
                name=product.name,
                created=True,
            )
        )

    return seeded
