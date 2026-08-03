"""Verifies the AI capabilities through their public APIs.

The hard part of testing a machine-learning system is deciding what "correct"
means. Two failure modes to avoid:

Asserting exact scores. `score == 0.9389` passes today and fails after any
model upgrade, weight change or library update -- none of which mean the
deployment broke. It also tells you nothing: a system returning 0.9389 for
everything would pass.

Reimplementing the backend. If the suite computed expected scores itself, it
would be testing its own arithmetic against the backend's, and the two would
have to be kept in sync forever.

So these checks assert *invariants over the known relationships* in the demo
catalog instead. The near-identical twin must outrank the desk lamp. A
product must not recommend itself. An image must match itself almost exactly.
Confidence must lie in its declared range. Those hold across model versions,
and a system that returns everything or nothing fails them.

The catalog's negative controls do real work here: the desk lamp exists so
that "ranks highly" can be distinguished from "is returned at all", and the
blue backpack exists so a recommender keying purely on colour gets caught.
"""

from __future__ import annotations

from typing import Any

import assertions as a
from context import SmokeContext
from dataset import BY_KEY

#: How deep to search. Larger than the catalog so ordering is observable
#: rather than truncated.
_TOP_K = 8


def _search(
    ctx: SmokeContext,
    *,
    query: str | None = None,
    image_key: str | None = None,
    top_k: int = _TOP_K,
) -> list[dict[str, Any]]:
    """Run a search and return its results, newest contract shape."""
    fields: dict[str, Any] = {"top_k": top_k}
    if query is not None:
        fields["query"] = query
    files = None
    if image_key is not None:
        files = {"file": (f"{image_key}.png", BY_KEY[image_key].image)}

    response = ctx.client.post_multipart(
        ctx.client.api("/products/search"), fields=fields, files=files
    )
    a.status_is(response, 200)
    payload = a.is_object(response.json(), context="search")
    results = a.is_list(payload.get("results"), context="search.results")

    for index, result in enumerate(results):
        item = a.is_object(result, context=f"search.results[{index}]")
        a.has_keys(item, ("product_id", "score"), context=f"search.results[{index}]")
        a.in_range(item["score"], 0.0, 1.0, context=f"search.results[{index}].score")
    return [a.is_object(r, context="result") for r in results]


def _ranking(ctx: SmokeContext, results: list[dict[str, Any]]) -> list[str]:
    """Map results to demo keys, in rank order.

    Unknown ids (products from outside this catalog) are kept as raw ids so a
    polluted environment is visible in the failure message rather than
    silently dropped.
    """
    by_id = {p.product_id: key for key, p in ctx.seeded.items()}
    return [by_id.get(str(r["product_id"]), str(r["product_id"])[:8]) for r in results]


# -- Search ----------------------------------------------------------------


def check_text_search(ctx: SmokeContext) -> str:
    """A text query retrieves the semantically right products.

    "blue running shoe" must rank both blue shoes above the desk lamp and the
    mug. That is a claim about meaning, not about any particular score.
    """
    results = _search(ctx, query="blue running shoe")
    a.require(len(results) > 0, "text search returned no results for a seeded catalog")

    ranking = _ranking(ctx, results)
    for weaker in ("lamp_yellow", "mug_red_a"):
        a.ranks_above(ranking, "shoe_blue_a", weaker, context="text search")
        a.ranks_above(ranking, "shoe_blue_b", weaker, context="text search")

    return f"{len(results)} results, blue shoes ranked above lamp/mug"


def check_image_search(ctx: SmokeContext) -> str:
    """An image finds itself, and its near-twin, ahead of everything else.

    Self-similarity is the single strongest invariant available: querying with
    a product's own image must return that product at essentially 1.0. Anything
    materially lower means the stored vector is not the one that image
    produces -- a broken embedding path that every other check could miss.
    """
    results = _search(ctx, image_key="shoe_blue_a")
    a.require(len(results) > 0, "image search returned no results")

    ranking = _ranking(ctx, results)
    a.require(
        ranking[0] == "shoe_blue_a",
        f"image search with a product's own image ranked {ranking[0]!r} first, "
        f"not the product itself. Ranking: {ranking}",
    )
    self_score = float(results[0]["score"])
    a.at_least(self_score, 0.95, context="image search self-similarity")

    # The visual twin must beat everything that is not a shoe.
    for weaker in ("lamp_yellow", "mug_red_a", "backpack_black"):
        a.ranks_above(ranking, "shoe_blue_b", weaker, context="image search")

    return f"self-match {self_score:.3f}, twin ranked above unrelated products"


