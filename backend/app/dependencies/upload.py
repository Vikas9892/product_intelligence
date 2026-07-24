"""FastAPI dependency provider for `UploadService`.

Mirrors `app.core.config.get_settings`'s cached-singleton pattern: one
`UploadService` instance per process, built lazily on first use, so
`Depends(get_upload_service)` doesn't reconstruct it (and re-run its
`mkdir`) on every request. This is also the seam tests use to redirect
uploads to a temporary directory —
`app.dependency_overrides[get_upload_service] = lambda: UploadService(upload_dir=tmp_path)`
— instead of monkeypatching global settings, which is the whole reason
`app/dependencies/` (reserved, empty, since Phase 1's Milestone 1) exists.
"""

from functools import lru_cache

from app.services.upload_service import UploadService


@lru_cache(maxsize=1)
def get_upload_service() -> UploadService:
    """Return the process-wide UploadService singleton, building it on first call."""
    return UploadService()
