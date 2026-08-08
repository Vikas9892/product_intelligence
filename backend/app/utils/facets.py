"""Canonical form for filterable facet values.

The one place that decides what `"Men Shoes"`, `" men-shoes "` and `"MEN
SHOES"` all mean. Both the ingest path and the query path call it, which is
the whole point: this bug existed because two code paths independently decided
how to canonicalise the same field.

The failure it fixes
--------------------

`ProductService` slugified category at ingest (`"Men shoes"` -> `"men-shoes"`)
and merely trimmed brand (`"Nike"` stayed `"Nike"`). `QdrantVectorStore.
_build_filter` passed the raw user string straight into `MatchValue`, which is
exact and case-sensitive. Confirmed by scrolling Qdrant directly:

    category = "men-shoes"  -> 5 points     category = "Men shoes" -> 0 points
    brand    = "Nike"       -> 1 point      brand    = "nike"      -> 0 points

So any filtered search returned nothing unless the user happened to type the
stored string exactly, character for character.

Fixing it by adding a second normaliser on the query side would reproduce the
original failure in a new place -- two implementations drifting apart is what
caused this. There is one function, and both paths import it.

Convention
----------

Casefold, collapse any run of non-alphanumeric characters to a single hyphen,
strip hyphens from the ends. That is exactly the convention the ingest path
already applied to category, so *stored category values need no migration*.

`None` and blank strings normalise to `None`, meaning "no filter" -- never a
filter on the empty string. An empty brand box must not silently exclude every
product.
"""

import re

#: Any run of characters that is not a letter or digit becomes one hyphen.
#: Deliberately aggressive: it collapses spaces, underscores, ampersands,
#: punctuation and repeated separators alike, so "Men  Shoes", "men_shoes" and
#: "Men-Shoes" all land on the same key.
_SEPARATOR_RUN = re.compile(r"[^a-z0-9]+")


def normalize_facet(value: str | None) -> str | None:
    """Return `value`'s canonical facet key, or `None` if it filters nothing.

    `casefold` rather than `lower`, so non-ASCII pairs fold correctly (German
    "ß" and "ss" reach the same key). Digits survive, so "Nike 90s" keys as
    "nike-90s" rather than losing the number.
    """
    if value is None:
        return None
    slug = _SEPARATOR_RUN.sub("-", value.strip().casefold()).strip("-")
    return slug or None
