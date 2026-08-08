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

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, cast
from uuid import uuid4

import pytest
from qdrant_client import QdrantClient

from app.exceptions.errors import VectorStoreException
from app.models.search import ProductFilters
from app.services.vectorstore.base import VectorCollection, VectorRecord
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

    Used only where the assertion is a *count* (how many creates happened),
    which no amount of machine load can perturb. The one test that asserted
    elapsed time uses `_RendezvousClient` instead.
    """

    def __init__(self, real_client: QdrantClient, *, delay_seconds: float) -> None:
        self._real = real_client
        self._delay_seconds = delay_seconds
        self.create_collection_calls = 0

    def collection_exists(self, *args: Any, **kwargs: Any) -> bool:
        time.sleep(self._delay_seconds)
        return bool(self._real.collection_exists(*args, **kwargs))

    def create_collection(self, *args: Any, **kwargs: Any) -> Any:
        self.create_collection_calls += 1
        return self._real.create_collection(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


class _RendezvousClient:
    """Delegates to a real in-memory client, but `collection_exists` rendezvouses.

    Each call waits at a two-party barrier before proceeding. That turns "do
    the two collections lock independently?" into a question with a
    deterministic answer instead of a timing measurement:

    * independent locks -> both callers reach the barrier, it releases, both
      proceed;
    * one shared lock -> the second caller never reaches it, and the first
      times out with `BrokenBarrierError`.

    This replaces a wall-clock assertion (`elapsed < 0.09` against a 0.05s
    sleep) that failed intermittently under load. The property under test was
    never really "it finished quickly" -- it was "these two ran concurrently",
    and a barrier states that directly.
    """

    def __init__(self, real_client: QdrantClient, *, timeout_seconds: float = 5.0) -> None:
        self._real = real_client
        self._barrier = threading.Barrier(2, timeout=timeout_seconds)
        self.create_collection_calls = 0
        self.rendezvous_failed = False

    def collection_exists(self, *args: Any, **kwargs: Any) -> bool:
        try:
            self._barrier.wait()
        except threading.BrokenBarrierError:
            # Serialized: the other caller never arrived.
            self.rendezvous_failed = True
        return self._real.collection_exists(*args, **kwargs)

    def create_collection(self, *args: Any, **kwargs: Any) -> bool:
        self.create_collection_calls += 1
        return self._real.create_collection(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def _store(
    *,
    client: QdrantClient | None = None,
    image_collection_name: str = "test_image_collection",
    text_collection_name: str = "test_text_collection",
) -> QdrantVectorStore:
    return QdrantVectorStore(
        client=client if client is not None else QdrantClient(location=":memory:"),
        image_collection_name=image_collection_name,
        image_vector_size=_VECTOR_SIZE,
        text_collection_name=text_collection_name,
        text_vector_size=_VECTOR_SIZE,
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

        _store(client=client, image_collection_name="widgets-image")

        assert client.collection_exists("widgets-image") is False

    async def test_creates_the_image_collection_on_first_use(self) -> None:
        client = QdrantClient(location=":memory:")
        store = _store(client=client, image_collection_name="widgets-image")
        assert client.collection_exists("widgets-image") is False

        await store.exists(VectorCollection.IMAGE, uuid4())

        assert client.collection_exists("widgets-image") is True

    async def test_creates_the_text_collection_on_first_use(self) -> None:
        client = QdrantClient(location=":memory:")
        store = _store(client=client, text_collection_name="widgets-text")
        assert client.collection_exists("widgets-text") is False

        await store.exists(VectorCollection.TEXT, uuid4())

        assert client.collection_exists("widgets-text") is True

    async def test_using_one_collection_does_not_create_the_other(self) -> None:
        client = QdrantClient(location=":memory:")
        store = _store(
            client=client,
            image_collection_name="widgets-image",
            text_collection_name="widgets-text",
        )

        await store.exists(VectorCollection.IMAGE, uuid4())

        assert client.collection_exists("widgets-image") is True
        assert client.collection_exists("widgets-text") is False

    async def test_is_idempotent_against_an_already_existing_collection(self) -> None:
        client = QdrantClient(location=":memory:")
        store = _store(client=client, image_collection_name="widgets-image")
        await store.exists(VectorCollection.IMAGE, uuid4())

        # A second store against the same client/collection must not
        # raise or attempt to recreate it on its own first use.
        second_store = _store(client=client, image_collection_name="widgets-image")
        await second_store.exists(VectorCollection.IMAGE, uuid4())

        assert client.collection_exists("widgets-image") is True


class TestCollectionIsolation:
    async def test_a_record_upserted_into_image_does_not_appear_in_text(self) -> None:
        store = _store()
        product_id = uuid4()

        await store.upsert(
            VectorCollection.IMAGE,
            [VectorRecord(product_id=product_id, vector=[1.0, 0.0, 0.0, 0.0])],
        )

        assert await store.exists(VectorCollection.IMAGE, product_id) is True
        assert await store.exists(VectorCollection.TEXT, product_id) is False

    async def test_the_same_product_id_can_exist_in_both_collections_independently(self) -> None:
        store = _store()
        product_id = uuid4()

        await store.upsert(
            VectorCollection.IMAGE,
            [
                VectorRecord(
                    product_id=product_id, vector=[1.0, 0.0, 0.0, 0.0], metadata={"m": "image"}
                )
            ],
        )
        await store.upsert(
            VectorCollection.TEXT,
            [
                VectorRecord(
                    product_id=product_id, vector=[0.0, 1.0, 0.0, 0.0], metadata={"m": "text"}
                )
            ],
        )

        image_results = await store.search(VectorCollection.IMAGE, [1.0, 0.0, 0.0, 0.0], top_k=5)
        text_results = await store.search(VectorCollection.TEXT, [0.0, 1.0, 0.0, 0.0], top_k=5)

        assert image_results[0].metadata == {"m": "image"}
        assert text_results[0].metadata == {"m": "text"}


class TestUpsertAndExists:
    async def test_exists_is_false_before_upsert_and_true_after(self) -> None:
        store = _store()
        product_id = uuid4()

        assert await store.exists(VectorCollection.IMAGE, product_id) is False

        await store.upsert(
            VectorCollection.IMAGE,
            [VectorRecord(product_id=product_id, vector=[1.0, 0.0, 0.0, 0.0])],
        )

        assert await store.exists(VectorCollection.IMAGE, product_id) is True

    async def test_upsert_of_an_empty_list_is_a_no_op(self) -> None:
        store = _store()

        await store.upsert(VectorCollection.IMAGE, [])  # must not raise

    async def test_upserting_the_same_id_twice_overwrites_rather_than_duplicates(
        self,
    ) -> None:
        store = _store()
        product_id = uuid4()
        await store.upsert(
            VectorCollection.IMAGE,
            [
                VectorRecord(
                    product_id=product_id, vector=[1.0, 0.0, 0.0, 0.0], metadata={"name": "Old"}
                )
            ],
        )

        await store.upsert(
            VectorCollection.IMAGE,
            [
                VectorRecord(
                    product_id=product_id, vector=[0.0, 1.0, 0.0, 0.0], metadata={"name": "New"}
                )
            ],
        )

        results = await store.search(VectorCollection.IMAGE, [0.0, 1.0, 0.0, 0.0], top_k=10)
        matches = [result for result in results if result.product_id == product_id]
        assert len(matches) == 1
        assert matches[0].metadata == {"name": "New"}


class TestRetrieve:
    async def test_retrieves_the_stored_vector_and_metadata(self) -> None:
        store = _store()
        product_id = uuid4()
        await store.upsert(
            VectorCollection.IMAGE,
            [
                VectorRecord(
                    product_id=product_id,
                    vector=[1.0, 0.0, 0.0, 0.0],
                    metadata={"brand": "Nike"},
                )
            ],
        )

        point = await store.retrieve(VectorCollection.IMAGE, product_id)

        assert point is not None
        assert point.product_id == product_id
        assert point.vector == [1.0, 0.0, 0.0, 0.0]
        assert point.metadata == {"brand": "Nike"}

    async def test_returns_none_for_an_absent_product(self) -> None:
        store = _store()

        point = await store.retrieve(VectorCollection.IMAGE, uuid4())

        assert point is None

    async def test_retrieve_is_isolated_per_collection(self) -> None:
        store = _store()
        product_id = uuid4()
        await store.upsert(
            VectorCollection.IMAGE,
            [VectorRecord(product_id=product_id, vector=[1.0, 0.0, 0.0, 0.0])],
        )

        assert await store.retrieve(VectorCollection.TEXT, product_id) is None


class TestSearch:
    async def test_finds_the_closest_match_first(self) -> None:
        store = _store()
        closest_id = uuid4()
        far_id = uuid4()
        await store.upsert(
            VectorCollection.IMAGE,
            [
                VectorRecord(product_id=closest_id, vector=[1.0, 0.0, 0.0, 0.0]),
                VectorRecord(product_id=far_id, vector=[0.0, 1.0, 0.0, 0.0]),
            ],
        )

        results = await store.search(VectorCollection.IMAGE, [1.0, 0.0, 0.0, 0.0], top_k=5)

        assert results[0].product_id == closest_id

    async def test_search_returns_metadata(self) -> None:
        store = _store()
        product_id = uuid4()
        await store.upsert(
            VectorCollection.IMAGE,
            [
                VectorRecord(
                    product_id=product_id,
                    vector=[1.0, 0.0, 0.0, 0.0],
                    metadata={"category": "shoes", "name": "Widget"},
                )
            ],
        )

        results = await store.search(VectorCollection.IMAGE, [1.0, 0.0, 0.0, 0.0], top_k=5)

        assert results[0].metadata == {"category": "shoes", "name": "Widget"}

    async def test_returns_an_empty_list_against_an_empty_collection(self) -> None:
        store = _store()

        results = await store.search(VectorCollection.IMAGE, [1.0, 0.0, 0.0, 0.0], top_k=5)

        assert results == []

    async def test_limits_results_to_top_k_even_with_more_candidates(self) -> None:
        store = _store()
        await store.upsert(
            VectorCollection.IMAGE,
            [
                VectorRecord(product_id=uuid4(), vector=[1.0, 0.0, 0.0, 0.0]),
                VectorRecord(product_id=uuid4(), vector=[0.9, 0.1, 0.0, 0.0]),
                VectorRecord(product_id=uuid4(), vector=[0.0, 1.0, 0.0, 0.0]),
                VectorRecord(product_id=uuid4(), vector=[0.0, 0.0, 1.0, 0.0]),
            ],
        )

        results = await store.search(VectorCollection.IMAGE, [1.0, 0.0, 0.0, 0.0], top_k=2)

        assert len(results) == 2

    async def test_orders_results_by_descending_similarity(self) -> None:
        store = _store()
        closest_id = uuid4()
        middle_id = uuid4()
        farthest_id = uuid4()
        await store.upsert(
            VectorCollection.IMAGE,
            [
                VectorRecord(product_id=farthest_id, vector=[0.0, 1.0, 0.0, 0.0]),
                VectorRecord(product_id=closest_id, vector=[1.0, 0.0, 0.0, 0.0]),
                VectorRecord(product_id=middle_id, vector=[0.7, 0.7, 0.0, 0.0]),
            ],
        )

        results = await store.search(VectorCollection.IMAGE, [1.0, 0.0, 0.0, 0.0], top_k=3)

        assert [result.product_id for result in results] == [closest_id, middle_id, farthest_id]
        assert results[0].score >= results[1].score >= results[2].score

    async def test_category_filter_restricts_results_to_matching_metadata(self) -> None:
        store = _store()
        shoe_id = uuid4()
        shirt_id = uuid4()
        await store.upsert(
            VectorCollection.IMAGE,
            [
                VectorRecord(
                    product_id=shoe_id, vector=[1.0, 0.0, 0.0, 0.0], metadata={"category": "shoes"}
                ),
                VectorRecord(
                    product_id=shirt_id,
                    vector=[1.0, 0.0, 0.0, 0.0],
                    metadata={"category": "shirts"},
                ),
            ],
        )

        results = await store.search(
            VectorCollection.IMAGE,
            [1.0, 0.0, 0.0, 0.0],
            top_k=10,
            filters=ProductFilters(category="shirts"),
        )

        assert [result.product_id for result in results] == [shirt_id]

    async def test_brand_filter_restricts_results_to_matching_metadata(self) -> None:
        store = _store()
        nike_id = uuid4()
        adidas_id = uuid4()
        await store.upsert(
            VectorCollection.IMAGE,
            [
                VectorRecord(
                    product_id=nike_id, vector=[1.0, 0.0, 0.0, 0.0], metadata={"brand": "Nike"}
                ),
                VectorRecord(
                    product_id=adidas_id, vector=[1.0, 0.0, 0.0, 0.0], metadata={"brand": "Adidas"}
                ),
            ],
        )

        results = await store.search(
            VectorCollection.IMAGE,
            [1.0, 0.0, 0.0, 0.0],
            top_k=10,
            filters=ProductFilters(brand="Nike"),
        )

        assert [result.product_id for result in results] == [nike_id]

    async def test_price_range_filter_restricts_results(self) -> None:
        store = _store()
        cheap_id = uuid4()
        mid_id = uuid4()
        expensive_id = uuid4()
        await store.upsert(
            VectorCollection.IMAGE,
            [
                VectorRecord(
                    product_id=cheap_id, vector=[1.0, 0.0, 0.0, 0.0], metadata={"price": 5.0}
                ),
                VectorRecord(
                    product_id=mid_id, vector=[1.0, 0.0, 0.0, 0.0], metadata={"price": 50.0}
                ),
                VectorRecord(
                    product_id=expensive_id, vector=[1.0, 0.0, 0.0, 0.0], metadata={"price": 500.0}
                ),
            ],
        )

        results = await store.search(
            VectorCollection.IMAGE,
            [1.0, 0.0, 0.0, 0.0],
            top_k=10,
            filters=ProductFilters(min_price=10.0, max_price=100.0),
        )

        assert [result.product_id for result in results] == [mid_id]

    async def test_combined_filters_are_all_required_to_match(self) -> None:
        store = _store()
        match_id = uuid4()
        wrong_brand_id = uuid4()
        await store.upsert(
            VectorCollection.IMAGE,
            [
                VectorRecord(
                    product_id=match_id,
                    vector=[1.0, 0.0, 0.0, 0.0],
                    metadata={"brand": "Nike", "category": "shoes"},
                ),
                VectorRecord(
                    product_id=wrong_brand_id,
                    vector=[1.0, 0.0, 0.0, 0.0],
                    metadata={"brand": "Adidas", "category": "shoes"},
                ),
            ],
        )

        results = await store.search(
            VectorCollection.IMAGE,
            [1.0, 0.0, 0.0, 0.0],
            top_k=10,
            filters=ProductFilters(brand="Nike", category="shoes"),
        )

        assert [result.product_id for result in results] == [match_id]

    async def test_an_all_none_filters_object_matches_everything(self) -> None:
        store = _store()
        product_id = uuid4()
        await store.upsert(
            VectorCollection.IMAGE,
            [VectorRecord(product_id=product_id, vector=[1.0, 0.0, 0.0, 0.0])],
        )

        results = await store.search(
            VectorCollection.IMAGE, [1.0, 0.0, 0.0, 0.0], top_k=10, filters=ProductFilters()
        )

        assert [result.product_id for result in results] == [product_id]


class TestDelete:
    async def test_delete_removes_the_record(self) -> None:
        store = _store()
        product_id = uuid4()
        await store.upsert(
            VectorCollection.IMAGE,
            [VectorRecord(product_id=product_id, vector=[1.0, 0.0, 0.0, 0.0])],
        )

        await store.delete(VectorCollection.IMAGE, [product_id])

        assert await store.exists(VectorCollection.IMAGE, product_id) is False

    async def test_delete_of_an_empty_list_is_a_no_op(self) -> None:
        store = _store()

        await store.delete(VectorCollection.IMAGE, [])  # must not raise


class TestHealth:
    async def test_returns_true_when_reachable(self) -> None:
        store = _store()

        assert await store.health() is True

    async def test_returns_false_when_unreachable(self) -> None:
        # health() never calls `_ensure_collection` — an unreachable
        # client exercises its own try/except directly, not that one.
        client = QdrantClient(url="http://localhost:1", timeout=1)
        store = _store(client=client)

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
        store = _store(client=client)

        with pytest.raises(VectorStoreException):
            await store.search(VectorCollection.IMAGE, [1.0, 0.0, 0.0, 0.0], top_k=5)

    async def test_upsert_wraps_a_client_failure(self) -> None:
        broken = _BrokenClient(QdrantClient(location=":memory:"), fail_method="upsert")
        store = _store(client=cast(QdrantClient, broken))

        with pytest.raises(VectorStoreException):
            await store.upsert(
                VectorCollection.IMAGE,
                [VectorRecord(product_id=uuid4(), vector=[1.0, 0.0, 0.0, 0.0])],
            )

    async def test_search_wraps_a_client_failure_distinct_from_ensure_collection(
        self,
    ) -> None:
        # Unlike the unreachable-client test above, this collection
        # genuinely exists (a real in-memory client) — only the search
        # call itself fails, exercising `search`'s own try/except rather
        # than `_ensure_collection`'s.
        broken = _BrokenClient(QdrantClient(location=":memory:"), fail_method="query_points")
        store = _store(client=cast(QdrantClient, broken))
        await store.upsert(
            VectorCollection.IMAGE, [VectorRecord(product_id=uuid4(), vector=[1.0, 0.0, 0.0, 0.0])]
        )

        with pytest.raises(VectorStoreException):
            await store.search(VectorCollection.IMAGE, [1.0, 0.0, 0.0, 0.0], top_k=5)

    async def test_delete_wraps_a_client_failure(self) -> None:
        broken = _BrokenClient(QdrantClient(location=":memory:"), fail_method="delete")
        store = _store(client=cast(QdrantClient, broken))

        with pytest.raises(VectorStoreException):
            await store.delete(VectorCollection.IMAGE, [uuid4()])

    async def test_exists_wraps_a_client_failure(self) -> None:
        broken = _BrokenClient(QdrantClient(location=":memory:"), fail_method="retrieve")
        store = _store(client=cast(QdrantClient, broken))

        with pytest.raises(VectorStoreException):
            await store.exists(VectorCollection.IMAGE, uuid4())

    async def test_retrieve_wraps_a_client_failure(self) -> None:
        broken = _BrokenClient(QdrantClient(location=":memory:"), fail_method="retrieve")
        store = _store(client=cast(QdrantClient, broken))

        with pytest.raises(VectorStoreException):
            await store.retrieve(VectorCollection.IMAGE, uuid4())


class TestThreadSafety:
    async def test_concurrent_first_use_creates_the_collection_only_once(self) -> None:
        real_client = QdrantClient(location=":memory:")
        slow_client = _SlowCollectionExistsClient(real_client, delay_seconds=0.05)
        store = _store(client=cast(QdrantClient, slow_client))

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: store._ensure_collection(VectorCollection.IMAGE), range(8)))

        assert slow_client.create_collection_calls == 1

    async def test_the_two_collections_lock_independently(self) -> None:
        """Loading the image collection must not block a concurrent text-collection load.

        Asserted by rendezvous, not by elapsed time. Both callers must meet at
        a two-party barrier: with independent locks they do, with one shared
        lock the second never arrives and the barrier breaks. The previous
        wall-clock form (`elapsed < 0.09` against a 0.05s sleep) tested the
        same property but failed intermittently on a loaded machine, because
        thread scheduling — not the lock design — decided the outcome.
        """
        real_client = QdrantClient(location=":memory:")
        client = _RendezvousClient(real_client)
        store = _store(client=cast(QdrantClient, client))

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(
                pool.map(
                    lambda collection: store._ensure_collection(collection),
                    [VectorCollection.IMAGE, VectorCollection.TEXT],
                )
            )

        assert (
            not client.rendezvous_failed
        ), "the two collections did not load concurrently, so they share a lock"
        assert client.create_collection_calls == 2
