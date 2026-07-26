"""Deterministic, rule-based text attribute extraction (Phase 7).

`TextAttributeExtractionService` finds catalog attributes and tags in a
product's name/brand/category/description using regex + lookup-dictionary
matching — deliberately *not* a model call. `CatalogIntelligenceService`
composes this alongside `ImageAttributeExtractionService` and resolves
whatever the two disagree on; this service only ever proposes candidates
for the text side, via `AttributePrediction`s with `Source.TEXT`.

Every method here is a plain (non-`async def`) method — unlike every I/O-
or model-backed service in this codebase, there's no blocking work to
speak of: matching a handful of keyword dictionaries against a short
string is microseconds, not something that needs `run_in_threadpool` or
even `async def` in the first place. `CatalogIntelligenceService` (itself
`async`, since it also awaits `ImageAttributeExtractionService`) just
calls these directly.

If `brand`/`category` were already submitted as structured fields on the
upload form (Phase 6's `brand`, Phase 2A's `category`), those are trusted
directly at confidence `1.0` rather than re-derived from free text —
re-parsing a value the client already told us outright would be strictly
less reliable than using it, not more.
"""

import re

from app.core.logging import get_logger
from app.models.attribute_prediction import AttributePrediction
from app.models.catalog_tags import CatalogTag, Source

logger = get_logger(__name__)

# --- Lookup data: deterministic, hand-curated, not learned. ---
# Keys are lowercase match keywords; values are the normalized, displayed
# attribute value. Multi-word phrases are supported (e.g. "running shoe").

_KNOWN_BRANDS: dict[str, str] = {
    "nike": "Nike",
    "adidas": "Adidas",
    "puma": "Puma",
    "reebok": "Reebok",
    "under armour": "Under Armour",
    "new balance": "New Balance",
    "asics": "Asics",
    "converse": "Converse",
    "vans": "Vans",
    "fila": "Fila",
    "skechers": "Skechers",
    "levi's": "Levi's",
    "levis": "Levi's",
    "h&m": "H&M",
    "zara": "Zara",
    "gucci": "Gucci",
    "prada": "Prada",
    "gap": "Gap",
    "uniqlo": "Uniqlo",
}

_CATEGORY_KEYWORDS: dict[str, str] = {
    "running shoes": "Running Shoes",
    "running shoe": "Running Shoes",
    "sneakers": "Sneakers",
    "sneaker": "Sneakers",
    "t-shirt": "T-Shirts",
    "t shirt": "T-Shirts",
    "tshirt": "T-Shirts",
    "jeans": "Jeans",
    "jacket": "Jackets",
    "dress": "Dresses",
    "shorts": "Shorts",
    "hoodie": "Hoodies",
    "sandals": "Sandals",
    "boots": "Boots",
    "backpack": "Backpacks",
    "watch": "Watches",
    "sunglasses": "Sunglasses",
    "shirt": "Shirts",
}

_COLOR_KEYWORDS: dict[str, str] = {
    "red": "Red",
    "blue": "Blue",
    "green": "Green",
    "black": "Black",
    "white": "White",
    "yellow": "Yellow",
    "orange": "Orange",
    "purple": "Purple",
    "pink": "Pink",
    "brown": "Brown",
    "grey": "Gray",
    "gray": "Gray",
    "navy": "Navy",
    "beige": "Beige",
    "maroon": "Maroon",
    "gold": "Gold",
    "silver": "Silver",
    "multicolor": "Multicolor",
}

_MATERIAL_KEYWORDS: dict[str, str] = {
    "mesh": "Mesh",
    "cotton": "Cotton",
    "leather": "Leather",
    "polyester": "Polyester",
    "wool": "Wool",
    "denim": "Denim",
    "silk": "Silk",
    "nylon": "Nylon",
    "rubber": "Rubber",
    "suede": "Suede",
    "canvas": "Canvas",
    "linen": "Linen",
    "synthetic": "Synthetic",
    "spandex": "Spandex",
    "velvet": "Velvet",
}

_GENDER_KEYWORDS: dict[str, str] = {
    "men's": "Men",
    "mens": "Men",
    "man's": "Men",
    "men": "Men",
    "women's": "Women",
    "womens": "Women",
    "woman's": "Women",
    "women": "Women",
    "unisex": "Unisex",
    "boy's": "Boys",
    "boys": "Boys",
    "girl's": "Girls",
    "girls": "Girls",
    "kid's": "Kids",
    "kids": "Kids",
}

_STYLE_KEYWORDS: dict[str, str] = {
    "running": "Running",
    "casual": "Casual",
    "formal": "Formal",
    "sports": "Sports",
    "athletic": "Athletic",
    "vintage": "Vintage",
    "classic": "Classic",
    "trendy": "Trendy",
    "streetwear": "Streetwear",
}

