"""Unit tests for the `BaseVectorStore` interface and `VectorRecord`."""

from uuid import UUID, uuid4

import pytest

from app.models.search import NearestNeighbor, ProductFilters, StoredPoint
from app.services.vectorstore.base import BaseVectorStore, VectorCollection, VectorRecord


class TestVectorRecord:
    def test_metadata_defaults_to_empty_dict(self) -> None:
        record = VectorRecord(product_id=uuid4(), vector=[0.1, 0.2])

        assert record.metadata == {}

    def test_constructs_with_metadata(self) -> None:
        product_id = uuid4()

        record = VectorRecord(
            product_id=product_id, vector=[0.1, 0.2], metadata={"category": "shoes"}
        )

        assert record.product_id == product_id
        assert record.vector == [0.1, 0.2]
        assert record.metadata == {"category": "shoes"}


class _FakeVectorStore(BaseVectorStore):
    """Records every call it receives, keyed by `VectorCollection`."""

    def __init__(self) -> None:
        self._records: dict[VectorCollection, dict[str, VectorRecord]] = {
            collection: {} for collection in VectorCollection
        }
        self.search_calls: list[VectorCollection] = []

    async def upsert(self, collection: VectorCollection, records: list[VectorRecord]) -> None:
        for record in records:
            self._records[collection][str(record.product_id)] = record

    async def search(
        self,
        collection: VectorCollection,
        query_vector: list[float],
        *,
        top_k: int,
        filters: ProductFilters | None = None,
    ) -> list[NearestNeighbor]:
        self.search_calls.append(collection)
        return [
            NearestNeighbor(product_id=record.product_id, score=1.0, metadata=record.metadata)
            for record in list(self._records[collection].values())[:top_k]
        ]

    async def delete(self, collection: VectorCollection, product_ids: list[UUID]) -> None:
        for product_id in product_ids:
            self._records[collection].pop(str(product_id), None)

    async def exists(self, collection: VectorCollection, product_id: UUID) -> bool:
        return str(product_id) in self._records[collection]

    async def retrieve(self, collection: VectorCollection, product_id: UUID) -> StoredPoint | None:
        record = self._records[collection].get(str(product_id))
        if record is None:
            return None
        return StoredPoint(
            product_id=record.product_id, vector=record.vector, metadata=record.metadata
        )

    async def health(self) -> bool:
        return True


class TestBaseVectorStore:
    def test_cannot_be_instantiated_directly(self) -> None:
        with pytest.raises(TypeError):
            BaseVectorStore()  # type: ignore[abstract]

    async def test_a_conforming_subclass_can_be_instantiated_and_used(self) -> None:
        store = _FakeVectorStore()
        product_id = uuid4()

        await store.upsert(
            VectorCollection.IMAGE, [VectorRecord(product_id=product_id, vector=[1.0, 0.0])]
        )

        assert await store.exists(VectorCollection.IMAGE, product_id) is True
        assert await store.health() is True
        results = await store.search(VectorCollection.IMAGE, [1.0, 0.0], top_k=5)
        assert results[0].product_id == product_id

        await store.delete(VectorCollection.IMAGE, [product_id])
        assert await store.exists(VectorCollection.IMAGE, product_id) is False

    async def test_retrieve_returns_the_stored_point(self) -> None:
        store = _FakeVectorStore()
        product_id = uuid4()
        await store.upsert(
            VectorCollection.IMAGE,
            [VectorRecord(product_id=product_id, vector=[1.0, 0.0], metadata={"brand": "Nike"})],
        )

        point = await store.retrieve(VectorCollection.IMAGE, product_id)

        assert point is not None
        assert point.product_id == product_id
        assert point.vector == [1.0, 0.0]
        assert point.metadata == {"brand": "Nike"}

    async def test_retrieve_returns_none_for_an_absent_product(self) -> None:
        store = _FakeVectorStore()

        point = await store.retrieve(VectorCollection.IMAGE, uuid4())

        assert point is None

    def test_a_subclass_missing_a_method_cannot_be_instantiated(self) -> None:
        class _IncompleteVectorStore(BaseVectorStore):
            async def upsert(
                self, collection: VectorCollection, records: list[VectorRecord]
            ) -> None:
                return None

        with pytest.raises(TypeError):
            _IncompleteVectorStore()  # type: ignore[abstract]


class TestPerModalityConvenienceMethods:
    """`upsert_image`/`upsert_text`/`search_image`/`search_text` are concrete on
    `BaseVectorStore` itself — every subclass gets them for free, implemented
    once in terms of the five abstract primitives.
    """

    async def test_upsert_image_targets_the_image_collection(self) -> None:
        store = _FakeVectorStore()
        product_id = uuid4()

        await store.upsert_image([VectorRecord(product_id=product_id, vector=[1.0, 0.0])])

        assert await store.exists(VectorCollection.IMAGE, product_id) is True
        assert await store.exists(VectorCollection.TEXT, product_id) is False

    async def test_upsert_text_targets_the_text_collection(self) -> None:
        store = _FakeVectorStore()
        product_id = uuid4()

        await store.upsert_text([VectorRecord(product_id=product_id, vector=[1.0, 0.0])])

        assert await store.exists(VectorCollection.TEXT, product_id) is True
        assert await store.exists(VectorCollection.IMAGE, product_id) is False

    async def test_search_image_targets_the_image_collection(self) -> None:
        store = _FakeVectorStore()

        await store.search_image([1.0, 0.0], top_k=5)

        assert store.search_calls == [VectorCollection.IMAGE]

    async def test_search_text_targets_the_text_collection(self) -> None:
        store = _FakeVectorStore()

        await store.search_text([1.0, 0.0], top_k=5)

        assert store.search_calls == [VectorCollection.TEXT]

    async def test_retrieve_image_targets_the_image_collection(self) -> None:
        store = _FakeVectorStore()
        product_id = uuid4()
        await store.upsert_image([VectorRecord(product_id=product_id, vector=[1.0, 0.0])])

        point = await store.retrieve_image(product_id)

        assert point is not None
        assert await store.retrieve_text(product_id) is None

    async def test_retrieve_text_targets_the_text_collection(self) -> None:
        store = _FakeVectorStore()
        product_id = uuid4()
        await store.upsert_text([VectorRecord(product_id=product_id, vector=[1.0, 0.0])])

        point = await store.retrieve_text(product_id)

        assert point is not None
        assert await store.retrieve_image(product_id) is None
