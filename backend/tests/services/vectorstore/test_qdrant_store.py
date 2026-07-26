"""Unit tests for `QdrantVectorStore`.

Every test runs against a real `QdrantClient(location=":memory:")` — the
official client's own local, in-process mode, not a fake or a mock. This
gives genuine confidence that our filter/point/collection construction is
actually compatible with the real `qdrant-client` API (which changed
`search` to `query_points` between versions — see the module docstring
reasoning in `qdrant_store.py`), without needing a running Qdrant server
for the test suite.

`_BrokenClient` is the one exception: a thin wrapper delegating to a real
in-memory client for every method except one deliberately-broken method,
used to exercise `upsert`/`delete`/`exists`'s own error-wrapping paths
independently of `_ensure_collection`'s (an unreachable client fails at
`_ensure_collection` before ever reaching the operation itself).
"""

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, cast
from uuid import uuid4

import pytest
from qdrant_client import QdrantClient

from app.exceptions.errors import VectorStoreException
from app.services.vectorstore.base import VectorRecord
from app.services.vectorstore.qdrant_store import QdrantVectorStore

_VECTOR_SIZE = 4


class _BrokenClient:
    """Delegates every call to a real in-memory client except `fail_method`."""

    def __init__(self, real_client: QdrantClient, *, fail_method: str) -> None:
        self._real = real_client
        self._fail_method = fail_method

    def __getattr__(self, name: str) -> Any:
        if name == self._fail_method:

            def _raise(*args: Any, **kwargs: Any) -> Any:
                raise RuntimeError("boom")

            return _raise
        return getattr(self._real, name)