_PATTERN_KEYWORDS: dict[str, str] = {
    "solid": "Solid",
    "striped": "Striped",
    "stripe": "Striped",
    "checked": "Checked",
    "plaid": "Plaid",
    "floral": "Floral",
    "polka dot": "Polka Dot",
    "printed": "Printed",
    "camouflage": "Camouflage",
    "camo": "Camouflage",
}

_SEASON_KEYWORDS: dict[str, str] = {
    "summer": "Summer",
    "winter": "Winter",
    "spring": "Spring",
    "autumn": "Fall",
    "fall": "Fall",
    "monsoon": "Monsoon",
    "all-season": "All-Season",
}

_OCCASION_KEYWORDS: dict[str, str] = {
    "party": "Party",
    "wedding": "Wedding",
    "office": "Office",
    "outdoor": "Outdoor",
    "travel": "Travel",
    "workout": "Workout",
    "gym": "Gym",
    "sports": "Sports",
    "casual": "Casual",
}

_AGE_GROUP_KEYWORDS: dict[str, str] = {
    "children": "Kids",
    "child": "Kids",
    "kids": "Kids",
    "kid": "Kids",
    "adult": "Adult",
    "toddler": "Toddler",
    "infant": "Infant",
    "baby": "Infant",
}

#: Free-text descriptive words that become tags on their own (not tied to
#: any single `ProductAttributes` field) — e.g. "lightweight", "durable".
_DESCRIPTOR_TAG_KEYWORDS: frozenset[str] = frozenset(
    {
        "lightweight",
        "breathable",
        "waterproof",
        "durable",
        "comfortable",
        "stylish",
        "premium",
        "soft",
        "warm",
        "stretchable",
        "washable",
        "eco-friendly",
        "sustainable",
        "quick-dry",
        "anti-slip",
        "cushioned",
    }
)

# Confidence assigned per rule "kind" — fixed and deterministic, not
# learned or tuned; a structured field the client explicitly submitted is
# trusted completely, keyword matches progressively less so as the
# attribute gets more open-ended/subjective.
_STRUCTURED_FIELD_CONFIDENCE = 1.0
_BRAND_KEYWORD_CONFIDENCE = 0.9
_CATEGORY_KEYWORD_CONFIDENCE = 0.85
_COLOR_KEYWORD_CONFIDENCE = 0.8
_GENDER_KEYWORD_CONFIDENCE = 0.85
_MATERIAL_KEYWORD_CONFIDENCE = 0.75
_STYLE_KEYWORD_CONFIDENCE = 0.7
_PATTERN_KEYWORD_CONFIDENCE = 0.7
_SEASON_KEYWORD_CONFIDENCE = 0.7
_AGE_GROUP_KEYWORD_CONFIDENCE = 0.7
_OCCASION_KEYWORD_CONFIDENCE = 0.65
_TAG_DESCRIPTOR_CONFIDENCE = 0.6


def _find_first_keyword(text: str, keywords: dict[str, str]) -> str | None:
    """Return the normalized value for the earliest-occurring keyword match.

    "Earliest occurring" (not "first in dict iteration order") is the
    deterministic tie-break when text mentions more than one candidate
    for the same attribute (e.g. "red and blue trim") — `ProductAttributes`
    fields are singular, so exactly one winner has to be chosen; picking
    whichever appears first in the actual text is simpler and at least as
    reasonable as any other fixed rule.
    """
    lowered = text.lower()
    best_index: int | None = None
    best_value: str | None = None
    for keyword, value in keywords.items():
        match = re.search(rf"\b{re.escape(keyword)}\b", lowered)
        if match and (best_index is None or match.start() < best_index):
            best_index = match.start()
            best_value = value
    return best_value


def _find_all_keywords(text: str, keywords: dict[str, str]) -> list[str]:
    """Return every distinct normalized value whose keyword appears in `text`.

    Unlike `_find_first_keyword`, this doesn't pick a single winner —
    used for tag generation, where (unlike a `ProductAttributes` field)
    there's no reason a product can't be tagged with more than one color
    or material mentioned in its description.
    """
    lowered = text.lower()
    found: list[str] = []
    for keyword, value in keywords.items():
        if re.search(rf"\b{re.escape(keyword)}\b", lowered) and value not in found:
            found.append(value)
    return found


