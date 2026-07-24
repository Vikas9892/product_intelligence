"""SHA-256 checksum computation for stored files.

A standalone, reusable service — computed once here so every later phase
that needs a file's checksum (duplicate detection, caching, integrity
verification — all explicitly out of scope for *this* phase, see
`backend/README.md`) reuses it instead of reimplementing file hashing.

Deliberately operates on a file already saved to disk (a `Path`), not on
the in-flight `UploadFile` stream `UploadService` writes from. This costs
a second read of the file after `UploadService` has already written it
once — negligible given the small upload-size cap this project defaults
to — in exchange for `ChecksumService` staying a genuinely standalone
utility that can hash *any* file on disk, not something wired into the
upload stream's write loop. See the Phase 2B section of
`backend/README.md` for the full tradeoff.
"""

import hashlib
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from app.exceptions.errors import ChecksumException

# 1 MiB per read chunk — mirrors `UploadService`'s streaming chunk size,
# bounding memory use regardless of file size.
_CHUNK_SIZE_BYTES = 1024 * 1024


class ChecksumService:
    """Computes a SHA-256 checksum for a file already on disk."""

    async def compute_sha256(self, path: Path) -> str:
        """Return the SHA-256 hex digest of the file at `path`.

        Reads in bounded chunks (never the whole file into memory at
        once) via a thread pool, since file I/O is blocking. Raises
        `ChecksumException` if the file can't be read — an
        infrastructure failure, not a client input problem.
        """
        hasher = hashlib.sha256()
        try:
            with path.open("rb") as file:
                while chunk := await run_in_threadpool(file.read, _CHUNK_SIZE_BYTES):
                    hasher.update(chunk)
        except OSError as exc:
            raise ChecksumException(f"Failed to compute checksum for '{path.name}'.") from exc
        return hasher.hexdigest()
