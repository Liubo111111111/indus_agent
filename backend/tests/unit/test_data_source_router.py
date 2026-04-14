"""Unit tests for DataSourceRouter – validate_pt, resolve_dir, get_latest_pt."""

from __future__ import annotations

from pathlib import Path

import pytest

from industry_classification.api.data_source_router import DataSourceRouter


# ---------------------------------------------------------------------------
# validate_pt
# ---------------------------------------------------------------------------


class TestValidatePt:
    def setup_method(self) -> None:
        self.router = DataSourceRouter(base_output_dir=Path("/tmp/fake"))

    def test_legacy_is_valid(self) -> None:
        assert self.router.validate_pt("_legacy") is True

    def test_valid_date(self) -> None:
        assert self.router.validate_pt("20260412") is True

    def test_valid_leap_day(self) -> None:
        assert self.router.validate_pt("20240229") is True

    def test_invalid_leap_day(self) -> None:
        # 2023 is not a leap year
        assert self.router.validate_pt("20230229") is False

    def test_invalid_month(self) -> None:
        assert self.router.validate_pt("20261301") is False

    def test_invalid_day(self) -> None:
        assert self.router.validate_pt("20260432") is False

    def test_too_short(self) -> None:
        assert self.router.validate_pt("2026041") is False

    def test_too_long(self) -> None:
        assert self.router.validate_pt("202604120") is False

    def test_non_numeric(self) -> None:
        assert self.router.validate_pt("abcdefgh") is False

    def test_empty_string(self) -> None:
        assert self.router.validate_pt("") is False

    def test_random_word(self) -> None:
        assert self.router.validate_pt("latest") is False

    def test_month_zero(self) -> None:
        assert self.router.validate_pt("20260001") is False

    def test_day_zero(self) -> None:
        assert self.router.validate_pt("20260100") is False


# ---------------------------------------------------------------------------
# resolve_dir
# ---------------------------------------------------------------------------


class TestResolveDir:
    def setup_method(self) -> None:
        self.router = DataSourceRouter(base_output_dir=Path("/data/output"))

    def test_date_partition(self) -> None:
        assert self.router.resolve_dir("20260412") == Path("/data/output/20260412")

    def test_legacy(self) -> None:
        assert self.router.resolve_dir("_legacy") == Path("/data/output/_legacy")


# ---------------------------------------------------------------------------
# get_latest_pt
# ---------------------------------------------------------------------------


class TestGetLatestPt:
    def test_returns_latest_date(self, tmp_path: Path) -> None:
        (tmp_path / "20260410").mkdir()
        (tmp_path / "20260412").mkdir()
        (tmp_path / "20260411").mkdir()
        router = DataSourceRouter(base_output_dir=tmp_path)
        assert router.get_latest_pt() == "20260412"

    def test_ignores_legacy(self, tmp_path: Path) -> None:
        (tmp_path / "_legacy").mkdir()
        (tmp_path / "20260410").mkdir()
        router = DataSourceRouter(base_output_dir=tmp_path)
        assert router.get_latest_pt() == "20260410"

    def test_ignores_non_date_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "data").mkdir()
        (tmp_path / "temp").mkdir()
        (tmp_path / "20260412").mkdir()
        router = DataSourceRouter(base_output_dir=tmp_path)
        assert router.get_latest_pt() == "20260412"

    def test_no_date_dirs_returns_none(self, tmp_path: Path) -> None:
        (tmp_path / "_legacy").mkdir()
        (tmp_path / "data").mkdir()
        router = DataSourceRouter(base_output_dir=tmp_path)
        assert router.get_latest_pt() is None

    def test_empty_dir_returns_none(self, tmp_path: Path) -> None:
        router = DataSourceRouter(base_output_dir=tmp_path)
        assert router.get_latest_pt() is None

    def test_nonexistent_base_returns_none(self, tmp_path: Path) -> None:
        router = DataSourceRouter(base_output_dir=tmp_path / "nope")
        assert router.get_latest_pt() is None

    def test_ignores_invalid_date_dirs(self, tmp_path: Path) -> None:
        # 8 digits but not a valid calendar date
        (tmp_path / "20231301").mkdir()
        (tmp_path / "20260412").mkdir()
        router = DataSourceRouter(base_output_dir=tmp_path)
        assert router.get_latest_pt() == "20260412"

    def test_files_not_counted(self, tmp_path: Path) -> None:
        # A file named like a date should be ignored (not a directory)
        (tmp_path / "20260412").write_text("not a dir")
        router = DataSourceRouter(base_output_dir=tmp_path)
        assert router.get_latest_pt() is None


