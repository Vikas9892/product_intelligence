"""Unit tests for `QdrantVectorStore`.

Every test runs against a real `QdrantClient(location=":memory:")` — the
official client's own local, in-process mode, not a fake or a mock. This
gives genuine confidence that our filter/point/collection construction is
actually compatible with the real `qdrant-client` API (which changed
`search` to `query_points` between versions — see the module docstring
reasoning in `qdrant_store.py`), without needing a running Qdrant server
for the test suite.
"""

from uuid import uuid4

import pytest
from qdrant_client import QdrantClient

from app.exceptions.errors import VectorStoreException
from app.services.vectorstore.base import VectorRecord
from app.services.vectorstore.qdrant_store import QdrantVectorStore

_VECTOR_SIZE = 4


def _store(*, collection_name: str = "test_collection") -> QdrantVectorStore:
    client = QdrantClient(location=":memory:")
    return QdrantVectorStore(
        client=client, collection_name=collection_name, vector_size=_VECTOR_SIZE
    )


class TestCollectionCreation:
    def test_construction_does_not_touch_qdrant(self) -> None:
        """Constructing a store must not require a live connection.

        `ProductService`/`SearchService` build a `QdrantVectorStore` as
        part of their own construction — if that eagerly hit Qdrant, every
        dependency-injection unit test (and the app itself, at startup)
        would need a running Qdrant server just to build an object graph.
        """
        client = QdrantClient(location=":memory:")

        QdrantVectorStore(client=client, collection_name="widgets", vector_size=_VECTOR_SIZE)

        assert client.collection_exists("widgets") is False

    async def test_creates_the_collection_on_first_use(self) -> None:
        client = QdrantClient(location=":memory:")
        store = QdrantVectorStore(
            client=client, collection_name="widgets", vector_size=_VECTOR_SIZE
        )
        assert client.collection_exists("widgets") is False

        await store.exists(uuid4())

        assert client.collection_exists("widgets") is True

    async def test_is_idempotent_against_an_already_existing_collection(self) -> None:
        client = QdrantClient(location=":memory:")
        store = QdrantVectorStore(
            client=client, collection_name="widgets", vector_size=_VECTOR_SIZE
        )
        await store.exists(uuid4())

        # A second store against the same client/collection must not
        # raise or attempt to recreate it on its own first use.
        second_store = QdrantVectorStore(
            client=client, collection_name="widgets", vector_size=_VECTOR_SIZE
        )
        await second_store.exists(uuid4())

        assert client.collection_exists("widgets") is True


class TestUpsertAndExists:
    async def test_exists_is_false_before_upsert_and_true_after(self) -> None:
        store = _store()
        product_id = uuid4()

        assert await store.exists(product_id) is False

        await store.upsert([VectorRecord(product_id=product_id, vector=[1.0, 0.0, 0.0, 0.0])])

        assert await store.exists(product_id) is True

    async def test_upsert_of_an_empty_list_is_a_no_op(self) -> None:
        store = _store()

        await store.upsert([])  # must not raise


class TestSearch:
    async def test_finds_the_closest_match_first(self) -> None:
        store = _store()
        closest_id = uuid4()
        far_id = uuid4()
        await store.upsert(
            [
                VectorRecord(product_id=closest_id, vector=[1.0, 0.0, 0.0, 0.0]),
                VectorRecord(product_id=far_id, vector=[0.0, 1.0, 0.0, 0.0]),
            ]
        )

        results = await store.search([1.0, 0.0, 0.0, 0.0], top_k=5)

        assert results[0].product_id == closest_id

    async def test_search_returns_metadata(self) -> None:
        store = _store()
        product_id = uuid4()
        await store.upsert(
            [
                VectorRecord(
                    product_id=product_id,
                    vector=[1.0, 0.0, 0.0, 0.0],
                    metadata={"category": "shoes", "name": "Widget"},
                )
            ]
        )

        results = await store.search([1.0, 0.0, 0.0, 0.0], top_k=5)

        assert results[0].metadata == {"category": "shoes", "name": "Widget"}


class TestDelete:
    async def test_delete_removes_the_record(self) -> None:
        store = _store()
        product_id = uuid4()
        await store.upsert([VectorRecord(product_id=product_id, vector=[1.0, 0.0, 0.0, 0.0])])

        await store.delete([product_id])

        assert await store.exists(product_id) is False

    async def test_delete_of_an_empty_list_is_a_no_op(self) -> None:
        store = _store()

        await store.delete([])  # must not raise


class TestHealth:
    async def test_returns_true_when_reachable(self) -> None:
        store = _store()

        assert await store.health() is True


class TestErrorWrapping:
    async def test_search_against_an_unreachable_client_raises_vector_store_exception(
        self,
    ) -> None:
        # An unreachable URL (not `:memory:`) so the underlying client
        # call genuinely fails, exercising `_ensure_collection`'s
        # error-wrapping path (`search`'s own lazy collection check runs
        # before the search request itself).
        client = QdrantClient(url="http://localhost:1", timeout=1)
        store = QdrantVectorStore(client=client, collection_name="real", vector_size=_VECTOR_SIZE)

        with pytest.raises(VectorStoreException):
            await store.search([1.0, 0.0, 0.0, 0.0], top_k=5)
