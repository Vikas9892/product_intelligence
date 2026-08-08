"""Integration tests for `GET /products/{id}` and `POST /products/batch`.

Regression tests for a client that could not turn a product ID back into a
product. Recommendations, duplicate decisions and explanations all return bare
IDs, and no route resolved them -- so every recommendation card rendered as
"Unresolved product".

Builds the real application and overrides only the lookup dependency, the same
seam `app/dependencies/` exists for.
"""

from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.application import create_app
from app.dependencies.product import get_product_lookup_service
from app.schemas.product_summary import MAX_BATCH_SIZE, ProductSummary
from app.services.product_lookup_service import ProductLookupService

_KNOWN = UUID("11111111-1111-1111-1111-111111111111")
_ALSO_KNOWN = UUID("22222222-2222-2222-2222-222222222222")

_STORED: dict[UUID, dict[str, Any]] = {
    _KNOWN: {
        "name": "Aurora Runner Blue",
        "brand": "Northwind",
        "category": "footwear",
        "price": 129.99,
        "color": "Blue",
        "tags": ["running", "blue"],
        "quality_score": 0.61,
    },
    _ALSO_KNOWN: {"name": "Trailblazer Black", "brand": "Summit", "category": "footwear"},
}


class _FakeLookupService(ProductLookupService):
    """Resolves from a fixed table instead of a vector store."""

    def __init__(self) -> None:
        pass

    async def get(self, product_id: UUID) -> ProductSummary | None:
        metadata = _STORED.get(product_id)
        return ProductSummary.from_metadata(product_id, metadata) if metadata else None


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_product_lookup_service] = _FakeLookupService
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestGetProduct:
    def test_resolves_a_known_id_to_its_metadata(self, client: TestClient) -> None:
        response = client.get(f"/api/v1/products/{_KNOWN}")

        assert response.status_code == 200
        body = response.json()
        assert body["product_id"] == str(_KNOWN)
        assert body["name"] == "Aurora Runner Blue"
        assert body["brand"] == "Northwind"
        assert body["category"] == "footwear"
        assert body["price"] == 129.99
        assert body["color"] == "Blue"
        assert body["tags"] == ["running", "blue"]

    def test_an_unknown_id_is_a_typed_404(self, client: TestClient) -> None:
        """A real, distinguishable state -- not an ambiguous placeholder."""
        response = client.get(f"/api/v1/products/{uuid4()}")

        assert response.status_code == 404
        error = response.json()["error"]
        assert error["code"] == "resource_not_found"
        assert "not indexed" in error["message"]

    def test_a_malformed_id_is_a_validation_error(self, client: TestClient) -> None:
        response = client.get("/api/v1/products/not-a-uuid")

        assert response.status_code == 422

    def test_is_registered_alongside_the_more_specific_routes(self, client: TestClient) -> None:
        """`/{id}` must not replace or shadow `/{id}/status` and friends.

        Checked against the served OpenAPI document rather than by calling the
        status route, which would need a live queue.
        """
        paths = client.get("/openapi.json").json()["paths"]

        assert "get" in paths["/api/v1/products/{product_id}"]
        assert "get" in paths["/api/v1/products/{product_id}/status"]
        assert "get" in paths["/api/v1/products/{product_id}/recommendations"]
        assert "post" in paths["/api/v1/products/batch"]


class TestBatchResolution:
    def test_resolves_many_ids_in_one_request(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/products/batch",
            json={"product_ids": [str(_KNOWN), str(_ALSO_KNOWN)]},
        )

        assert response.status_code == 200
        body = response.json()
        assert [p["name"] for p in body["products"]] == [
            "Aurora Runner Blue",
            "Trailblazer Black",
        ]
        assert body["missing"] == []

    def test_reports_unknown_ids_without_failing_the_request(self, client: TestClient) -> None:
        """A partially-stale list must still render what exists."""
        unknown = uuid4()
        response = client.post(
            "/api/v1/products/batch",
            json={"product_ids": [str(_KNOWN), str(unknown)]},
        )

        assert response.status_code == 200
        body = response.json()
        assert [p["product_id"] for p in body["products"]] == [str(_KNOWN)]
        assert body["missing"] == [str(unknown)]

    def test_collapses_duplicate_ids(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/products/batch",
            json={"product_ids": [str(_KNOWN), str(_KNOWN), str(_KNOWN)]},
        )

        assert len(response.json()["products"]) == 1

    def test_rejects_an_oversized_batch(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/products/batch",
            json={"product_ids": [str(uuid4()) for _ in range(MAX_BATCH_SIZE + 1)]},
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_accepts_a_batch_exactly_at_the_cap(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/products/batch",
            json={"product_ids": [str(uuid4()) for _ in range(MAX_BATCH_SIZE)]},
        )

        assert response.status_code == 200

    def test_rejects_an_empty_batch(self, client: TestClient) -> None:
        response = client.post("/api/v1/products/batch", json={"product_ids": []})

        assert response.status_code == 422
