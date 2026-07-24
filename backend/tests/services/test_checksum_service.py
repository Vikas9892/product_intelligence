"""Unit tests for `ChecksumService`."""

import hashlib
from pathlib import Path

import pytest

from app.exceptions.errors import ChecksumException
from app.services.checksum_service import ChecksumService


class TestComputeSha256:
    async def test_matches_hashlib_for_small_content(self, tmp_path: Path) -> None:
        content = b"hello world"
        file_path = tmp_path / "small.txt"
        file_path.write_bytes(content)

        digest = await ChecksumService().compute_sha256(file_path)

        assert digest == hashlib.sha256(content).hexdigest()

    async def test_matches_hashlib_across_multiple_chunk_reads(self, tmp_path: Path) -> None:
        # Larger than the service's 1 MiB chunk size, so the read loop
        # actually iterates more than once.
        content = b"0123456789abcdef" * 100_000  # 1.6 MB
        file_path = tmp_path / "large.bin"
        file_path.write_bytes(content)

        digest = await ChecksumService().compute_sha256(file_path)

        assert digest == hashlib.sha256(content).hexdigest()

    async def test_is_deterministic_for_identical_content(self, tmp_path: Path) -> None:
        content = b"same bytes"
        first_path = tmp_path / "a.txt"
        second_path = tmp_path / "b.txt"
        first_path.write_bytes(content)
        second_path.write_bytes(content)

        service = ChecksumService()
        assert await service.compute_sha256(first_path) == await service.compute_sha256(second_path)

    async def test_differs_for_different_content(self, tmp_path: Path) -> None:
        path_a = tmp_path / "a.txt"
        path_b = tmp_path / "b.txt"
        path_a.write_bytes(b"content A")
        path_b.write_bytes(b"content B")

        service = ChecksumService()
        assert await service.compute_sha256(path_a) != await service.compute_sha256(path_b)

    async def test_raises_checksum_exception_for_a_missing_file(self, tmp_path: Path) -> None:
        missing_path = tmp_path / "does-not-exist.bin"

        with pytest.raises(ChecksumException):
            await ChecksumService().compute_sha256(missing_path)
