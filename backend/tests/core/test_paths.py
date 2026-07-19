"""Unit tests for centralized filesystem paths."""

from pathlib import Path

import pytest

from app.core import paths


def test_backend_dir_points_at_the_actual_backend_root() -> None:
    assert paths.APP_DIR == paths.BACKEND_DIR / "app"
    assert (paths.BACKEND_DIR / "pyproject.toml").exists()


def test_derived_paths_are_nested_correctly() -> None:
    assert paths.UPLOAD_DIR == paths.STORAGE_DIR / "uploads"
    assert paths.DEFAULT_SQLITE_PATH == paths.STORAGE_DIR / "app.db"
    assert paths.ENV_FILE == paths.BACKEND_DIR / ".env"


def test_ensure_runtime_directories_creates_missing_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage_dir = tmp_path / "storage"
    upload_dir = storage_dir / "uploads"
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(paths, "STORAGE_DIR", storage_dir)
    monkeypatch.setattr(paths, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(paths, "LOG_DIR", log_dir)

    assert not storage_dir.exists()

    paths.ensure_runtime_directories()

    assert storage_dir.is_dir()
    assert upload_dir.is_dir()
    assert log_dir.is_dir()


def test_ensure_runtime_directories_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage_dir = tmp_path / "storage"
    monkeypatch.setattr(paths, "STORAGE_DIR", storage_dir)
    monkeypatch.setattr(paths, "UPLOAD_DIR", storage_dir / "uploads")
    monkeypatch.setattr(paths, "LOG_DIR", tmp_path / "logs")

    paths.ensure_runtime_directories()
    paths.ensure_runtime_directories()  # must not raise on the second call

    assert storage_dir.is_dir()
