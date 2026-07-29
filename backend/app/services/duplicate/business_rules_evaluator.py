"""`BusinessRulesEvaluator`: turns a candidate's metadata into explainable business signals (Phase 15).

The "Business Validation" stage of the verification pipeline: a pure,
stateless component that compares the checked product against one matched
candidate on brand, category, price, title, and attribute overlap, and
produces (a) a normalized `[0, 1]` business score, (b) a `veto` flag for
hard gates, and (c) a list of human-readable `VerificationReason`s.

Deliberately owns no retrieval, reranking, or model inference — it only
compares already-known fields, the same "compute pure signals, decide
nothing about the pipeline" separation `SimilarityScorer` (Phase 8)
already follows. `DuplicateVerificationService` (Milestone 4) combines
this score with the cross-encoder score into the final confidence, and
respects `veto` as an absolute override.

Reuses `rapidfuzz.fuzz.token_sort_ratio` for name/category fuzzy matching
— the exact same normalization (`strip().lower()`, `/100.0`)
`SimilarityScorer` already uses, so a "same category" judgment here is
consistent with the text-similarity signal elsewhere in the codebase.
"""

from dataclasses import dataclass
from typing import Any

from rapidfuzz import fuzz

from app.core.config import settings
from app.core.logging import get_logger
from app.models.product_attributes import ProductAttributes
from app.models.verification_reason import VerificationReason

logger = get_logger(__name__)

#: token_sort_ratio (0..1) at/above which two category strings count as
#: "the same category" — categories are compared fuzzily (a slugified
#: stored value vs. a natural-language submitted one), not by exact match.
_CATEGORY_MATCH_RATIO = 0.90

#: The attribute fields compared for overlap. Brand/category are handled
#: by their own dedicated rules, so they're excluded here.
_OVERLAP_ATTRIBUTES = ("color", "material", "gender", "style")


@dataclass(frozen=True)
class BusinessRulesResult:
    """The outcome of evaluating every business rule for one candidate.

    `score` is the fraction of *applicable* rules (those with data on both
    sides) that were satisfied — a neutral `0.0` when nothing could be
    compared. `veto` is set when a configured hard gate
    (`require_same_brand`/`require_same_category`) is violated, and
    absolutely overrides any cross-encoder score in the final decision.
    """

    score: float
    veto: bool
    reasons: list[VerificationReason]