# ---------------------------------------------------------------------------
# helpers – create a minimal SQLite with pipeline_runs rows
# ---------------------------------------------------------------------------

import sqlite3
import time
from unittest.mock import patch


def _create_sqlite(partition_dir: Path, row_count: int = 0) -> None:
    """Create a minimal ``pipeline_results.sqlite3`` with *row_count* rows."""
    db_path = partition_dir / "pipeline_results.sqlite3"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE pipeline_runs (run_id TEXT PRIMARY KEY, entity_key TEXT NOT NULL)"
    )
    for i in range(row_count):
        conn.execute(
            "INSERT INTO pipeline_runs (run_id, entity_key) VALUES (?, ?)",
            (f"run_{i}", f"ent_{i}"),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# list_dates
# ---------------------------------------------------------------------------


class TestListDates:
    def test_basic_date_entries(self, tmp_path: Path) -> None:
        d1 = tmp_path / "20260412"
        d1.mkdir()
        _create_sqlite(d1, row_count=5)

        d2 = tmp_path / "20260411"
        d2.mkdir()
        _create_sqlite(d2, row_count=3)

        router = DataSourceRouter(base_output_dir=tmp_path)
        result = router.list_dates()

        assert len(result) == 2
        assert result[0] == {"pt": "20260412", "record_count": 5}
        assert result[1] == {"pt": "20260411", "record_count": 3}

    def test_descending_order(self, tmp_path: Path) -> None:
        for name in ["20260410", "20260412", "20260411"]:
            d = tmp_path / name
            d.mkdir()
            _create_sqlite(d, row_count=1)

        router = DataSourceRouter(base_output_dir=tmp_path)
        pts = [e["pt"] for e in router.list_dates()]
        assert pts == ["20260412", "20260411", "20260410"]

    def test_legacy_at_end(self, tmp_path: Path) -> None:
        d1 = tmp_path / "20260412"
        d1.mkdir()
        _create_sqlite(d1, row_count=2)

        legacy = tmp_path / "_legacy"
        legacy.mkdir()
        _create_sqlite(legacy, row_count=10)

        router = DataSourceRouter(base_output_dir=tmp_path)
        result = router.list_dates()

        assert len(result) == 2
        assert result[0] == {"pt": "20260412", "record_count": 2}
        assert result[-1] == {"pt": "_legacy", "record_count": 10}

    def test_no_legacy_when_absent(self, tmp_path: Path) -> None:
        d = tmp_path / "20260412"
        d.mkdir()
        _create_sqlite(d, row_count=1)

        router = DataSourceRouter(base_output_dir=tmp_path)
        result = router.list_dates()
        pts = [e["pt"] for e in result]
        assert "_legacy" not in pts

    def test_ignores_non_date_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "data").mkdir()
        (tmp_path / "temp").mkdir()
        d = tmp_path / "20260412"
        d.mkdir()
        _create_sqlite(d, row_count=1)

        router = DataSourceRouter(base_output_dir=tmp_path)
        result = router.list_dates()
        assert len(result) == 1
        assert result[0]["pt"] == "20260412"

    def test_ignores_invalid_date_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "20231301").mkdir()  # invalid month
        d = tmp_path / "20260412"
        d.mkdir()
        _create_sqlite(d, row_count=1)

        router = DataSourceRouter(base_output_dir=tmp_path)
        result = router.list_dates()
        assert len(result) == 1

    def test_missing_sqlite_gives_zero_count(self, tmp_path: Path) -> None:
        (tmp_path / "20260412").mkdir()  # no sqlite file

        router = DataSourceRouter(base_output_dir=tmp_path)
        result = router.list_dates()
        assert result[0] == {"pt": "20260412", "record_count": 0}

    def test_empty_base_dir(self, tmp_path: Path) -> None:
        router = DataSourceRouter(base_output_dir=tmp_path)
        assert router.list_dates() == []

    def test_nonexistent_base_dir(self, tmp_path: Path) -> None:
        router = DataSourceRouter(base_output_dir=tmp_path / "nope")
        assert router.list_dates() == []

    def test_only_legacy(self, tmp_path: Path) -> None:
        legacy = tmp_path / "_legacy"
        legacy.mkdir()
        _create_sqlite(legacy, row_count=7)

        router = DataSourceRouter(base_output_dir=tmp_path)
        result = router.list_dates()
        assert len(result) == 1
        assert result[0] == {"pt": "_legacy", "record_count": 7}


