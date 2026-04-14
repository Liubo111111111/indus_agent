"""Tests for backend/scripts/archive_legacy_data.py."""
from __future__ import annotations

from pathlib import Path

import pytest

# The script lives outside the package, so import via runpy-style or add to path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from archive_legacy_data import archive


class TestArchive:
    """Unit tests for the archive() function."""

    def test_moves_existing_files(self, tmp_path: Path) -> None:
        """All three target files are moved to _legacy/."""
        for name in ("formal_output.jsonl", "fallback_output.jsonl", "pipeline_results.sqlite3"):
            (tmp_path / name).write_text("data")

        archive(tmp_path)

        for name in ("formal_output.jsonl", "fallback_output.jsonl", "pipeline_results.sqlite3"):
            assert not (tmp_path / name).exists()
            assert (tmp_path / "_legacy" / name).exists()

    def test_skips_missing_files(self, tmp_path: Path) -> None:
        """Missing source files are silently skipped."""
        (tmp_path / "formal_output.jsonl").write_text("data")
        # fallback_output.jsonl and pipeline_results.sqlite3 do not exist

        archive(tmp_path)

        assert (tmp_path / "_legacy" / "formal_output.jsonl").exists()
        assert not (tmp_path / "_legacy" / "fallback_output.jsonl").exists()
        assert not (tmp_path / "_legacy" / "pipeline_results.sqlite3").exists()

    def test_creates_legacy_dir(self, tmp_path: Path) -> None:
        """_legacy directory is created if it doesn't exist."""
        (tmp_path / "formal_output.jsonl").write_text("data")

        archive(tmp_path)

        assert (tmp_path / "_legacy").is_dir()

    def test_no_files_no_error(self, tmp_path: Path) -> None:
        """Running with no source files produces no error."""
        archive(tmp_path)
        assert (tmp_path / "_legacy").is_dir()