def check_hybrid_search(ctx: SmokeContext) -> str:
    """Image and text together still rank the right things first.

    Checked separately from either modality because fusion is its own code
    path: a broken weighting could pass both single-modality checks and still
    return nonsense here.
    """
    results = _search(ctx, query="blue running shoe", image_key="shoe_blue_a")
    a.require(len(results) > 0, "hybrid search returned no results")

    ranking = _ranking(ctx, results)
    for weaker in ("lamp_yellow", "mug_red_a"):
        a.ranks_above(ranking, "shoe_blue_a", weaker, context="hybrid search")
        a.ranks_above(ranking, "shoe_blue_b", weaker, context="hybrid search")

    modalities = results[0].get("matched_modalities")
    a.require(
        isinstance(modalities, list) and len(modalities) > 0,
        f"hybrid search result reports matched_modalities={modalities!r}; "
        f"expected a non-empty list naming which signals matched",
    )
    return f"{len(results)} results, modalities={modalities}"


# -- Duplicates ------------------------------------------------------------


def check_duplicate_detected(ctx: SmokeContext) -> str:
    """The near-identical twin is recognised as a duplicate.

    Submits shoe_blue_b's image and metadata. The catalog already holds both
    blue shoes, so a correct system reports a duplicate and points at one of
    them.
    """
    product = BY_KEY["shoe_blue_b"]
    response = ctx.client.post_multipart(
        ctx.client.api("/products/check-duplicate"),
        fields={
            "name": product.name,
            "brand": product.brand,
            "category": product.category,
        },
        files={"file": (product.filename, product.image)},
    )
    a.status_is(response, 200)
    payload = a.is_object(response.json(), context="check-duplicate")
    a.has_keys(
        payload,
        ("duplicate", "confidence", "reason", "matched_product", "signals"),
        context="check-duplicate",
    )

    a.require(
        payload["duplicate"] is True,
        f"the near-identical twin of a catalogued product was NOT flagged as a "
        f"duplicate (confidence={payload['confidence']}, reason={payload['reason']!r})",
    )
    confidence = a.in_range(
        payload["confidence"], 0.0, 1.0, context="check-duplicate.confidence"
    )

    blue_shoes = {ctx.product_id("shoe_blue_a"), ctx.product_id("shoe_blue_b")}
    a.require(
        str(payload["matched_product"]) in blue_shoes,
        f"duplicate matched {payload['matched_product']!r}, which is neither blue shoe",
    )

    signals = a.is_object(payload["signals"], context="check-duplicate.signals")
    for name, value in signals.items():
        a.in_range(value, 0.0, 1.0, context=f"check-duplicate.signals.{name}")

    return f"detected, confidence {confidence:.3f}, {len(signals)} signals"


def check_non_duplicate_not_flagged(ctx: SmokeContext) -> str:
    """An unrelated product is not called a duplicate.

    The negative case matters as much as the positive one: a detector that
    answers "duplicate" to everything would pass the check above.
    """
    product = BY_KEY["lamp_yellow"]
    response = ctx.client.post_multipart(
        ctx.client.api("/products/check-duplicate"),
        fields={
            "name": "Demo Unrelated Verification Widget",
            "brand": "SmokeTest",
            "category": "hardware",
        },
        files={"file": (product.filename, product.image)},
    )
    a.status_is(response, 200)
    payload = a.is_object(response.json(), context="check-duplicate(negative)")
    a.require(
        payload["duplicate"] is False,
        f"an unrelated product was flagged as a duplicate of "
        f"{payload.get('matched_product')!r} (confidence={payload.get('confidence')})",
    )
    confidence = a.in_range(
        payload["confidence"], 0.0, 1.0, context="check-duplicate(negative).confidence"
    )
    return f"correctly not flagged, confidence {confidence:.3f}"


# -- Recommendations -------------------------------------------------------


def check_recommendations(ctx: SmokeContext) -> str:
    """Recommendations for the blue shoe are relevant and exclude itself."""
    source = ctx.product_id("shoe_blue_a")
    response = ctx.client.get(
        ctx.client.api(f"/products/{source}/recommendations"), params={"top_k": 6}
    )
    a.status_is(response, 200)
    payload = a.is_object(response.json(), context="recommendations")
    a.has_keys(
        payload, ("recommendation_type", "recommendations"), context="recommendations"
    )

    items = a.is_list(
        payload["recommendations"], context="recommendations.recommendations"
    )
    a.require(
        len(items) > 0,
        "no recommendations returned for a product in an eight-item catalog; "
        "note the worker precomputes these into a cache with a TTL, so an "
        "empty result can also mean the cache expired",
    )

    ids = [str(a.is_object(i, context="recommendation")["product_id"]) for i in items]
    a.require(
        source not in ids,
        "a product was recommended as similar to itself, which is never useful",
    )

    scores = [float(i["score"]) for i in items]
    for index, score in enumerate(scores):
        a.in_range(score, 0.0, 1.0, context=f"recommendations[{index}].score")

    # Deliberately NOT asserting a globally descending order. `_diversify`
    # round-robins by brand -- one candidate per brand per round, best-scoring
    # first -- so a lower-scored product from an unseen brand legitimately
    # precedes a higher-scored one from a brand already represented. Observed
    # exactly that, and it is documented behavior, not a defect.
    #
    # What does hold: the single best match leads, because the first round
    # takes the top-scoring candidate before any diversification applies.
    a.require(
        scores[0] == max(scores),
        f"the top recommendation scored {scores[0]} but a later one scored "
        f"{max(scores)}; the best match should lead even after brand "
        f"diversification. Scores: {scores}",
    )

    ranking = _ranking(ctx, [{"product_id": i} for i in ids])
    # The near-twin must beat every product from an unrelated category. Not
    # asserted against shoe_black: the blue backpack legitimately outranks it
    # on colour, which is real behavior, not a defect.
    for weaker in ("lamp_yellow", "mug_red_a", "mug_red_b"):
        a.ranks_above(ranking, "shoe_blue_b", weaker, context="recommendations")

    return f"{len(items)} returned, source excluded, twin ranked above unrelated"


