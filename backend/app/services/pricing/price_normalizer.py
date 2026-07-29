"""`PriceNormalizer`: turns raw retrieval results into clean priced comparables (Phase 17).

Pure, stateless: reads a list of `HybridSearchResult`s and keeps only the
ones whose stored metadata carries a usable price (present, numeric, and
`> 0`), building a `ComparableProduct` for each. Everything downstream
(`PriceEstimator`) can then assume every comparable has a positive price,
so the pricing math never guards against missing/zero prices. Owns no
retrieval and no aggregation — it only cleans and shapes, the same
"normalize, decide nothing" separation `SimilarityScorer`/
`BusinessRulesEvaluator` already follow.
"""

from typing import Any

from app.core.logging import get_logger
from app.models.comparable_product import ComparableProduct
from app.models.search import HybridSearchResult

logger = get_logger(__name__)


class PriceNormalizer:
    """Extracts positively-priced `ComparableProduct`s from hybrid-search results."""

    def to_comparables(self, results: list[HybridSearchResult]) -> list[ComparableProduct]:
        """Build a `ComparableProduct` for each result with a usable (`> 0`) stored price."""
        comparables: list[ComparableProduct] = []
        for result in results:
            price = _coerce_price(result.metadata.get("price"))
            if price is None:
                continue
            comparables.append(
                ComparableProduct(
                    product_id=result.product_id,
                    price=price,
                    similarity=result.score,
                    name=_coerce_str(result.metadata.get("name")),
                    brand=_coerce_str(result.metadata.get("brand")),
                    category=_coerce_str(result.metadata.get("category")),
                )
            )
        logger.info(
            "Priced comparables extracted: results=%d, priced=%d", len(results), len(comparables)
        )
        return comparables


def _coerce_price(value: Any) -> float | None:
    """Return `value` as a positive float, or `None` if it's missing/non-numeric/non-positive."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    price = float(value)
    return price if price > 0 else None


def _coerce_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
