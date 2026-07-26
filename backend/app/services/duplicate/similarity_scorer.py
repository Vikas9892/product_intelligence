"""`SimilarityScorer`: computes independent similarity signals between two products.

Grouped under `app/services/duplicate/` rather than loose in `app/services/`
— the same "group a phase's closely-related services under their own
subpackage" convention `app/services/catalog/` established in Phase 7.

Given the product currently being checked (its name/brand/category and
resolved `ProductAttributes`) and one candidate already retrieved by
`HybridSearchService` (a `HybridSearchResult`, carrying that candidate's
own metadata plus its per-modality `image_score`/`text_score`), `score`
computes four independent `SimilaritySignal`s and bundles them into a
`DuplicateResult`:

- **image** — the candidate's own `image_score` from hybrid retrieval,
  reused as-is rather than recomputed. `HybridSearchService` already ran
  `SearchService`'s CLIP-embedding cosine similarity to *find* this
  candidate in the first place; re-embedding and re-comparing here would
  be redundant work computing the exact same number.
- **text** — the same reuse, using `candidate.text_score` (BGE-embedding
  cosine similarity from `TextSearchService`).
- **metadata** — deterministic (non-embedding) fuzzy-text similarity,
  via `rapidfuzz.fuzz.token_sort_ratio`, between the checked product's
  name/brand/category and the candidate's own metadata values, averaged
  over whichever of those three fields is actually present on both
  sides. Deliberately case-insensitive and word-order-insensitive: the
  candidate's `category` metadata is a lowercase, hyphen-slugified value
  (`ProductService._normalize_category`), while the checked product's own
  `category` is natural-language ("Running Shoes") — `token_sort_ratio`
  on lowercased text tolerates exactly that kind of formatting drift
  without it being scored as a real difference.
- **attribute** — the same fuzzy-ratio approach, field-by-field, over
  `ProductAttributes`' brand/category/color/material/style/gender against
  the matching keys in the candidate's metadata (Phase 7 already stores
  `color`/`material`/`gender`/`style` there; `brand`/`category` are
  present too, though sourced from the normalized submitted fields rather
  than catalog intelligence's own guess — see `product_service.py`'s own
  docstring for why). A field missing on either side is excluded from the
  average rather than penalized — a product simply lacking a detected
  `material`, for instance, isn't evidence of *dissimilarity*.

No duplicate/not-duplicate decision is made here — see
`DuplicateDetectionService` for conflict resolution, thresholding, and
the final `DuplicateDecision`.
"""

from typing import Any

from rapidfuzz import fuzz

from app.core.config import settings
from app.models.duplicate_result import DuplicateResult
from app.models.product_attributes import ProductAttributes
from app.models.search import HybridSearchResult
from app.models.similarity_signal import SimilaritySignal

#: `ProductAttributes` fields compared field-by-field against the
#: candidate's metadata for the "attribute" signal — the phase spec's own
#: worked example ("Brand, Category, Color, Material, Style, Gender").
_ATTRIBUTE_FIELDS: tuple[str, ...] = ("brand", "category", "color", "material", "style", "gender")


class SimilarityScorer:
    """Computes image/text/metadata/attribute similarity signals for one candidate."""

    def __init__(
        self,
        *,
        image_weight: float | None = None,
        text_weight: float | None = None,
        metadata_weight: float | None = None,
        attribute_weight: float | None = None,
    ) -> None:
        self._image_weight = (
            image_weight if image_weight is not None else settings.duplicate_detection.image_weight
        )
        self._text_weight = (
            text_weight if text_weight is not None else settings.duplicate_detection.text_weight
        )
        self._metadata_weight = (
            metadata_weight
            if metadata_weight is not None
            else settings.duplicate_detection.metadata_weight
        )
        self._attribute_weight = (
            attribute_weight
            if attribute_weight is not None
            else settings.duplicate_detection.attribute_weight
        )

    def score(
        self,
        *,
        name: str,
        brand: str | None,
        category: str | None,
        attributes: ProductAttributes,
        candidate: HybridSearchResult,
    ) -> DuplicateResult:
        """Compare one candidate against the product currently being checked."""
        signals = [
            _signal("image", candidate.image_score, self._image_weight),
            _signal("text", candidate.text_score, self._text_weight),
            _signal(
                "metadata",
                _metadata_similarity(name, brand, category, candidate.metadata),
                self._metadata_weight,
            ),
            _signal(
                "attribute",
                _attribute_similarity(attributes, candidate.metadata),
                self._attribute_weight,
            ),
        ]
        overall = max(0.0, min(1.0, sum(signal.contribution for signal in signals)))
        return DuplicateResult(
            product_id=candidate.product_id, signals=signals, overall_similarity=overall
        )


def _signal(name: str, raw_score: float, weight: float) -> SimilaritySignal:
    """Clamp `raw_score` into `[0, 1]` (cosine similarity can stray slightly outside it) and weight it."""
    score = max(0.0, min(1.0, raw_score))
    return SimilaritySignal(name=name, score=score, weight=weight, contribution=score * weight)


def _fuzzy_ratio(a: str, b: str) -> float:
    """Case-insensitive, word-order-insensitive similarity ratio in `[0, 1]`."""
    return fuzz.token_sort_ratio(a.strip().lower(), b.strip().lower()) / 100.0


def _metadata_similarity(
    name: str, brand: str | None, category: str | None, candidate_metadata: dict[str, Any]
) -> float:
    """Average fuzzy similarity over whichever of name/brand/category is present on both sides."""
    pairs: tuple[tuple[str | None, Any], ...] = (
        (name, candidate_metadata.get("name")),
        (brand, candidate_metadata.get("brand")),
        (category, candidate_metadata.get("category")),
    )
    ratios = [
        _fuzzy_ratio(value, candidate_value)
        for value, candidate_value in pairs
        if value and value.strip() and isinstance(candidate_value, str) and candidate_value.strip()
    ]
    return sum(ratios) / len(ratios) if ratios else 0.0


def _attribute_similarity(
    attributes: ProductAttributes, candidate_metadata: dict[str, Any]
) -> float:
    """Average fuzzy similarity, field-by-field, over `_ATTRIBUTE_FIELDS` present on both sides."""
    ratios = []
    for field_name in _ATTRIBUTE_FIELDS:
        value = getattr(attributes, field_name)
        candidate_value = candidate_metadata.get(field_name)
        if not value or not isinstance(candidate_value, str) or not candidate_value.strip():
            continue
        ratios.append(_fuzzy_ratio(value, candidate_value))
    return sum(ratios) / len(ratios) if ratios else 0.0