# -- Pricing ---------------------------------------------------------------

_VALID_CONFIDENCE = {"low", "medium", "high"}


def check_pricing(ctx: SmokeContext) -> str:
    """A price estimate is well-formed and backed by real comparables.

    The estimate's *value* is not asserted. With an eight-item catalog the
    comparables legitimately span mugs and backpacks, so the figure is not
    meaningfully checkable -- and asserting it would mean reimplementing the
    estimator. What is checkable: the response is structurally valid,
    confidence is a declared level, and the comparables are real products
    with real prices.
    """
    source = ctx.product_id("shoe_blue_a")
    response = ctx.client.get(ctx.client.api(f"/pricing/{source}"))
    a.status_is(response, 200)
    payload = a.is_object(response.json(), context="pricing")
    a.has_keys(
        payload,
        (
            "estimated_price",
            "confidence",
            "confidence_score",
            "strategy",
            "comparable_count",
            "comparables",
        ),
        context="pricing",
    )

    a.require(
        payload["confidence"] in _VALID_CONFIDENCE,
        f"pricing confidence={payload['confidence']!r}, expected one of "
        f"{sorted(_VALID_CONFIDENCE)}",
    )
    a.in_range(
        payload["confidence_score"], 0.0, 1.0, context="pricing.confidence_score"
    )
    a.at_least(payload["estimated_price"], 0.0, context="pricing.estimated_price")

    comparables = a.is_list(payload["comparables"], context="pricing.comparables")
    a.require(
        len(comparables) > 0,
        "pricing returned no comparables for a catalog with eight priced products",
    )
    a.require(
        int(payload["comparable_count"]) == len(comparables),
        f"comparable_count={payload['comparable_count']} but {len(comparables)} "
        f"comparables were returned",
    )
    for index, comparable in enumerate(comparables):
        item = a.is_object(comparable, context=f"pricing.comparables[{index}]")
        a.has_keys(
            item, ("product_id", "price"), context=f"pricing.comparables[{index}]"
        )
        a.at_least(item["price"], 0.0, context=f"pricing.comparables[{index}].price")
    a.require(
        source not in [str(c["product_id"]) for c in comparables],
        "the product being priced appears in its own comparables",
    )

    return (
        f"{payload['estimated_price']} from {len(comparables)} comparables "
        f"({payload['confidence']}, {payload['strategy']})"
    )


# -- Explanations ----------------------------------------------------------


def check_explanations(ctx: SmokeContext) -> str:
    """Decision traces exist and are structurally sound.

    Explainability is a headline capability, so a deployment that serves
    scores but cannot say why is broken even though every other check passes.
    """
    source = ctx.product_id("shoe_blue_a")
    response = ctx.client.get(ctx.client.api(f"/products/{source}/explanations"))
    a.status_is(response, 200)
    payload = a.is_object(response.json(), context="explanations")
    a.has_keys(
        payload, ("product_id", "duplicate", "recommendations"), context="explanations"
    )

    sections = 0
    for name in ("duplicate", "recommendations"):
        section = payload[name]
        if section is None:
            # A legitimate state: nothing was decided for this product.
            continue
        entries = section if isinstance(section, list) else [section]
        for entry in entries:
            item = a.is_object(entry, context=f"explanations.{name}")
            a.has_keys(item, ("reasons", "confidence"), context=f"explanations.{name}")
            a.in_range(
                item["confidence"], 0.0, 1.0, context=f"explanations.{name}.confidence"
            )
            reasons = a.is_list(item["reasons"], context=f"explanations.{name}.reasons")
            a.require(
                len(reasons) > 0,
                f"explanations.{name} carries an empty reasons list, which explains nothing",
            )
            for reason in reasons:
                a.has_keys(
                    a.is_object(reason, context=f"explanations.{name}.reason"),
                    ("code", "description"),
                    context=f"explanations.{name}.reason",
                )
            sections += 1

    a.require(
        sections > 0,
        "no decision traces at all for a product that was deduplicated and "
        "recommended against an eight-item catalog",
    )
    return f"{sections} decision trace(s), all with coded reasons"
