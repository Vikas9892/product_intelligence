"""Small, stateless text-assembly helpers shared across layers.

`build_text_representation` originated in `ProductService` (Phase 6) as a
private, module-level helper; it moves here in Phase 8 because
`DuplicateDetectionService` needs the exact same "one natural-language
string from name/brand/category/description" text to build its own
hybrid-search query — importing it from `app.services.product_service`
directly would create a circular import once `ProductService` composes
`DuplicateDetectionService` (Milestone 4). Extracting it to `app/utils/`
(this module's whole purpose — helpers with no service state, shared by
whichever layer needs them) avoids that without duplicating the logic.

`build_text_representation_from_metadata` (Phase 11) is the same
assembly, but starting from an already-stored vector-metadata `dict`
(Phase 9's `name`/`brand`/`category`/`description` shape) rather than
freshly-submitted fields — used wherever a query text is needed for a
product that's only known by ID (`RecommendationEngineService`'s target
metadata, `DuplicateDetectionService.detect_by_product_id`'s target
metadata, `RerankerService`'s own candidate documents), so all three
build their cross-encoder query/document text the same way instead of
each re-deriving it from a raw metadata dict independently.
"""

from typing import Any


def build_text_representation(
    name: str, brand: str | None, category: str | None, description: str | None
) -> str:
    """Join a product's name/brand/category/description into one natural-language string.

    Deliberately uses the *raw* submitted values (only stripped of
    surrounding whitespace), not a slugified category (`"men-tshirts"`) —
    a sentence embedding model (or a duplicate-detection hybrid search
    query) should see "Men Tshirts", not a URL-safe slug. Slugifying
    exists purely so category is a stable, exact-match filter value for
    the vector store; it's a storage/filtering concern, not a
    semantic-meaning one, so this function never slugifies its input.
    """
    parts = [name.strip()]
    for part in (brand, category, description):
        if part and part.strip():
            parts.append(part.strip())
    return ". ".join(parts)


def build_text_representation_from_metadata(metadata: dict[str, Any]) -> str:
    """`build_text_representation`, sourced from a stored vector-metadata `dict` instead.

    Tolerates whatever shape the metadata actually has (a non-string
    `name`/`brand`/`category`/`description`, or any of them missing
    entirely) rather than raising — a candidate's stored metadata is
    catalog data, not caller input, so a malformed or sparse entry should
    degrade to a shorter (possibly empty) string, not fail the whole
    reranking pass over it.
    """
    name = metadata.get("name")
    brand = metadata.get("brand")
    category = metadata.get("category")
    description = metadata.get("description")
    return build_text_representation(
        name if isinstance(name, str) else "",
        brand if isinstance(brand, str) else None,
        category if isinstance(category, str) else None,
        description if isinstance(description, str) else None,
    )
