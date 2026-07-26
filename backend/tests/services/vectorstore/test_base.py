"""Unit tests for the `BaseVectorStore` interface and `VectorRecord`."""

from typing import Any
from uuid import uuid4

import pytest

from app.models.search import NearestNeighbor
from app.services.vectorstore.base import BaseVectorStore, VectorRecord


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


class TestBaseVectorStore:
    def test_cannot_be_instantiated_directly(self) -> None:
        with pytest.raises(TypeError):
            BaseVectorStore()  # type: ignore[abstract]

    async def test_a_conforming_subclass_can_be_instantiated_and_used(self) -> None:
        class _FakeVectorStore(BaseVectorStore):
            def __init__(self) -> None:
                self._records: dict[str, VectorRecord] = {}

            async def upsert(self, records: list[VectorRecord]) -> None:
                for record in records:
                    self._records[str(record.product_id)] = record

            async def search(
                self,
                query_vector: list[float],
                *,
                top_k: int,
                filters: dict[str, Any] | None = None,
            ) -> list[NearestNeighbor]:
                return [
                    NearestNeighbor(
                        product_id=record.product_id, score=1.0, metadata=record.metadata
                    )
                    for record in list(self._records.values())[:top_k]
                ]

            async def delete(self, product_ids: list) -> None:  # type: ignore[type-arg]
                for product_id in product_ids:
                    self._records.pop(str(product_id), None)

            async def exists(self, product_id) -> bool:  # type: ignore[no-untyped-def]
                return str(product_id) in self._records

            async def health(self) -> bool:
                return True

        store = _FakeVectorStore()
        product_id = uuid4()

        await store.upsert([VectorRecord(product_id=product_id, vector=[1.0, 0.0])])

        assert await store.exists(product_id) is True
        assert await store.health() is True
        results = await store.search([1.0, 0.0], top_k=5)
        assert results[0].product_id == product_id

        await store.delete([product_id])
        assert await store.exists(product_id) is False

    def test_a_subclass_missing_a_method_cannot_be_instantiated(self) -> None:
        class _IncompleteVectorStore(BaseVectorStore):
            async def upsert(self, records: list[VectorRecord]) -> None:
                return None

        with pytest.raises(TypeError):
            _IncompleteVectorStore()  # type: ignore[abstract]
