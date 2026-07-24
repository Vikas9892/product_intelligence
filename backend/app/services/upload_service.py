"""Upload service: validates and durably stores uploaded product image files.

The single place that decides whether an uploaded file is acceptable
(filename/extension, declared MIME type, size) and where an accepted file
actually lands on disk. Kept separate from `app/api/products.py` so the
route stays a thin HTTP adapter — parse the request, call the service,
shape the response — while this validation/storage logic stays unit
testable without spinning up the ASGI app.
"""

import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from app.core import constants
from app.core.config import settings
from app.core.logging import get_logger
from app.exceptions.errors import (
    FileTooLargeException,
    UnsupportedMediaTypeException,
    ValidationException,
)
from app.schemas.product import ProductImage

logger = get_logger(__name__)

# 1 MiB per read/write chunk while streaming an upload to disk — bounds
# memory use regardless of the configured maximum upload size.
_CHUNK_SIZE_BYTES = 1024 * 1024


class UploadService:
    """Validates and stores uploaded product image files.

    Every limit defaults to `settings.storage.*`/`constants.*` but can be
    overridden per instance — tests use this to redirect uploads to a
    `tmp_path` or shrink the size limit, without monkeypatching the global
    `settings` singleton (the same `is not None`, not truthiness, override
    idiom `app.core.logging.configure_logging` already uses, so a caller
    can pass `max_upload_size_mb=0` deliberately without it being treated
    as "not provided").
    """

    def __init__(
        self,
        *,
        upload_dir: Path | None = None,
        max_upload_size_mb: int | None = None,
        allowed_extensions: tuple[str, ...] | None = None,
        allowed_mime_types: frozenset[str] | None = None,
    ) -> None:
        self._upload_dir = upload_dir if upload_dir is not None else settings.storage.upload_dir

        resolved_max_mb = (
            max_upload_size_mb
            if max_upload_size_mb is not None
            else settings.storage.max_upload_size_mb
        )
        self._max_upload_size_bytes = resolved_max_mb * 1024 * 1024

        self._allowed_extensions = (
            allowed_extensions
            if allowed_extensions is not None
            else settings.storage.allowed_image_extensions
        )
        self._allowed_mime_types = (
            allowed_mime_types
            if allowed_mime_types is not None
            else constants.SUPPORTED_IMAGE_MIME_TYPES
        )

        # Belt-and-suspenders: `app/lifespan.py` already ensures this exists
        # at real application startup. Repeating it here means the service
        # is self-sufficient for direct/unit-test use too.
        self._upload_dir.mkdir(parents=True, exist_ok=True)

    async def save_upload(self, file: UploadFile) -> ProductImage:
        """Validate `file` and write it to the upload directory.

        Raises `ValidationException` (missing filename),
        `UnsupportedMediaTypeException` (disallowed extension or MIME
        type), or `FileTooLargeException` (exceeds the configured limit).
        Returns metadata describing where the accepted file was stored.
        """
        filename, extension = self._validate_filename_and_extension(file.filename)
        content_type = self._validate_mime_type(file.content_type)

        stored_filename = f"{uuid.uuid4().hex}{extension}"
        destination = self._upload_dir / stored_filename
        size_bytes = await self._stream_to_disk(file, destination)

        logger.info(
            "Stored upload '%s' as '%s' (%d bytes, %s)",
            filename,
            stored_filename,
            size_bytes,
            content_type,
        )

        return ProductImage(
            original_filename=filename,
            stored_filename=stored_filename,
            content_type=content_type,
            size_bytes=size_bytes,
            uploaded_at=datetime.now(UTC),
        )

    def _validate_filename_and_extension(self, filename: str | None) -> tuple[str, str]:
        if not filename:
            raise ValidationException("Uploaded file is missing a filename.")

        extension = Path(filename).suffix.lower()
        if extension not in self._allowed_extensions:
            raise UnsupportedMediaTypeException(
                f"Unsupported file extension '{extension or '(none)'}'. "
                f"Allowed extensions: {', '.join(self._allowed_extensions)}."
            )
        return filename, extension

    def _validate_mime_type(self, content_type: str | None) -> str:
        # Declared type from the multipart part's Content-Type header —
        # client-controlled, a first line of defense rather than an
        # authoritative check. Verifying the file's *actual* bytes match
        # (e.g. via Pillow) belongs to a later image-processing phase, not
        # upload validation.
        if content_type is None or content_type not in self._allowed_mime_types:
            raise UnsupportedMediaTypeException(
                f"Unsupported content type '{content_type}'. "
                f"Allowed types: {', '.join(sorted(self._allowed_mime_types))}."
            )
        return content_type

    async def _stream_to_disk(self, file: UploadFile, destination: Path) -> int:
        """Read `file` in bounded chunks, enforcing the size limit as it goes.

        Never buffers more than one chunk beyond the configured limit in
        memory or on disk — as soon as the cumulative size is exceeded,
        the partial file is deleted and `FileTooLargeException` raised,
        rather than trusting the client-supplied `Content-Length` header
        or fully buffering an oversized file first.
        """
        size = 0
        try:
            with destination.open("wb") as buffer:
                while chunk := await file.read(_CHUNK_SIZE_BYTES):
                    size += len(chunk)
                    if size > self._max_upload_size_bytes:
                        raise FileTooLargeException(
                            "Uploaded file exceeds the maximum allowed size of "
                            f"{self._max_upload_size_bytes // (1024 * 1024)}MB."
                        )
                    await run_in_threadpool(buffer.write, chunk)
        except FileTooLargeException:
            destination.unlink(missing_ok=True)
            raise
        return size
