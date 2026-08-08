"""End-to-end facet filtering against a real in-memory Qdrant.

The bug these cover: image-only and text-only search worked, but adding a brand
or category filter returned zero results every time. Ingest canonicalised
category and merely trimmed brand; the query path sent the raw user string into
`MatchValue`, which is exact and case-sensitive.

These exercise a real `QdrantClient(location=":memory:")` rather than asserting
on the shape of a filter object, because the original defect was not a
malformed filter — it was a perfectly well-formed filter that matched nothing.
Only a real match/no-match can tell those apart.
"""

from typing import cast
from uuid import UUID, uuid4

import pytest
from qdrant_client import QdrantClient

from app.models.search import ProductFilters
from app.services.vectorstore.base import VectorCollection, VectorRecord
from app.services.vectorstore.qdrant_store import QdrantVectorStore
from app.utils.facets import normalize_facet

_NIKE = UUID("11111111-1111-1111-1111-111111111111")
_ADIDAS = UUID("22222222-2222-2222-2222-222222222222")


def _payload(*, name: str, brand: str, category: str) -> dict[str, object]:
    """Exactly what `ProductService` writes, canonical keys included."""
    return {
        "name": name,
        "brand": brand,
        "category": category,
        "brand_key": normalize_facet(brand),
        "category_key": normalize_facet(category),
        "price": 4000.0,
    }


_VECTOR_SIZE = 8


@pytest.fixture
def store() -> QdrantVectorStore:
    return QdrantVectorStore(
        client=QdrantClient(location=":memory:"),
        image_collection_name="test_image_facets",
        image_vector_size=_VECTOR_SIZE,
        text_collection_name="test_text_facets",
        text_vector_size=_VECTOR_SIZE,
    )


async def _seed(store: QdrantVectorStore) -> None:
    await store.upsert(
        VectorCollection.TEXT,
        [
            VectorRecord(
                product_id=_NIKE,
                vector=[1.0] * _VECTOR_SIZE,
                # Stored exactly as ingest would store it: category slugified
                # from "Men Shoes", brand keeping its display casing.
                metadata=_payload(name="nike shoes", brand="Nike", category="men-shoes"),
            ),
            VectorRecord(
                product_id=_ADIDAS,
                vector=[0.9] * _VECTOR_SIZE,
                metadata=_payload(name="adidas shoes", brand="Adidas", category="men-shoes"),
            ),
        ],
    )


async def _search(store: QdrantVectorStore, filters: ProductFilters | None) -> list[UUID]:
    results = await store.search(
        VectorCollection.TEXT, [1.0] * _VECTOR_SIZE, top_k=10, filters=filters
    )
    return [result.product_id for result in results]


class TestFacetFiltering:
    async def test_a_product_ingested_as_men_shoes_is_found_by_the_typed_form(
        self, store: QdrantVectorStore
    ) -> None:
        """Ingested as "Men Shoes" (stored "men-shoes"); searched as "men shoes"."""
        await _seed(store)

        found = await _search(store, ProductFilters(brand="nike", category="men shoes"))

        assert found == [_NIKE]

    @pytest.mark.parametrize(
        ("brand", "category"),
        [
            ("NIKE", " men-shoes "),
            ("nike", "Men  Shoes"),
            (" Nike ", "MEN SHOES"),
            ("Nike", "men_shoes"),
        ],
    )
    async def test_case_and_spacing_variants_all_match(
        self, store: QdrantVectorStore, brand: str, category: str
    ) -> None:
        await _seed(store)

        found = await _search(store, ProductFilters(brand=brand, category=category))

        assert found == [_NIKE]

    async def test_the_filter_still_actually_filters(self, store: QdrantVectorStore) -> None:
        """A genuinely non-matching facet must return nothing."""
        await _seed(store)

        assert await _search(store, ProductFilters(brand="Puma")) == []
        assert await _search(store, ProductFilters(category="women-shoes")) == []

    async def test_a_different_real_brand_selects_only_that_brand(
        self, store: QdrantVectorStore
    ) -> None:
        await _seed(store)

        assert await _search(store, ProductFilters(brand="adidas")) == [_ADIDAS]