class BusinessRulesEvaluator:
    """Compares a checked product against one candidate on brand/category/price/title/attributes."""

    def __init__(
        self,
        *,
        require_same_brand: bool | None = None,
        require_same_category: bool | None = None,
        max_price_difference_ratio: float | None = None,
        title_similarity_threshold: float | None = None,
    ) -> None:
        verification = settings.duplicate_verification
        self._require_same_brand = (
            require_same_brand
            if require_same_brand is not None
            else verification.require_same_brand
        )
        self._require_same_category = (
            require_same_category
            if require_same_category is not None
            else verification.require_same_category
        )
        self._max_price_difference_ratio = (
            max_price_difference_ratio
            if max_price_difference_ratio is not None
            else verification.max_price_difference_ratio
        )
        self._title_similarity_threshold = (
            title_similarity_threshold
            if title_similarity_threshold is not None
            else verification.title_similarity_threshold
        )

    def evaluate(
        self,
        *,
        name: str,
        brand: str | None,
        category: str | None,
        price: float | None,
        attributes: ProductAttributes,
        candidate_metadata: dict[str, Any],
    ) -> BusinessRulesResult:
        """Evaluate every applicable business rule between the checked product and one candidate."""
        reasons: list[VerificationReason] = []
        satisfied = 0
        applicable = 0
        veto = False

        brand_outcome = self._evaluate_brand(brand, candidate_metadata.get("brand"))
        if brand_outcome is not None:
            applicable += 1
            matched, reason = brand_outcome
            reasons.append(reason)
            satisfied += int(matched)
            veto = veto or (self._require_same_brand and not matched)

        category_outcome = self._evaluate_category(category, candidate_metadata.get("category"))
        if category_outcome is not None:
            applicable += 1
            matched, reason = category_outcome
            reasons.append(reason)
            satisfied += int(matched)
            veto = veto or (self._require_same_category and not matched)

        price_outcome = self._evaluate_price(price, candidate_metadata.get("price"))
        if price_outcome is not None:
            applicable += 1
            matched, reason = price_outcome
            reasons.append(reason)
            satisfied += int(matched)

        title_outcome = self._evaluate_title(name, candidate_metadata.get("name"))
        if title_outcome is not None:
            applicable += 1
            matched, reason = title_outcome
            reasons.append(reason)
            satisfied += int(matched)

        overlap_outcome = self._evaluate_attribute_overlap(attributes, candidate_metadata)
        if overlap_outcome is not None:
            applicable += 1
            matched, reason = overlap_outcome
            reasons.append(reason)
            satisfied += int(matched)

        score = satisfied / applicable if applicable else 0.0
        logger.info(
            "Business rules evaluated: score=%.2f, veto=%s, applicable=%d, satisfied=%d",
            score,
            veto,
            applicable,
            satisfied,
        )
        return BusinessRulesResult(score=score, veto=veto, reasons=reasons)

    def _evaluate_brand(
        self, query_brand: str | None, candidate_brand: object
    ) -> tuple[bool, VerificationReason] | None:
        query_norm = _normalize(query_brand)
        candidate_norm = _normalize(candidate_brand)
        if not query_norm or not candidate_norm:
            return None
        if query_norm == candidate_norm:
            return True, VerificationReason(
                code="same_brand", message=f"Same brand ({query_brand})"
            )
        return False, VerificationReason(
            code="brand_mismatch",
            message=f"Different brand ({query_brand} vs {candidate_brand})",
        )

    def _evaluate_category(
        self, query_category: str | None, candidate_category: object
    ) -> tuple[bool, VerificationReason] | None:
        if not _normalize(query_category) or not _normalize(candidate_category):
            return None
        ratio = _fuzzy_ratio(str(query_category), str(candidate_category))
        if ratio >= _CATEGORY_MATCH_RATIO:
            return True, VerificationReason(
                code="same_category", message=f"Same category ({query_category})"
            )
        return False, VerificationReason(
            code="category_mismatch",
            message=f"Different category ({query_category} vs {candidate_category})",
        )

    def _evaluate_price(
        self, query_price: float | None, candidate_price: object
    ) -> tuple[bool, VerificationReason] | None:
        if query_price is None or not isinstance(candidate_price, int | float):
            return None
        denominator = max(abs(float(candidate_price)), 1e-9)
        difference_ratio = abs(query_price - float(candidate_price)) / denominator
        if difference_ratio <= self._max_price_difference_ratio:
            return True, VerificationReason(
                code="close_price",
                message=f"Similar price (within {difference_ratio:.0%})",
            )
        return False, VerificationReason(
            code="price_difference",
            message=f"Price differs by {difference_ratio:.0%}",
        )

    def _evaluate_title(
        self, query_name: str, candidate_name: object
    ) -> tuple[bool, VerificationReason] | None:
        if not _normalize(candidate_name):
            return None
        ratio = _fuzzy_ratio(query_name, str(candidate_name))
        if ratio >= self._title_similarity_threshold:
            return True, VerificationReason(
                code="title_similarity", message=f"Title similarity {ratio:.0%}"
            )
        return False, VerificationReason(
            code="title_difference", message=f"Title similarity only {ratio:.0%}"
        )

    def _evaluate_attribute_overlap(
        self, attributes: ProductAttributes, candidate_metadata: dict[str, Any]
    ) -> tuple[bool, VerificationReason] | None:
        matched: list[str] = []
        comparable = 0
        for field in _OVERLAP_ATTRIBUTES:
            query_value = _normalize(getattr(attributes, field, None))
            candidate_value = _normalize(candidate_metadata.get(field))
            if not query_value or not candidate_value:
                continue
            comparable += 1
            if query_value == candidate_value:
                matched.append(field)
        if comparable == 0:
            return None
        if matched:
            return True, VerificationReason(
                code="attribute_overlap",
                message=f"Matching attributes: {', '.join(matched)}",
            )
        return False, VerificationReason(
            code="attribute_mismatch", message="No matching attributes"
        )


def _normalize(value: object) -> str:
    """Lower/strip a possibly-non-string value to a comparable token, `""` when absent."""
    return value.strip().lower() if isinstance(value, str) else ""


def _fuzzy_ratio(a: str, b: str) -> float:
    """token_sort_ratio in `[0, 1]` — the same normalization `SimilarityScorer` uses."""
    return fuzz.token_sort_ratio(a.strip().lower(), b.strip().lower()) / 100.0