# ---------------------------------------------------------------------------
# _DatesCache TTL behaviour
# ---------------------------------------------------------------------------


class TestDatesCacheTTL:
    def test_cache_returns_same_result(self, tmp_path: Path) -> None:
        d = tmp_path / "20260412"
        d.mkdir()
        _create_sqlite(d, row_count=3)

        router = DataSourceRouter(base_output_dir=tmp_path, cache_ttl=60)
        first = router.list_dates()

        # Add another directory – should NOT appear because cache is valid
        d2 = tmp_path / "20260413"
        d2.mkdir()
        _create_sqlite(d2, row_count=1)

        second = router.list_dates()
        assert first is second  # exact same list object

    def test_cache_expires(self, tmp_path: Path) -> None:
        d = tmp_path / "20260412"
        d.mkdir()
        _create_sqlite(d, row_count=3)

        router = DataSourceRouter(base_output_dir=tmp_path, cache_ttl=60)
        first = router.list_dates()
        assert len(first) == 1

        # Add another directory
        d2 = tmp_path / "20260413"
        d2.mkdir()
        _create_sqlite(d2, row_count=1)

        # Fast-forward time past TTL
        with patch("industry_classification.api.data_source_router.time") as mock_time:
            mock_time.monotonic.return_value = time.monotonic() + 120
            second = router.list_dates()

        assert len(second) == 2


# ---------------------------------------------------------------------------
# helpers for aggregate_stats / list_daily_summaries tests
# ---------------------------------------------------------------------------

import json