class TestEmptyFacets:
    """An empty box must apply no filter, not a filter on the empty string."""

    @pytest.mark.parametrize("blank", ["", "   ", None])
    async def test_a_blank_brand_does_not_reduce_results(
        self, store: QdrantVectorStore, blank: str | None
    ) -> None:
        await _seed(store)
        unfiltered = await _search(store, None)

        assert await _search(store, ProductFilters(brand=blank)) == unfiltered

    @pytest.mark.parametrize("blank", ["", "   ", None])
    async def test_a_blank_category_does_not_reduce_results(
        self, store: QdrantVectorStore, blank: str | None
    ) -> None:
        await _seed(store)
        unfiltered = await _search(store, None)

        assert await _search(store, ProductFilters(category=blank)) == unfiltered

    async def test_unfiltered_search_still_returns_everything(
        self, store: QdrantVectorStore
    ) -> None:
        """Image-only and text-only search must not regress."""
        await _seed(store)

        assert len(await _search(store, None)) == 2


class TestRoundTrip:
    async def test_the_ingest_value_and_the_query_value_agree(self) -> None:
        """What ingest writes and what a query sends must be the same string."""
        assert (
            normalize_facet("Men Shoes")
            == _payload(name="x", brand="Nike", category="men-shoes")["category_key"]
        )
        assert (
            normalize_facet("nike")
            == _payload(name="x", brand="Nike", category="men-shoes")["brand_key"]
        )


class _IndexRecordingClient:
    """Delegates to a real in-memory client, recording payload-index calls.

    Asserted on calls rather than on `get_collection().payload_schema`, because
    Qdrant's local (`:memory:`) mode does not track payload indexes — it
    reports an empty schema however many indexes were created. Checking the
    calls is what can actually be verified without a server.
    """

    def __init__(self, real_client: QdrantClient) -> None:
        self._real = real_client
        self.indexed_fields: list[str] = []

    def create_payload_index(self, *args: object, **kwargs: object) -> object:
        field = kwargs.get("field_name")
        if isinstance(field, str):
            self.indexed_fields.append(field)
        return self._real.create_payload_index(*args, **kwargs)  # type: ignore[arg-type]

    def __getattr__(self, name: str) -> object:
        return getattr(self._real, name)


class TestPayloadIndexes:
    async def test_facet_indexes_are_created_with_the_collection(self) -> None:
        """A fresh environment must not silently lack them."""
        recorder = _IndexRecordingClient(QdrantClient(location=":memory:"))
        store = QdrantVectorStore(
            client=cast(QdrantClient, recorder),
            image_collection_name="idx_image",
            image_vector_size=_VECTOR_SIZE,
            text_collection_name="idx_text",
            text_vector_size=_VECTOR_SIZE,
        )

        await _seed(store)

        assert "brand_key" in recorder.indexed_fields
        assert "category_key" in recorder.indexed_fields


class TestUnindexedProductsAreNotFound:
    async def test_a_product_without_facet_keys_does_not_match(
        self, store: QdrantVectorStore
    ) -> None:
        """Documents the migration requirement rather than hiding it.

        Products indexed before canonical keys existed carry none, so they
        cannot be filtered on. Re-indexing is required — see the commit
        message and DEMO.md.
        """
        await store.upsert(
            VectorCollection.TEXT,
            [
                VectorRecord(
                    product_id=uuid4(),
                    vector=[1.0] * _VECTOR_SIZE,
                    metadata={"name": "legacy", "brand": "Nike", "category": "men-shoes"},
                )
            ],
        )

        assert await _search(store, ProductFilters(brand="Nike")) == []
