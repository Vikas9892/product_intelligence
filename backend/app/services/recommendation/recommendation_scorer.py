"""`RecommendationScorer`: computes one candidate's recommendation score against a target product.

Grouped under `app/services/recommendation/`, mirroring the
`app/services/catalog/`/`app/services/duplicate/` subpackage convention
Phases 7-8 already established for a phase's closely-related services.

Given the target product's own stored metadata (a `dict` — `brand`/
`category`/`color`/`material`/`gender`/`season`/`style`/`tags`/
`quality_score`, the same shape `ProductService` writes into the vector
store, see that module's docstring) and one candidate already retrieved
by `HybridSearchService.search_by_product_id`, `score` computes four
signals and combines them into one `RecommendationCandidate`:

- **similarity** — the candidate's own fused `score` from hybrid
  retrieval, reused as-is rather than recomputed (the same "reuse what
  retrieval already computed" reasoning `SimilarityScorer`, Phase 8,
  established for its own image/text signals).
- **attribute match** — the fraction of `color`/`material`/`gender`/
  `season`/`style` that agree (case-insensitive, exact match) between
  target and candidate, counted only over fields present on both sides —
  a field missing on either side is excluded from the average rather
  than penalized, same reasoning as `SimilarityScorer`'s own attribute
  signal. `brand`/`category` are intentionally *not* counted here —
  they get their own dedicated `shared_brand`/`shared_category` booleans
  on `RecommendationReason` instead of being folded into a continuous
  score, since they're usually the most salient single fact behind "why
  was this recommended."
- **tag match** — Jaccard overlap (`|shared| / |union|`) between the
  target's and candidate's tag sets, case-insensitive.
- **quality** — the candidate's own stored `quality_score` (Phase 7's
  `CatalogIntelligenceResult.quality_score`, persisted into vector
  metadata specifically so it survives retrieval-by-ID — see
  `ProductService`'s own docstring).

Each is weighted and summed into `final_score`, clamped to `[0, 1]`.
`RecommendationEngineService` (Milestone 3) owns ranking/diversity/
explanation generation — this class only scores one candidate at a time
and never compares candidates against each other.
"""

from typing import Any

from app.core.config import settings
from app.models.recommendation_candidate import RecommendationCandidate
from app.models.recommendation_reason import RecommendationReason
from app.models.search import HybridSearchResult

#: Catalog-intelligence-derived fields compared for the "attribute match"
#: signal — deliberately excludes brand/category (see module docstring).
_ATTRIBUTE_FIELDS: tuple[str, ...] = ("color", "material", "gender", "season", "style")


class RecommendationScorer:
    """Computes similarity/attribute/tag/quality signals for one recommendation candidate."""

    def __init__(
        self,
        *,
        similarity_weight: float | None = None,
        attribute_weight: float | None = None,
        tag_weight: float | None = None,
        quality_weight: float | None = None,
    ) -> None:
        self._similarity_weight = (
            similarity_weight
            if similarity_weight is not None
            else settings.recommendation.similarity_weight
        )
        self._attribute_weight = (
            attribute_weight
            if attribute_weight is not None
            else settings.recommendation.attribute_weight
        )
        self._tag_weight = (
            tag_weight if tag_weight is not None else settings.recommendation.tag_weight
        )
        self._quality_weight = (
            quality_weight if quality_weight is not None else settings.recommendation.quality_weight
        )

    def score(
        self, *, target_metadata: dict[str, Any], candidate: HybridSearchResult
    ) -> RecommendationCandidate:
        """Score `candidate` against `target_metadata` — the target product's own stored metadata."""
        similarity = _clamp(candidate.score)
        attribute_score, matched_attributes = _attribute_match(target_metadata, candidate.metadata)
        tag_score, shared_tags = _tag_match(
            target_metadata.get("tags"), candidate.metadata.get("tags")
        )
        quality = _clamp(_as_float(candidate.metadata.get("quality_score")))

        final_score = _clamp(
            self._similarity_weight * similarity
            + self._attribute_weight * attribute_score
            + self._tag_weight * tag_score
            + self._quality_weight * quality
        )

        reason = RecommendationReason(
            matched_attributes=matched_attributes,
            shared_tags=shared_tags,
            shared_brand=_values_match(
                target_metadata.get("brand"), candidate.metadata.get("brand")
            ),
            shared_category=_values_match(
                target_metadata.get("category"), candidate.metadata.get("category")
            ),
        )
        return RecommendationCandidate(
            product_id=candidate.product_id,
            similarity_score=similarity,
            attribute_score=attribute_score,
            tag_score=tag_score,
            quality_score=quality,
            final_score=final_score,
            reason=reason,
        )


def _clamp(value: float) -> float:
    """Clamp into `[0, 1]` (cosine similarity can stray slightly outside it)."""
    return max(0.0, min(1.0, value))


def _as_float(value: object) -> float:
    """Coerce a metadata value to `float`, defaulting to `0.0` for anything else (missing, `None`, ...)."""
    return value if isinstance(value, (int, float)) else 0.0


def _values_match(a: object, b: object) -> bool:
    """Case-insensitive, trimmed string equality — `False` if either side isn't a non-blank string."""
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    a_normalized, b_normalized = a.strip().lower(), b.strip().lower()
    if not a_normalized or not b_normalized:
        return False
    return a_normalized == b_normalized


def _attribute_match(
    target_metadata: dict[str, Any], candidate_metadata: dict[str, Any]
) -> tuple[float, list[str]]:
    """Average agreement over `_ATTRIBUTE_FIELDS` present (non-blank) on both sides."""
    matched: list[str] = []
    considered = 0
    for field_name in _ATTRIBUTE_FIELDS:
        target_value = target_metadata.get(field_name)
        candidate_value = candidate_metadata.get(field_name)
        if not isinstance(target_value, str) or not target_value.strip():
            continue
        if not isinstance(candidate_value, str) or not candidate_value.strip():
            continue
        considered += 1
        if _values_match(target_value, candidate_value):
            matched.append(field_name)

    score = len(matched) / considered if considered else 0.0
    return score, matched


def _tag_match(target_tags: object, candidate_tags: object) -> tuple[float, list[str]]:
    """Jaccard overlap between two tag sets, case-insensitive."""
    target_set = _normalize_tags(target_tags)
    candidate_set = _normalize_tags(candidate_tags)
    shared = sorted(target_set & candidate_set)
    union = target_set | candidate_set
    score = len(shared) / len(union) if union else 0.0
    return score, shared


def _normalize_tags(tags: object) -> set[str]:
    if not isinstance(tags, list):
        return set()
    return {tag.strip().lower() for tag in tags if isinstance(tag, str) and tag.strip()}
