"""Integration tests for the async upload pipeline (Phase 12): `POST /products/upload`
(queued mode), `GET /products/{id}/status`, and `GET /jobs/{job_id}`.

Builds the *real* `create_app()` application, overriding `get_upload_service`
(so the file actually gets validated/stored under `tmp_path`, exactly as
in synchronous mode) and `get_queue_manager` with a fake in-memory
`BaseQueue` — no real Redis, embedding model, or vector store is needed,
since queuing happens *before* any of that runs. The full synchronous
pipeline (image processing, embeddings, vector indexing, ...) stays
covered by `tests/api/test_products.py`/`test_recommendations.py`/etc.
(each forces `ASYNC_PIPELINE__ENABLED=false` for exactly this reason);
`ProductWorker` actually running this job is `tests/workers/
test_product_worker.py`'s job.
"""

import io
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.application import create_app
from app.core.config import settings
from app.dependencies.queue import get_queue_manager
from app.dependencies.upload import get_upload_service
from app.jobs.base_job import Job
from app.jobs.job_types import JobType
from app.queue.base_queue import BaseQueue
from app.queue.queue_manager import QueueManager
from app.services.upload_service import UploadService

_UPLOAD_URL = f"{settings.application.api_prefix}/products/upload"


class _FakeQueue(BaseQueue):
    """Records every enqueued job in memory — no real Redis needed."""

    def __init__(self) -> None:
        self.enqueued: list[Job] = []

    async def enqueue(self, job: Job) -> None:
        self.enqueued.append(job)

    async def dequeue(self) -> Job | None:
        return None

    async def ack(self, job: Job) -> None:
        pass

    async def retry(self, job: Job, *, error: str) -> None:
        pass

    async def get(self, job_id: UUID) -> Job | None:
        return next((job for job in self.enqueued if job.job_id == job_id), None)

    async def get_by_product_id(self, product_id: UUID) -> Job | None:
        return next((job for job in self.enqueued if job.product_id == product_id), None)

    async def update(self, job: Job) -> None:
        for index, existing in enumerate(self.enqueued):
            if existing.job_id == job.job_id:
                self.enqueued[index] = job


def _image_file() -> dict[str, tuple[str, io.BytesIO, str]]:
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), (10, 20, 30)).save(buffer, format="JPEG")
    buffer.seek(0)
    return {"file": ("photo.jpg", buffer, "image/jpeg")}


@pytest.fixture
def async_upload_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, _FakeQueue]]:
    monkeypatch.setattr(settings.async_pipeline, "enabled", True)
    app = create_app()
    fake_queue = _FakeQueue()
    _override(app, tmp_path, fake_queue)

    with TestClient(app) as client:
        yield client, fake_queue


def _override(app: FastAPI, upload_dir: Path, fake_queue: _FakeQueue) -> None:
    app.dependency_overrides[get_upload_service] = lambda: UploadService(upload_dir=upload_dir)
    app.dependency_overrides[get_queue_manager] = lambda: QueueManager(queue=fake_queue)


class TestAsyncUploadAccepted:
    def test_returns_202(self, async_upload_client: tuple[TestClient, _FakeQueue]) -> None:
        client, _fake_queue = async_upload_client

        response = client.post(_UPLOAD_URL, data={"name": "Widget"}, files=_image_file())

        assert response.status_code == 202

    def test_response_includes_product_id_job_id_and_status_url(
        self, async_upload_client: tuple[TestClient, _FakeQueue]
    ) -> None:
        client, _fake_queue = async_upload_client

        response = client.post(_UPLOAD_URL, data={"name": "Widget"}, files=_image_file())

        body = response.json()
        product_id = UUID(body["product_id"])  # a real UUID string
        job_id = UUID(body["job_id"])
        assert body["status"] == "pending"
        assert (
            body["status_url"] == f"{settings.application.api_prefix}/products/{product_id}/status"
        )
        assert job_id != product_id

    def test_enqueues_exactly_one_job(
        self, async_upload_client: tuple[TestClient, _FakeQueue]
    ) -> None:
        client, fake_queue = async_upload_client

        response = client.post(_UPLOAD_URL, data={"name": "Widget"}, files=_image_file())

        assert len(fake_queue.enqueued) == 1
        job = fake_queue.enqueued[0]
        assert str(job.job_id) == response.json()["job_id"]
        assert str(job.product_id) == response.json()["product_id"]
        assert job.job_type is JobType.PRODUCT_PROCESSING

    def test_the_job_payload_carries_the_submitted_product_fields(
        self, async_upload_client: tuple[TestClient, _FakeQueue]
    ) -> None:
        client, fake_queue = async_upload_client

        client.post(
            _UPLOAD_URL,
            data={"name": "Nike Widget", "brand": "Nike", "category": "Shoes"},
            files=_image_file(),
        )

        job = fake_queue.enqueued[0]
        assert job.payload["product"]["name"] == "Nike Widget"
        assert job.payload["product"]["brand"] == "Nike"
        assert "image" in job.payload

    def test_the_uploaded_file_is_still_written_to_disk(
        self, async_upload_client: tuple[TestClient, _FakeQueue], tmp_path: Path
    ) -> None:
        client, fake_queue = async_upload_client

        client.post(_UPLOAD_URL, data={"name": "Widget"}, files=_image_file())

        stored_filename = fake_queue.enqueued[0].payload["image"]["stored_filename"]
        assert (tmp_path / stored_filename).is_file()


class TestProductStatus:
    def test_returns_the_queued_jobs_status(
        self, async_upload_client: tuple[TestClient, _FakeQueue]
    ) -> None:
        client, _fake_queue = async_upload_client
        upload_response = client.post(_UPLOAD_URL, data={"name": "Widget"}, files=_image_file())
        product_id = upload_response.json()["product_id"]

        response = client.get(f"{settings.application.api_prefix}/products/{product_id}/status")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "pending"
        assert body["progress"] == 0
        assert body["product_id"] == product_id
        assert body["job_id"] == upload_response.json()["job_id"]

    def test_an_unknown_product_id_returns_404(
        self, async_upload_client: tuple[TestClient, _FakeQueue]
    ) -> None:
        client, _fake_queue = async_upload_client

        response = client.get(f"{settings.application.api_prefix}/products/{uuid4()}/status")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "resource_not_found"


class TestJobStatus:
    def test_returns_the_same_shape_as_product_status(
        self, async_upload_client: tuple[TestClient, _FakeQueue]
    ) -> None:
        client, _fake_queue = async_upload_client
        upload_response = client.post(_UPLOAD_URL, data={"name": "Widget"}, files=_image_file())
        job_id = upload_response.json()["job_id"]

        response = client.get(f"{settings.application.api_prefix}/jobs/{job_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["job_id"] == job_id
        assert body["status"] == "pending"

    def test_an_unknown_job_id_returns_404(
        self, async_upload_client: tuple[TestClient, _FakeQueue]
    ) -> None:
        client, _fake_queue = async_upload_client

        response = client.get(f"{settings.application.api_prefix}/jobs/{uuid4()}")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "resource_not_found"
