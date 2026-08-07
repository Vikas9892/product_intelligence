"""`ComparableFilter`: keeps only comparables that can legitimately inform a price (Phase 17).

Sits between `PriceNormalizer` (which cleans and shapes) and `PriceEstimator`
(which aggregates), and decides *relevance* — the step that was missing.

Why this exists
---------------

`PriceNormalizer` filtered on one condition: the stored price is `> 0`.
Everything the retrieval layer returned was therefore priced against, however
unrelated. Measured on the demo catalog before this module existed:

    pricing a running shoe (footwear), estimate 76.50 from 7 comparables
        0.9812  footwear     shoe_blue_b     134.99
        0.8605  footwear     shoe_black      119.99
        0.7795  bags         backpack_blue    89.00
        0.7560  bags         backpack_black   94.00
        0.7381  lighting     lamp_yellow      45.00   <- a desk lamp
        0.7155  kitchenware  mug_red_b        28.00
        0.7033  kitchenware  mug_red_a        24.50

    pricing a 24.50 mug (kitchenware), estimate 91.57 from 7 comparables
        0.9805  kitchenware  mug_red_b        28.00
        0.8039  lighting     lamp_yellow      45.00
        ...then every shoe and backpack in the catalog

A mug valued at 91.57 because it was averaged against footwear is the same
defect as a shoe priced partly from a desk lamp, just more obvious.

Why category is the primary filter, not similarity
--------------------------------------------------

The instinctive fix is a similarity floor, and on this data a floor alone
would not work. Cross-category items score 0.68-0.80, while a *legitimate*
same-category comparable (the black trail shoe) scores 0.8605. Any floor high
enough to exclude the lamp at 0.8039 would also discard real footwear
comparables. Embedding similarity measures "looks and reads alike", which is
not the same question as "is priced by the same market".

So the filter is ordered by what the evidence supports:

1. **Category compatibility** does the real work. A price comparable must come
   from the same category, because that is what makes it a comparable at all.
2. **A similarity floor** removes weak evidence *within* a category. It is a
   guard against thin matches, not the category separator.

Both are configurable and both are reported, so an exclusion is as auditable
as an inclusion.
"""

from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger
from app.models.comparable_product import ComparableProduct

logger = get_logger(__name__)


@dataclass(frozen=True)
class FilterOutcome:
    """The kept comparables, plus why the rest were dropped.

    The counts exist to be surfaced in the decision trace: a price estimate
    that silently discarded half its evidence is not auditable.
    """

    kept: list[ComparableProduct]
    excluded_by_category: int
    excluded_by_similarity: int
    applied_similarity_floor: float
    applied_category: str | None

    @property
    def excluded_total(self) -> int:
        return self.excluded_by_category + self.excluded_by_similarity


class ComparableFilter:
    """Drops comparables that cannot legitimately inform a price."""

    def __init__(
        self,
        *,
        similarity_floor: float | None = None,
        enforce_category: bool | None = None,
    ) -> None:
        self._similarity_floor = (
            similarity_floor
            if similarity_floor is not None
            else settings.pricing.min_comparable_similarity
        )
        self._enforce_category = (
            enforce_category
            if enforce_category is not None
            else settings.pricing.restrict_to_same_category
        )

    def apply(self, comparables: list[ComparableProduct], *, category: str | None) -> FilterOutcome:
        """Keep the comparables relevant to a product in `category`.

        `category` is the *subject's* category. When it is unknown, the
        category rule is skipped rather than guessed at — filtering everything
        out because the subject is unlabelled would turn missing metadata into
        a refusal to price.
        """
        target = _normalize(category)
        enforce_category = self._enforce_category and target is not None

        kept: list[ComparableProduct] = []
        excluded_by_category = 0
        excluded_by_similarity = 0

        for comparable in comparables:
            if enforce_category and _normalize(comparable.category) != target:
                excluded_by_category += 1
                continue
            if comparable.similarity < self._similarity_floor:
                excluded_by_similarity += 1
                continue
            kept.append(comparable)

        logger.info(
            "Pricing comparables filtered: in=%d, kept=%d, dropped_category=%d, "
            "dropped_similarity=%d, floor=%.2f, category=%s",
            len(comparables),
            len(kept),
            excluded_by_category,
            excluded_by_similarity,
            self._similarity_floor,
            target,
        )
        return FilterOutcome(
            kept=kept,
            excluded_by_category=excluded_by_category,
            excluded_by_similarity=excluded_by_similarity,
            applied_similarity_floor=self._similarity_floor,
            applied_category=target if enforce_category else None,
        )


def _normalize(category: str | None) -> str | None:
    """Casefold and trim a category for comparison, or `None` if unusable."""
    if not isinstance(category, str):
        return None
    cleaned = category.strip().casefold()
    return cleaned or None