class TextAttributeExtractionService:
    """Extracts catalog attributes and tags from product text via regex/lookup, not AI."""

    def extract_attributes(
        self,
        *,
        name: str,
        brand: str | None,
        category: str | None,
        description: str | None,
    ) -> list[AttributePrediction]:
        """Return one `AttributePrediction` per attribute this service could determine.

        `brand`/`category`, if already given, are trusted directly at
        confidence `1.0`; every other attribute (and brand/category when
        *not* already given) comes from keyword matching over
        `name`/`category`/`description` combined.
        """
        combined_text = _combine_text(name, category, description)
        predictions: list[AttributePrediction] = []

        if brand:
            predictions.append(_structured_prediction("brand", brand))
        else:
            _append_first_match(
                predictions, "brand", combined_text, _KNOWN_BRANDS, _BRAND_KEYWORD_CONFIDENCE
            )

        if category:
            predictions.append(_structured_prediction("category", category))
        else:
            _append_first_match(
                predictions,
                "category",
                combined_text,
                _CATEGORY_KEYWORDS,
                _CATEGORY_KEYWORD_CONFIDENCE,
            )

        for attribute, keywords, confidence in (
            ("color", _COLOR_KEYWORDS, _COLOR_KEYWORD_CONFIDENCE),
            ("material", _MATERIAL_KEYWORDS, _MATERIAL_KEYWORD_CONFIDENCE),
            ("gender", _GENDER_KEYWORDS, _GENDER_KEYWORD_CONFIDENCE),
            ("style", _STYLE_KEYWORDS, _STYLE_KEYWORD_CONFIDENCE),
            ("pattern", _PATTERN_KEYWORDS, _PATTERN_KEYWORD_CONFIDENCE),
            ("season", _SEASON_KEYWORDS, _SEASON_KEYWORD_CONFIDENCE),
            ("occasion", _OCCASION_KEYWORDS, _OCCASION_KEYWORD_CONFIDENCE),
            ("age_group", _AGE_GROUP_KEYWORDS, _AGE_GROUP_KEYWORD_CONFIDENCE),
        ):
            _append_first_match(predictions, attribute, combined_text, keywords, confidence)

        logger.info("Text attribute extraction complete: predictions=%d", len(predictions))
        return predictions

    def generate_tags(
        self,
        *,
        name: str,
        brand: str | None,
        category: str | None,
        description: str | None,
    ) -> list[CatalogTag]:
        """Return tags derived from this product's text.

        Reuses `extract_attributes` for the single-winner attributes
        (brand/category/the first-matched color, etc.) and additionally
        includes *every* color/material/style keyword found (not just the
        one `extract_attributes` picked as the winner) plus any free-text
        descriptor words (e.g. "lightweight") — tags aren't constrained to
        one value per category the way a `ProductAttributes` field is.
        """
        tags: list[CatalogTag] = []
        seen: set[str] = set()

        def _add(value: str, confidence: float) -> None:
            # Every caller below only ever passes an already-non-empty
            # value (an `AttributePrediction.value` or a lookup-dictionary
            # value) — the only real possibility worth guarding against is
            # a duplicate.
            normalized = value.strip().lower()
            if normalized in seen:
                return
            seen.add(normalized)
            tags.append(CatalogTag(tag=normalized, confidence=confidence, source=Source.TEXT))

        for prediction in self.extract_attributes(
            name=name, brand=brand, category=category, description=description
        ):
            _add(prediction.value, prediction.confidence)

        combined_text = _combine_text(name, category, description)
        for keywords, confidence in (
            (_COLOR_KEYWORDS, _COLOR_KEYWORD_CONFIDENCE),
            (_MATERIAL_KEYWORDS, _MATERIAL_KEYWORD_CONFIDENCE),
            (_STYLE_KEYWORDS, _STYLE_KEYWORD_CONFIDENCE),
        ):
            for value in _find_all_keywords(combined_text, keywords):
                _add(value, confidence)

        for descriptor in sorted(_DESCRIPTOR_TAG_KEYWORDS):
            if re.search(rf"\b{re.escape(descriptor)}\b", combined_text.lower()):
                _add(descriptor, _TAG_DESCRIPTOR_CONFIDENCE)

        logger.info("Text tag generation complete: tags=%d", len(tags))
        return tags


def _combine_text(name: str, category: str | None, description: str | None) -> str:
    """Join the fields worth scanning for keywords into one string."""
    return " ".join(part for part in (name, category, description) if part)


def _structured_prediction(attribute: str, value: str) -> AttributePrediction:
    return AttributePrediction(
        attribute=attribute,
        value=value,
        confidence=_STRUCTURED_FIELD_CONFIDENCE,
        source=Source.TEXT,
    )


def _append_first_match(
    predictions: list[AttributePrediction],
    attribute: str,
    text: str,
    keywords: dict[str, str],
    confidence: float,
) -> None:
    value = _find_first_keyword(text, keywords)
    if value is not None:
        predictions.append(
            AttributePrediction(
                attribute=attribute, value=value, confidence=confidence, source=Source.TEXT
            )
        )