class _SlowCollectionExistsClient:
    """Delegates to a real in-memory client, but `collection_exists` sleeps first.

    Widens the race window `_ensure_collection`'s double-checked locking
    closes — without the delay, concurrent callers would very likely
    never actually overlap inside the lock on a fast local test run.
    """

    def __init__(self, real_client: QdrantClient, *, delay_seconds: float) -> None:
        self._real = real_client
        self._delay_seconds = delay_seconds
        self.create_collection_calls = 0

    def collection_exists(self, *args: Any, **kwargs: Any) -> bool:
        time.sleep(self._delay_seconds)
        return self._real.collection_exists(*args, **kwargs)

    def create_collection(self, *args: Any, **kwargs: Any) -> bool:
        self.create_collection_calls += 1
        return self._real.create_collection(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


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

    async def test_upserting_the_same_id_twice_overwrites_rather_than_duplicates(
        self,
    ) -> None:
        store = _store()
        product_id = uuid4()
        await store.upsert(
            [
                VectorRecord(
                    product_id=product_id, vector=[1.0, 0.0, 0.0, 0.0], metadata={"name": "Old"}
                )
            ]
        )

        await store.upsert(
            [
                VectorRecord(
                    product_id=product_id, vector=[0.0, 1.0, 0.0, 0.0], metadata={"name": "New"}
                )
            ]
        )

        results = await store.search([0.0, 1.0, 0.0, 0.0], top_k=10)
        matches = [result for result in results if result.product_id == product_id]
        assert len(matches) == 1
        assert matches[0].metadata == {"name": "New"}


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

    async def test_returns_an_empty_list_against_an_empty_collection(self) -> None:
        store = _store()

        results = await store.search([1.0, 0.0, 0.0, 0.0], top_k=5)

        assert results == []

    async def test_limits_results_to_top_k_even_with_more_candidates(self) -> None:
        store = _store()
        await store.upsert(
            [
                VectorRecord(product_id=uuid4(), vector=[1.0, 0.0, 0.0, 0.0]),
                VectorRecord(product_id=uuid4(), vector=[0.9, 0.1, 0.0, 0.0]),
                VectorRecord(product_id=uuid4(), vector=[0.0, 1.0, 0.0, 0.0]),
                VectorRecord(product_id=uuid4(), vector=[0.0, 0.0, 1.0, 0.0]),
            ]
        )

        results = await store.search([1.0, 0.0, 0.0, 0.0], top_k=2)

        assert len(results) == 2

    async def test_orders_results_by_descending_similarity(self) -> None:
        store = _store()
        closest_id = uuid4()
        middle_id = uuid4()
        farthest_id = uuid4()
        await store.upsert(
            [
                VectorRecord(product_id=farthest_id, vector=[0.0, 1.0, 0.0, 0.0]),
                VectorRecord(product_id=closest_id, vector=[1.0, 0.0, 0.0, 0.0]),
                VectorRecord(product_id=middle_id, vector=[0.7, 0.7, 0.0, 0.0]),
            ]
        )

        results = await store.search([1.0, 0.0, 0.0, 0.0], top_k=3)

        assert [result.product_id for result in results] == [closest_id, middle_id, farthest_id]
        assert results[0].score >= results[1].score >= results[2].score

    async def test_filters_restrict_results_to_matching_metadata(self) -> None:
        store = _store()
        shoe_id = uuid4()
        shirt_id = uuid4()
        await store.upsert(
            [
                VectorRecord(
                    product_id=shoe_id, vector=[1.0, 0.0, 0.0, 0.0], metadata={"category": "shoes"}
                ),
                VectorRecord(
                    product_id=shirt_id,
                    vector=[1.0, 0.0, 0.0, 0.0],
                    metadata={"category": "shirts"},
                ),
            ]
        )

        results = await store.search([1.0, 0.0, 0.0, 0.0], top_k=10, filters={"category": "shirts"})

        assert [result.product_id for result in results] == [shirt_id]


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

    async def test_returns_false_when_unreachable(self) -> None:
        # health() never calls `_ensure_collection` — an unreachable
        # client exercises its own try/except directly, not that one.
        client = QdrantClient(url="http://localhost:1", timeout=1)
        store = QdrantVectorStore(client=client, collection_name="real", vector_size=_VECTOR_SIZE)

        assert await store.health() is False


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

    async def test_upsert_wraps_a_client_failure(self) -> None:
        broken = _BrokenClient(QdrantClient(location=":memory:"), fail_method="upsert")
        store = QdrantVectorStore(
            client=cast(QdrantClient, broken), collection_name="real", vector_size=_VECTOR_SIZE
        )

        with pytest.raises(VectorStoreException):
            await store.upsert([VectorRecord(product_id=uuid4(), vector=[1.0, 0.0, 0.0, 0.0])])

    async def test_search_wraps_a_client_failure_distinct_from_ensure_collection(
        self,
    ) -> None:
        # Unlike the unreachable-client test above, this collection
        # genuinely exists (a real in-memory client) — only the search
        # call itself fails, exercising `search`'s own try/except rather
        # than `_ensure_collection`'s.
        broken = _BrokenClient(QdrantClient(location=":memory:"), fail_method="query_points")
        store = QdrantVectorStore(
            client=cast(QdrantClient, broken), collection_name="real", vector_size=_VECTOR_SIZE
        )
        await store.upsert([VectorRecord(product_id=uuid4(), vector=[1.0, 0.0, 0.0, 0.0])])

        with pytest.raises(VectorStoreException):
            await store.search([1.0, 0.0, 0.0, 0.0], top_k=5)

    async def test_delete_wraps_a_client_failure(self) -> None:
        broken = _BrokenClient(QdrantClient(location=":memory:"), fail_method="delete")
        store = QdrantVectorStore(
            client=cast(QdrantClient, broken), collection_name="real", vector_size=_VECTOR_SIZE
        )

        with pytest.raises(VectorStoreException):
            await store.delete([uuid4()])

    async def test_exists_wraps_a_client_failure(self) -> None:
        broken = _BrokenClient(QdrantClient(location=":memory:"), fail_method="retrieve")
        store = QdrantVectorStore(
            client=cast(QdrantClient, broken), collection_name="real", vector_size=_VECTOR_SIZE
        )

        with pytest.raises(VectorStoreException):
            await store.exists(uuid4())


class TestThreadSafety:
    async def test_concurrent_first_use_creates_the_collection_only_once(self) -> None:
        real_client = QdrantClient(location=":memory:")
        slow_client = _SlowCollectionExistsClient(real_client, delay_seconds=0.05)
        store = QdrantVectorStore(
            client=cast(QdrantClient, slow_client),
            collection_name="widgets",
            vector_size=_VECTOR_SIZE,
        )

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: store._ensure_collection(), range(8)))

        assert slow_client.create_collection_calls == 1
