"""DataSourceRouter – route API requests to date-partitioned data directories.

Each batch run produces output under ``output/{pt}/`` where *pt* is a
``yyyymmdd`` date string.  Legacy data lives under ``output/_legacy/``.
This module validates *pt* values, resolves directory paths, and (in later
tasks) builds per-partition service instances on the fly.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from industry_classification.api.schemas import StatsResponse

from industry_classification.api.services import (
    FallbackService,
    RunService,
    SearchService,
    StatsService,
)
from industry_classification.writers.jsonl_store import JsonlKeyedStore

logger = logging.getLogger(__name__)

_YYYYMMDD_RE = re.compile(r"^\d{8}$")
_DATE_RANGE_RE = re.compile(r"^(\d{8})_(\d{8})$")


@dataclass
class _DatesCache:
    """In-memory cache for the date list returned by ``list_dates()``."""

    entries: list[dict] = field(default_factory=list)
    latest_pt: str | None = None
    expires_at: float = 0.0


class DataSourceRouter:
    """Map a ``pt`` parameter to the corresponding date-partition directory."""

    def __init__(self, base_output_dir: Path, cache_ttl: int = 60) -> None:
        self._base = Path(base_output_dir)
        self._cache_ttl = cache_ttl
        self._dates_cache: _DatesCache | None = None

    # ------------------------------------------------------------------
    # pt validation
    # ------------------------------------------------------------------

    def validate_pt(self, pt: str) -> bool:
        """Return *True* if *pt* is ``'_legacy'``, ``'_root'``, a valid ``yyyymmdd`` date, or ``yyyymmdd_yyyymmdd`` range."""
        if pt in ("_legacy", "_root"):
            return True
        if _YYYYMMDD_RE.match(pt):
            try:
                datetime.strptime(pt, "%Y%m%d")
                return True
            except ValueError:
                return False
        m = _DATE_RANGE_RE.match(pt)
        if m:
            try:
                datetime.strptime(m.group(1), "%Y%m%d")
                datetime.strptime(m.group(2), "%Y%m%d")
                return True
            except ValueError:
                return False
        return False

    # ------------------------------------------------------------------
    # directory resolution
    # ------------------------------------------------------------------

    def resolve_dir(self, pt: str) -> Path:
        """Return ``base_output_dir / pt``.  Does **not** check existence.

        Special case: ``_legacy`` resolves to ``base_output_dir / _legacy``
        if it exists, otherwise falls back to ``base_output_dir`` itself
        (where single-classify results are written).
        """
        if pt == "_legacy":
            legacy_dir = self._base / "_legacy"
            if legacy_dir.is_dir():
                return legacy_dir
            return self._base
        if pt == "_root":
            return self._base
        return self._base / pt

    # ------------------------------------------------------------------
    # latest date
    # ------------------------------------------------------------------

    def get_latest_pt(self) -> str | None:
        """Scan *base_output_dir* for ``yyyymmdd`` directories and return the latest.

        Returns ``None`` when no date-partition directories exist.
        """
        if not self._base.is_dir():
            return None

        latest: str | None = None
        for child in self._base.iterdir():
            if not child.is_dir():
                continue
            name = child.name
            if not _YYYYMMDD_RE.match(name):
                continue
            try:
                datetime.strptime(name, "%Y%m%d")
            except ValueError:
                continue
            if latest is None or name > latest:
                latest = name
        return latest

    # ------------------------------------------------------------------
    # service construction
    # ------------------------------------------------------------------

    def build_services(self, pt: str) -> dict[str, Any]:
        """Build service instances for the given *pt* partition.

        Each call constructs fresh instances so that no long-lived references
        are held across requests (requirement 8.1).

        Raises ``ValueError`` if the resolved directory does not exist.
        """
        partition_dir = self.resolve_dir(pt)
        if not partition_dir.is_dir():
            raise ValueError(f"Partition directory does not exist: {partition_dir}")

        formal_path = partition_dir / "formal_output.jsonl"
        fallback_path = partition_dir / "fallback_output.jsonl"
        sqlite_path = partition_dir / "pipeline_results.sqlite3"

        formal_store = JsonlKeyedStore(formal_path)
        fallback_store = JsonlKeyedStore(fallback_path)

        # wide_row_index is optional context; build empty dict per-partition
        wide_index: dict[str, Any] = {}

        sql = sqlite_path if sqlite_path.is_file() else None

        return {
            "stats_service": StatsService(formal_store, fallback_store, sqlite_path=sql),
            "run_service": RunService(formal_store, fallback_store, wide_row_index=wide_index, sqlite_path=sql),
            "search_service": SearchService(formal_store, fallback_store, wide_row_index=wide_index, sqlite_path=sql),
            "fallback_service": FallbackService(formal_store, fallback_store, wide_row_index=wide_index, sqlite_path=sql),
        }

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_record_count(partition_dir: Path) -> int:
        """Open the partition's SQLite file, read the row count, and close immediately."""
        db_path = partition_dir / "pipeline_results.sqlite3"
        if not db_path.is_file():
            return 0
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                count = conn.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0]
            except sqlite3.OperationalError:
                count = 0
            finally:
                conn.close()
            return count
        except Exception:
            logger.debug("Failed to read record count from %s", db_path, exc_info=True)
            return 0

    # ------------------------------------------------------------------
    # list dates
    # ------------------------------------------------------------------

    def list_dates(self) -> list[dict]:
        """Return available date partitions sorted descending, ``_legacy`` last.

        Results are cached in memory for ``cache_ttl`` seconds.
        """
        if (
            self._dates_cache is not None
            and time.monotonic() < self._dates_cache.expires_at
        ):
            return self._dates_cache.entries

        if not self._base.is_dir():
            entries: list[dict] = []
            self._dates_cache = _DatesCache(
                entries=entries,
                latest_pt=None,
                expires_at=time.monotonic() + self._cache_ttl,
            )
            return entries

        date_entries: list[dict] = []
        range_entries: list[dict] = []
        has_legacy = False

        for child in self._base.iterdir():
            if not child.is_dir():
                continue
            name = child.name
            if name == "_legacy":
                has_legacy = True
                continue
            # Single date: yyyymmdd
            if _YYYYMMDD_RE.match(name):
                try:
                    datetime.strptime(name, "%Y%m%d")
                except ValueError:
                    continue
                record_count = self._read_record_count(child)
                date_entries.append({"pt": name, "record_count": record_count})
                continue
            # Date range: yyyymmdd_yyyymmdd
            m = _DATE_RANGE_RE.match(name)
            if m:
                try:
                    datetime.strptime(m.group(1), "%Y%m%d")
                    datetime.strptime(m.group(2), "%Y%m%d")
                except ValueError:
                    continue
                record_count = self._read_record_count(child)
                range_entries.append({"pt": name, "record_count": record_count})

        # Sort by date descending
        date_entries.sort(key=lambda e: e["pt"], reverse=True)
        # Range entries sorted by end date descending
        range_entries.sort(key=lambda e: e["pt"].split("_")[1], reverse=True)

        latest_pt = date_entries[0]["pt"] if date_entries else None

        # Combine: single dates first, then ranges, then _legacy
        all_entries = date_entries + range_entries

        # Append _legacy at the end
        if has_legacy:
            legacy_dir = self._base / "_legacy"
            record_count = self._read_record_count(legacy_dir)
            all_entries.append({"pt": "_legacy", "record_count": record_count})

        self._dates_cache = _DatesCache(
            entries=all_entries,
            latest_pt=latest_pt,
            expires_at=time.monotonic() + self._cache_ttl,
        )
        return all_entries

    # ------------------------------------------------------------------
    # date range helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _date_range(pt_start: str, pt_end: str) -> list[str]:
        """Return all ``yyyymmdd`` strings from *pt_start* to *pt_end* inclusive."""
        start = datetime.strptime(pt_start, "%Y%m%d")
        end = datetime.strptime(pt_end, "%Y%m%d")
        days: list[str] = []
        cur = start
        while cur <= end:
            days.append(cur.strftime("%Y%m%d"))
            cur += timedelta(days=1)
        return days

    # ------------------------------------------------------------------
    # range aggregation
    # ------------------------------------------------------------------

    def aggregate_stats(self, pt_start: str, pt_end: str) -> StatsResponse:
        """Aggregate statistics across all existing partitions in the date range.

        Opens and closes each partition's SQLite connection individually
        (requirement 8.2).  Non-existent partitions are silently skipped
        (requirement 4.5).

        Raises ``ValueError`` when *pt_start* > *pt_end* (requirement 4.4).
        """
        if pt_start > pt_end:
            raise ValueError(
                f"pt_start ({pt_start}) must not be later than pt_end ({pt_end})"
            )

        total_processed = 0
        annotated_count = 0
        label_distribution: dict[str, int] = {}

        for pt in self._date_range(pt_start, pt_end):
            partition_dir = self.resolve_dir(pt)
            if not partition_dir.is_dir():
                continue

            db_path = partition_dir / "pipeline_results.sqlite3"
            if not db_path.is_file():
                continue

            try:
                conn = sqlite3.connect(str(db_path))
                try:
                    # count by route
                    rows = conn.execute(
                        "SELECT route, COUNT(*) FROM pipeline_runs GROUP BY route"
                    ).fetchall()
                    for route, cnt in rows:
                        total_processed += cnt

                    # label distribution
                    rows = conn.execute(
                        "SELECT final_label, COUNT(*) FROM pipeline_runs GROUP BY final_label"
                    ).fetchall()
                    for label, cnt in rows:
                        key = label or "未知"
                        label_distribution[key] = label_distribution.get(key, 0) + cnt

                    # annotated count
                    row = conn.execute(
                        "SELECT COUNT(*) FROM pipeline_runs "
                        "WHERE annotations IS NOT NULL AND annotations != '[]'"
                    ).fetchone()
                    annotated_count += row[0] if row else 0
                except sqlite3.OperationalError:
                    logger.debug(
                        "Failed to query stats from %s", db_path, exc_info=True
                    )
                finally:
                    conn.close()
            except Exception:
                logger.debug(
                    "Failed to open SQLite at %s", db_path, exc_info=True
                )

        return StatsResponse(
            total_processed=total_processed,
            annotated_count=annotated_count,
            unannotated_count=total_processed - annotated_count,
            label_distribution=label_distribution,
        )

    # ------------------------------------------------------------------
    # daily summaries
    # ------------------------------------------------------------------

    def list_daily_summaries(self, pt_start: str, pt_end: str) -> list[dict]:
        """Return per-day summaries for existing partitions in the date range.

        Prefers ``run_summary.json`` when available (requirement 5.4);
        falls back to querying SQLite.  Results are sorted by date descending
        (requirement 5.5).

        Raises ``ValueError`` when *pt_start* > *pt_end*.
        """
        if pt_start > pt_end:
            raise ValueError(
                f"pt_start ({pt_start}) must not be later than pt_end ({pt_end})"
            )

        summaries: list[dict] = []

        for pt in self._date_range(pt_start, pt_end):
            partition_dir = self.resolve_dir(pt)
            if not partition_dir.is_dir():
                continue

            summary_path = partition_dir / "run_summary.json"
            if summary_path.is_file():
                try:
                    data = json.loads(summary_path.read_text(encoding="utf-8"))
                    formal_count = data.get("formal_count", 0)
                    fallback_count = data.get("fallback_count", 0)
                    total_count = data.get(
                        "processed_count", formal_count + fallback_count
                    )
                    summaries.append(
                        {
                            "pt": pt,
                            "total_count": total_count,
                            "formal_count": formal_count,
                            "fallback_count": fallback_count,
                        }
                    )
                    continue
                except Exception:
                    logger.debug(
                        "Failed to read run_summary.json from %s",
                        summary_path,
                        exc_info=True,
                    )
                    # fall through to SQLite

            # Fallback: query SQLite
            db_path = partition_dir / "pipeline_results.sqlite3"
            if not db_path.is_file():
                continue

            try:
                conn = sqlite3.connect(str(db_path))
                try:
                    rows = conn.execute(
                        "SELECT route, COUNT(*) FROM pipeline_runs GROUP BY route"
                    ).fetchall()
                    formal_count = 0
                    fallback_count = 0
                    for route, cnt in rows:
                        if route == "formal":
                            formal_count = cnt
                        elif route == "fallback":
                            fallback_count = cnt
                    summaries.append(
                        {
                            "pt": pt,
                            "total_count": formal_count + fallback_count,
                            "formal_count": formal_count,
                            "fallback_count": fallback_count,
                        }
                    )
                except sqlite3.OperationalError:
                    logger.debug(
                        "Failed to query summaries from %s",
                        db_path,
                        exc_info=True,
                    )
                finally:
                    conn.close()
            except Exception:
                logger.debug(
                    "Failed to open SQLite at %s", db_path, exc_info=True
                )

        # Sort by date descending (requirement 5.5)
        summaries.sort(key=lambda s: s["pt"], reverse=True)
        return summaries
