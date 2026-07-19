"""Centralized filesystem paths for the backend.

Every module that needs a path on disk should import it from here instead
of building its own relative path with `Path(__file__)` — this is the one
place that knows where the project root actually is, so that knowledge
doesn't get re-derived (and potentially re-derived incorrectly) all over
the codebase.
"""

from pathlib import Path

# backend/app/core/paths.py -> parents[0]=core, [1]=app, [2]=backend
BACKEND_DIR: Path = Path(__file__).resolve().parents[2]
APP_DIR: Path = BACKEND_DIR / "app"
ENV_FILE: Path = BACKEND_DIR / ".env"

STORAGE_DIR: Path = BACKEND_DIR / "storage"
UPLOAD_DIR: Path = STORAGE_DIR / "uploads"
LOG_DIR: Path = BACKEND_DIR / "logs"

DEFAULT_SQLITE_PATH: Path = STORAGE_DIR / "app.db"


def ensure_runtime_directories() -> None:
    """Create directories the app writes to at runtime, if they don't exist.

    Deliberately NOT called on import: directory creation is a side effect
    that belongs to explicit application startup (Milestone 4), not to
    importing this module — keeping imports side-effect-free is what lets
    the config system be unit-tested without touching the real filesystem.
    """
    for directory in (STORAGE_DIR, UPLOAD_DIR, LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)
