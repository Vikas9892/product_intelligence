"""Internal domain model: `RecommendationType`, which recommendation strategy produced a result.

Lives in `app/models/` rather than `app/core/constants.py` — unlike
`DuplicateDetectionMode` (a configuration knob controlling *behavior*),
`RecommendationType` is a *request/result* value a caller selects per call
(`GET /products/{id}/recommendations?recommendation_type=...`) and that
travels with the result, the same role `SearchModality`/`Source` already
play as domain-level vocabularies.
"""

from enum import StrEnum


class RecommendationType(StrEnum):
    """Which recommendation strategy `RecommendationEngineService` should use.

    Only `SIMILAR` and `RELATED` are implemented this phase — `SIMILAR`
    anchors on the target product's full hybrid (image + text) profile,
    `RELATED` anchors on text/category alone (decoupled from pure visual
    likeness). `COMPLEMENTARY` ("goes well with," e.g. recommending socks
    for a pair of shoes) is intentionally reserved, unimplemented — it
    needs a *different* kind of relationship (products that pair well
    together, not products that resemble each other) that neither
    similarity signal here can express; the phase spec explicitly leaves
    it "future-ready" rather than asking for a placeholder algorithm.
    """

    SIMILAR = "similar"
    RELATED = "related"
    COMPLEMENTARY = "complementary"