def _create_full_sqlite(
    partition_dir: Path,
    rows: list[tuple[str, str, str, str | None]],
) -> None:
    """Create ``pipeline_results.sqlite3`` with route, final_label, annotations columns.

    Each row is ``(run_id, entity_key, route, annotations_json)``.
    ``final_label`` is derived from the route for simplicity.
    """
    db_path = partition_dir / "pipeline_results.sqlite3"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE pipeline_runs (
            run_id TEXT PRIMARY KEY,
            entity_key TEXT NOT NULL,
            route TEXT,
            final_label TEXT,
            annotations TEXT
        )"""
    )
    for run_id, entity_key, route, annotations in rows:
        label = "制造业" if route == "formal" else "服务业"
        conn.execute(
            "INSERT INTO pipeline_runs (run_id, entity_key, route, final_label, annotations) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, entity_key, route, label, annotations),
        )
    conn.commit()
    conn.close()


def _write_summary(partition_dir: Path, processed: int, formal: int, fallback: int) -> None:
    """Write a ``run_summary.json`` file."""
    data = {
        "processed_count": processed,
        "formal_count": formal,
        "fallback_count": fallback,
    }
    (partition_dir / "run_summary.json").write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# aggregate_stats
# ---------------------------------------------------------------------------


class TestAggregateStats:
    def test_single_partition(self, tmp_path: Path) -> None:
        d = tmp_path / "20260412"
        d.mkdir()
        _create_full_sqlite(d, [
            ("r1", "e1", "formal", "[]"),
            ("r2", "e2", "fallback", None),
        ])
        router = DataSourceRouter(base_output_dir=tmp_path)
        result = router.aggregate_stats("20260412", "20260412")
        assert result.total_processed == 2
        assert result.label_distribution["制造业"] == 1
        assert result.label_distribution["服务业"] == 1

    def test_multi_partition_aggregation(self, tmp_path: Path) -> None:
        d1 = tmp_path / "20260410"
        d1.mkdir()
        _create_full_sqlite(d1, [
            ("r1", "e1", "formal", "[]"),
            ("r2", "e2", "formal", '[{"label":"x"}]'),
        ])
        d2 = tmp_path / "20260411"
        d2.mkdir()
        _create_full_sqlite(d2, [
            ("r3", "e3", "fallback", None),
        ])
        router = DataSourceRouter(base_output_dir=tmp_path)
        result = router.aggregate_stats("20260410", "20260411")
        assert result.total_processed == 3
        assert result.annotated_count == 1  # only r2 has non-empty annotations
        assert result.label_distribution["制造业"] == 2
        assert result.label_distribution["服务业"] == 1

    def test_skips_missing_partitions(self, tmp_path: Path) -> None:
        d = tmp_path / "20260410"
        d.mkdir()
        _create_full_sqlite(d, [("r1", "e1", "formal", None)])
        # 20260411 does not exist
        router = DataSourceRouter(base_output_dir=tmp_path)
        result = router.aggregate_stats("20260410", "20260411")
        assert result.total_processed == 1

    def test_pt_start_after_pt_end_raises(self, tmp_path: Path) -> None:
        router = DataSourceRouter(base_output_dir=tmp_path)
        with pytest.raises(ValueError, match="must not be later"):
            router.aggregate_stats("20260413", "20260410")

    def test_empty_range_no_partitions(self, tmp_path: Path) -> None:
        router = DataSourceRouter(base_output_dir=tmp_path)
        result = router.aggregate_stats("20260410", "20260412")
        assert result.total_processed == 0
        assert result.label_distribution == {}

    def test_partition_without_sqlite(self, tmp_path: Path) -> None:
        d = tmp_path / "20260410"
        d.mkdir()
        # directory exists but no sqlite file
        router = DataSourceRouter(base_output_dir=tmp_path)
        result = router.aggregate_stats("20260410", "20260410")
        assert result.total_processed == 0

    def test_label_distribution_merges_across_partitions(self, tmp_path: Path) -> None:
        d1 = tmp_path / "20260410"
        d1.mkdir()
        _create_full_sqlite(d1, [("r1", "e1", "formal", None)])
        d2 = tmp_path / "20260411"
        d2.mkdir()
        _create_full_sqlite(d2, [("r2", "e2", "formal", None)])
        router = DataSourceRouter(base_output_dir=tmp_path)
        result = router.aggregate_stats("20260410", "20260411")
        # Both are "formal" → label "制造业", should merge
        assert result.label_distribution["制造业"] == 2


# ---------------------------------------------------------------------------
# list_daily_summaries
# ---------------------------------------------------------------------------


class TestListDailySummaries:
    def test_prefers_run_summary_json(self, tmp_path: Path) -> None:
        d = tmp_path / "20260412"
        d.mkdir()
        _write_summary(d, processed=10, formal=7, fallback=3)
        _create_full_sqlite(d, [("r1", "e1", "formal", None)])  # should be ignored
        router = DataSourceRouter(base_output_dir=tmp_path)
        result = router.list_daily_summaries("20260412", "20260412")
        assert len(result) == 1
        assert result[0]["total_count"] == 10
        assert result[0]["formal_count"] == 7
        assert result[0]["fallback_count"] == 3

    def test_falls_back_to_sqlite(self, tmp_path: Path) -> None:
        d = tmp_path / "20260412"
        d.mkdir()
        _create_full_sqlite(d, [
            ("r1", "e1", "formal", None),
            ("r2", "e2", "formal", None),
            ("r3", "e3", "fallback", None),
        ])
        router = DataSourceRouter(base_output_dir=tmp_path)
        result = router.list_daily_summaries("20260412", "20260412")
        assert len(result) == 1
        assert result[0]["total_count"] == 3
        assert result[0]["formal_count"] == 2
        assert result[0]["fallback_count"] == 1

    def test_skips_missing_partitions(self, tmp_path: Path) -> None:
        d = tmp_path / "20260410"
        d.mkdir()
        _write_summary(d, processed=5, formal=3, fallback=2)
        # 20260411 does not exist
        router = DataSourceRouter(base_output_dir=tmp_path)
        result = router.list_daily_summaries("20260410", "20260411")
        assert len(result) == 1
        assert result[0]["pt"] == "20260410"

    def test_sorted_descending(self, tmp_path: Path) -> None:
        for date in ["20260410", "20260411", "20260412"]:
            d = tmp_path / date
            d.mkdir()
            _write_summary(d, processed=1, formal=1, fallback=0)
        router = DataSourceRouter(base_output_dir=tmp_path)
        result = router.list_daily_summaries("20260410", "20260412")
        pts = [s["pt"] for s in result]
        assert pts == ["20260412", "20260411", "20260410"]

    def test_pt_start_after_pt_end_raises(self, tmp_path: Path) -> None:
        router = DataSourceRouter(base_output_dir=tmp_path)
        with pytest.raises(ValueError, match="must not be later"):
            router.list_daily_summaries("20260413", "20260410")

    def test_empty_range_no_partitions(self, tmp_path: Path) -> None:
        router = DataSourceRouter(base_output_dir=tmp_path)
        result = router.list_daily_summaries("20260410", "20260412")
        assert result == []

    def test_partition_without_sqlite_or_summary(self, tmp_path: Path) -> None:
        d = tmp_path / "20260410"
        d.mkdir()
        # directory exists but no sqlite and no run_summary.json
        router = DataSourceRouter(base_output_dir=tmp_path)
        result = router.list_daily_summaries("20260410", "20260410")
        assert result == []
