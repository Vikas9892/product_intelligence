"""Unit tests for `UploadService`.

Every test constructs `UploadService` with an explicit `upload_dir`
(`tmp_path`) so nothing here ever touches the real `backend/storage/`
directory.
"""

from pathlib import Path

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.exceptions.errors import (
    FileTooLargeException,
    UnsupportedMediaTypeException,
    ValidationException,
)
from app.services.upload_service import UploadService


def _upload_file(
    *,
    filename: str | None = "photo.jpg",
    content_type: str | None = "image/jpeg",
    content: bytes = b"fake-image-bytes",
) -> UploadFile:
    import io

    headers = Headers({"content-type": content_type}) if content_type is not None else Headers({})
    return UploadFile(file=io.BytesIO(content), filename=filename, headers=headers)


class TestUploadServiceInit:
    def test_creates_the_upload_directory_if_missing(self, tmp_path: Path) -> None:
        nested_dir = tmp_path / "does" / "not" / "exist" / "yet"

        UploadService(upload_dir=nested_dir)

        assert nested_dir.is_dir()


class TestSaveUploadSuccess:
    async def test_stores_the_file_and_returns_its_metadata(self, tmp_path: Path) -> None:
        service = UploadService(upload_dir=tmp_path)
        content = b"\xff\xd8\xff" + b"0" * 100  # arbitrary bytes, not a real JPEG

        image = await service.save_upload(_upload_file(content=content))

        assert image.original_filename == "photo.jpg"
        assert image.content_type == "image/jpeg"
        assert image.size_bytes == len(content)
        assert image.stored_filename != image.original_filename  # generated, not client-supplied

        stored_path = tmp_path / image.stored_filename
        assert stored_path.is_file()
        assert stored_path.read_bytes() == content

    async def test_stored_filename_preserves_the_original_extension(self, tmp_path: Path) -> None:
        service = UploadService(upload_dir=tmp_path)

        image = await service.save_upload(
            _upload_file(filename="photo.PNG", content_type="image/png")
        )

        assert image.stored_filename.endswith(".png")  # normalized to lowercase


class TestSaveUploadValidation:
    async def test_rejects_a_missing_filename(self, tmp_path: Path) -> None:
        service = UploadService(upload_dir=tmp_path)

        with pytest.raises(ValidationException):
            await service.save_upload(_upload_file(filename=None))

    async def test_rejects_an_empty_filename(self, tmp_path: Path) -> None:
        service = UploadService(upload_dir=tmp_path)

        with pytest.raises(ValidationException):
            await service.save_upload(_upload_file(filename=""))

    async def test_rejects_a_disallowed_extension(self, tmp_path: Path) -> None:
        service = UploadService(upload_dir=tmp_path)

        with pytest.raises(UnsupportedMediaTypeException):
            await service.save_upload(
                _upload_file(filename="document.txt", content_type="text/plain")
            )

    async def test_rejects_a_disallowed_mime_type(self, tmp_path: Path) -> None:
        service = UploadService(upload_dir=tmp_path)

        with pytest.raises(UnsupportedMediaTypeException):
            await service.save_upload(
                _upload_file(filename="photo.jpg", content_type="application/pdf")
            )

    async def test_rejects_a_missing_content_type(self, tmp_path: Path) -> None:
        service = UploadService(upload_dir=tmp_path)

        with pytest.raises(UnsupportedMediaTypeException):
            await service.save_upload(_upload_file(content_type=None))

    async def test_disallowed_file_is_never_written_to_disk(self, tmp_path: Path) -> None:
        service = UploadService(upload_dir=tmp_path)

        with pytest.raises(UnsupportedMediaTypeException):
            await service.save_upload(
                _upload_file(filename="document.txt", content_type="text/plain")
            )

        assert list(tmp_path.iterdir()) == []


class TestSaveUploadSizeLimit:
    async def test_rejects_a_file_over_the_configured_limit(self, tmp_path: Path) -> None:
        # max_upload_size_mb accepts fractional-MB precision via bytes math
        # in the service, but here we just need "smaller than the payload".
        service = UploadService(upload_dir=tmp_path, max_upload_size_mb=1)
        oversized_content = b"0" * (2 * 1024 * 1024)  # 2 MiB > 1 MiB limit

        with pytest.raises(FileTooLargeException):
            await service.save_upload(_upload_file(content=oversized_content))

    async def test_partial_file_is_cleaned_up_after_a_size_rejection(self, tmp_path: Path) -> None:
        service = UploadService(upload_dir=tmp_path, max_upload_size_mb=1)
        oversized_content = b"0" * (2 * 1024 * 1024)

        with pytest.raises(FileTooLargeException):
            await service.save_upload(_upload_file(content=oversized_content))

        assert list(tmp_path.iterdir()) == []

    async def test_accepts_a_file_at_exactly_the_limit(self, tmp_path: Path) -> None:
        service = UploadService(upload_dir=tmp_path, max_upload_size_mb=1)
        exact_content = b"0" * (1024 * 1024)  # exactly 1 MiB

        image = await service.save_upload(_upload_file(content=exact_content))

        assert image.size_bytes == 1024 * 1024
