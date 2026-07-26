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
"""


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
