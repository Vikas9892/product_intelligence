"""Reusable validators for uploaded files.

Extracted out of `UploadService` (Phase 2A) so validation rules live in
one place, independent of *how or where* an accepted file gets stored —
`UploadService` calls these before writing to disk, and any future upload
path (a bulk-import script, a different endpoint) can reuse them without
depending on `UploadService` at all. Pure functions: given the same
inputs, always the same result, no I/O, trivially unit-testable.

File *size* validation deliberately isn't here — see `UploadService`'s
`_stream_to_disk` docstring for why: it's inherently a streaming,
as-you-go check (the size isn't fully known until the file has been
entirely read), not a pure function over an already-known value like
extension or MIME type are.
"""

from pathlib import Path

from app.exceptions.errors import UnsupportedMediaTypeException, ValidationException


def validate_filename_and_extension(
    filename: str | None, *, allowed_extensions: tuple[str, ...]
) -> tuple[str, str]:
    """Validate `filename` is present and has an allowed extension.

    Returns `(filename, extension)` with the extension lowercased.
    Raises `ValidationException` if `filename` is missing/empty, or
    `UnsupportedMediaTypeException` if its extension isn't allowed.
    """
    if not filename:
        raise ValidationException("Uploaded file is missing a filename.")

    extension = Path(filename).suffix.lower()
    if extension not in allowed_extensions:
        raise UnsupportedMediaTypeException(
            f"Unsupported file extension '{extension or '(none)'}'. "
            f"Allowed extensions: {', '.join(allowed_extensions)}."
        )
    return filename, extension


def validate_mime_type(content_type: str | None, *, allowed_mime_types: frozenset[str]) -> str:
    """Validate `content_type` is present and allowed; returns it narrowed to `str`.

    The declared type from a multipart part's `Content-Type` header is
    client-controlled — this is a first line of defense, not an
    authoritative check. Verifying the file's *actual* bytes match (e.g.
    via Pillow) belongs to a later image-processing phase, not here.
    """
    if content_type is None or content_type not in allowed_mime_types:
        raise UnsupportedMediaTypeException(
            f"Unsupported content type '{content_type}'. "
            f"Allowed types: {', '.join(sorted(allowed_mime_types))}."
        )
    return content_type
