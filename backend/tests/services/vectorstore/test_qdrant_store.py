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
    def test_creates_the_collection_if_it_does_not_exist(self) -> None:
        client = QdrantClient(location=":memory:")
        assert client.collection_exists("widgets") is False

        QdrantVectorStore(client=client, collection_name="widgets", vector_size=_VECTOR_SIZE)

        assert client.collection_exists("widgets") is True

    def test_is_idempotent_against_an_already_existing_collection(self) -> None:
        client = QdrantClient(location=":memory:")
        QdrantVectorStore(client=client, collection_name="widgets", vector_size=_VECTOR_SIZE)

        # Constructing a second store against the same client/collection
        # must not raise or attempt to recreate it.
        QdrantVectorStore(client=client, collection_name="widgets", vector_size=_VECTOR_SIZE)

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
    async def test_search_against_a_missing_collection_raises_vector_store_exception(
        self,
    ) -> None:
        client = QdrantClient(location=":memory:")
        store = QdrantVectorStore(client=client, collection_name="real", vector_size=_VECTOR_SIZE)
        # Force an operation against a collection this store's client
        # never created, to exercise the error-wrapping path.
        store._collection_name = "does-not-exist"

        with pytest.raises(VectorStoreException):
            await store.search([1.0, 0.0, 0.0, 0.0], top_k=5)
