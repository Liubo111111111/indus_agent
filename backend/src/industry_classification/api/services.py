"""Service layer for the Dashboard API.

Each service class accepts ``JsonlKeyedStore`` instances (formal / fallback)
as constructor parameters and exposes thin business-logic methods that the
route layer calls.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

from industry_classification.api.schemas import (
    AccessSettingsResponse,
    AccessSettingsUpdate,
    AnnotationResponse,
    FallbackRecord,
    PaginatedFallbackList,
    PaginatedRunList,
    ReviewResponse,
    RunDetail,
    RunSummary,
    SearchResult,
    SettingsResponse,
    SettingsUpdate,
    StatsResponse,
    TaxonomyLabelDTO,
    TaxonomyResponse,
)
from industry_classification.settings import (
    _load_env_values,
    load_llm_settings,
    load_taxonomy,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"


def _extract_entity_key(publish_key: str) -> str:
    """Return the first segment of a ``publish_key`` (the entity_key)."""
    return publish_key.split("::")[0]


def _get_audit(record: dict[str, Any]) -> dict[str, Any]:
    return record.get("audit") or {}


class _SqliteResultReader:
    def __init__(self, sqlite_path: Path | None) -> None:
        self._path = sqlite_path

    @property
    def enabled(self) -> bool:
        if self._path is None or not self._path.exists():
            return False
        try:
            conn = sqlite3.connect(self._path)
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='pipeline_runs'"
            ).fetchone()
            conn.close()
            return row is not None
        except Exception:
            return False

    def _connect(self) -> sqlite3.Connection:
        assert self._path is not None
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _load_json(payload: str | None, default: Any) -> Any:
        if not payload:
            return default
        return json.loads(payload)

    def _list_run_rows(self) -> list[sqlite3.Row]:
        if not self.enabled:
            return []
        with self._connect() as conn:
            return conn.execute(
                """
                select
                    r.run_id,
                    r.entity_key,
                    r.route,
                    r.error_type,
                    r.wide_row_json,
                    r.static_profile_json,
                    r.dynamic_profile_json,
                    r.decision_record_json,
                    r.timing_ms_json,
                    r.feature_schema_version,
                    r.taxonomy_version,
                    r.graph_version,
                    r.prompt_version_static,
                    r.prompt_version_dynamic,
                    r.prompt_version_final,
                    r.model_version_static,
                    r.model_version_dynamic,
                    r.model_version_final,
                    r.created_at,
                    r.updated_at
                from pipeline_runs r
                inner join (
                    select entity_key, max(updated_at) as max_updated
                    from pipeline_runs
                    group by entity_key
                ) latest
                    on r.entity_key = latest.entity_key
                   and r.updated_at = latest.max_updated
                order by r.updated_at desc, r.run_id desc
                """
            ).fetchall()

    def _annotation_map(self) -> dict[str, list[dict[str, Any]]]:
        if not self.enabled:
            return {}
        with self._connect() as conn:
            rows = conn.execute(
                """
                select run_id, entity_key, annotated_label, reviewer_notes, reviewer_name, created_at
                from annotations
                order by created_at asc
                """
            ).fetchall()
        result: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            entry = {
                "annotated_label": row["annotated_label"],
                "reviewer_notes": row["reviewer_notes"],
                "reviewer_name": row["reviewer_name"] if "reviewer_name" in row.keys() else "",
                "created_at": row["created_at"],
            }
            result.setdefault(row["run_id"], []).append(entry)
        return result

    def count_by_route(self) -> tuple[int, int]:
        runs = self._list_run_rows()
        formal = sum(1 for row in runs if row["route"] == "formal")
        fallback = sum(1 for row in runs if row["route"] == "fallback")
        return formal, fallback

    def list_runs(self, offset: int, limit: int) -> list[dict[str, Any]]:
        rows = self._list_run_rows()
        page = rows[offset : offset + limit]
        annotations = self._annotation_map()
        result: list[dict[str, Any]] = []
        for row in page:
            wide = self._load_json(row["wide_row_json"], {})
            decision = self._load_json(row["decision_record_json"], {})
            ann_list = annotations.get(row["run_id"], [])
            latest_label = ann_list[-1]["annotated_label"] if ann_list else None
            result.append(
                {
                    "run_id": row["run_id"],
                    "entity_key": row["entity_key"],
                    "enterprise_name": wide.get("enterprise_name", row["entity_key"]),
                    "final_label": latest_label or decision.get("final_label"),
                    "confidence_level": decision.get("confidence_level"),
                    "route": row["route"],
                    "error_type": row["error_type"],
                    "timestamp": None,
                    "annotations": ann_list,
                }
            )
        return result

    def get_run_detail(self, run_id: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                select
                    run_id,
                    entity_key,
                    route,
                    error_type,
                    wide_row_json,
                    static_profile_json,
                    dynamic_profile_json,
                    decision_record_json,
                    timing_ms_json,
                    feature_schema_version,
                    taxonomy_version,
                    graph_version,
                    prompt_version_static,
                    prompt_version_dynamic,
                    prompt_version_final,
                    model_version_static,
                    model_version_dynamic,
                    model_version_final
                from pipeline_runs
                where run_id = ?
                """,
                (run_id,),
            ).fetchone()
            annotation_row = conn.execute(
                """
                select annotated_label, reviewer_notes, created_at
                from annotations
                where run_id = ?
                order by created_at asc
                """,
                (run_id,),
            ).fetchall()
        if row is None:
            return None
        wide = self._load_json(row["wide_row_json"], {})
        ann_list = [
            {
                "annotated_label": ar["annotated_label"],
                "reviewer_notes": ar["reviewer_notes"],
                "created_at": ar["created_at"],
            }
            for ar in annotation_row
        ]
        return {
            "run_id": row["run_id"],
            "entity_key": row["entity_key"],
            "enterprise_name": wide.get("enterprise_name", row["entity_key"]),
            "business_scope": wide.get("business_scope", ""),
            "wide_row": wide,
            "static_profile": self._load_json(row["static_profile_json"], None),
            "dynamic_profile": self._load_json(row["dynamic_profile_json"], None),
            "decision_record": self._load_json(row["decision_record_json"], None),
            "route": row["route"],
            "error_type": row["error_type"],
            "audit": {
                "run_id": row["run_id"],
                "entity_key": row["entity_key"],
                "feature_schema_version": row["feature_schema_version"],
                "taxonomy_version": row["taxonomy_version"],
                "graph_version": row["graph_version"],
                "prompt_version_static": row["prompt_version_static"],
                "prompt_version_dynamic": row["prompt_version_dynamic"],
                "prompt_version_final": row["prompt_version_final"],
                "model_version_static": row["model_version_static"],
                "model_version_dynamic": row["model_version_dynamic"],
                "model_version_final": row["model_version_final"],
                "route": row["route"],
            },
            "timing_ms": self._load_json(row["timing_ms_json"], None),
            "annotations": ann_list,
        }

    def search(self, query: str) -> list[dict[str, Any]]:
        query_lower = query.lower()
        annotations = self._annotation_map()
        items: list[dict[str, Any]] = []
        for row in self._list_run_rows():
            wide = self._load_json(row["wide_row_json"], {})
            enterprise_name = wide.get("enterprise_name", row["entity_key"])
            if query_lower in row["entity_key"].lower() or query_lower in enterprise_name.lower():
                decision = self._load_json(row["decision_record_json"], {})
                ann_list = annotations.get(row["run_id"], [])
                latest_label = ann_list[-1]["annotated_label"] if ann_list else None
                items.append(
                    {
                        "entity_key": row["entity_key"],
                        "enterprise_name": enterprise_name,
                        "final_label": latest_label or decision.get("final_label"),
                        "route": row["route"],
                        "run_id": row["run_id"],
                    }
                )
        return items

    def list_fallbacks(self, offset: int, limit: int) -> list[dict[str, Any]]:
        rows = [row for row in self._list_run_rows() if row["route"] == "fallback"]
        result: list[dict[str, Any]] = []
        for row in rows[offset : offset + limit]:
            wide = self._load_json(row["wide_row_json"], {})
            decision = self._load_json(row["decision_record_json"], {})
            result.append(
                {
                    "entity_key": row["entity_key"],
                    "enterprise_name": wide.get("enterprise_name", row["entity_key"]),
                    "final_label": decision.get("final_label"),
                    "confidence_level": decision.get("confidence_level"),
                    "error_type": row["error_type"],
                    "decision_record": decision or None,
                    "audit": {
                        "run_id": row["run_id"],
                        "entity_key": row["entity_key"],
                        "route": row["route"],
                    },
                }
            )
        return result

    def count_annotated(self) -> int:
        if not self.enabled:
            return 0
        with self._connect() as conn:
            row = conn.execute(
                "select count(distinct run_id) from annotations"
            ).fetchone()
            return row[0] if row else 0

    def get_label_distribution(self) -> dict[str, int]:
        if not self.enabled:
            return {}
        dist: dict[str, int] = {}
        with self._connect() as conn:
            # 优先从 inference_steps 取模型原始 final_decision 结果
            step_labels: dict[str, str] = {}
            step_rows = conn.execute(
                """
                select run_id, result_json
                from inference_steps
                where step_name = 'final_decision'
                """
            ).fetchall()
            for sr in step_rows:
                result = self._load_json(sr["result_json"], {})
                if result and result.get("final_label"):
                    step_labels[sr["run_id"]] = result["final_label"]

        for row in self._list_run_rows():
            # 优先用 inference_steps 中的模型原始标签
            label = step_labels.get(row["run_id"])
            if not label:
                decision = self._load_json(row["decision_record_json"], {})
                label = decision.get("final_label") if decision else None
            dist[label or "未知"] = dist.get(label or "未知", 0) + 1
        return dist

    def list_annotated_runs(self) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        annotations = self._annotation_map()
        if not annotations:
            return []
        result: list[dict[str, Any]] = []
        for row in self._list_run_rows():
            ann_list = annotations.get(row["run_id"])
            if not ann_list:
                continue
            wide = self._load_json(row["wide_row_json"], {})
            decision = self._load_json(row["decision_record_json"], {})
            latest = ann_list[-1]
            result.append({
                "run_id": row["run_id"],
                "entity_key": row["entity_key"],
                "enterprise_name": wide.get("enterprise_name", row["entity_key"]),
                "model_label": decision.get("final_label"),
                "annotated_label": latest["annotated_label"],
                "annotation_count": len(ann_list),
                "latest_notes": latest.get("reviewer_notes", ""),
                "latest_reviewer": latest.get("reviewer_name", ""),
                "latest_time": latest.get("created_at", ""),
                "annotations": ann_list,
            })
        return result

    def review_fallback(
        self,
        entity_key: str,
        approved_label: str,
        reviewer_notes: str,
    ) -> str | None:
        if not self.enabled:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                select run_id, decision_record_json
                from pipeline_runs
                where entity_key = ? and route = 'fallback'
                limit 1
                """,
                (entity_key,),
            ).fetchone()
            if row is None:
                return None
            decision = self._load_json(row["decision_record_json"], {})
            decision["final_label"] = approved_label
            decision["confidence_level"] = "human_review"
            decision["low_confidence"] = False
            decision["decision_reason"] = (
                f"Human review: {reviewer_notes}" if reviewer_notes else "Human review"
            )
            decision["supporting_evidence"] = []

            publish_row = conn.execute(
                """
                select publish_key, record_json
                from published_records
                where run_id = ? and route = 'fallback'
                limit 1
                """,
                (row["run_id"],),
            ).fetchone()

            conn.execute(
                """
                update pipeline_runs
                set route = 'formal',
                    error_type = null,
                    decision_record_json = ?,
                    updated_at = current_timestamp
                where run_id = ?
                """,
                (json.dumps(decision, ensure_ascii=False, sort_keys=True), row["run_id"]),
            )

            if publish_row is not None:
                fallback_publish_key = publish_row["publish_key"]
                formal_publish_key = (
                    "::".join(fallback_publish_key.split("::")[:-1])
                    if fallback_publish_key.endswith("::fallback")
                    else fallback_publish_key
                )
                record = self._load_json(publish_row["record_json"], {})
                record["decision_record"] = decision
                record["error_type"] = None
                audit = record.get("audit") or {}
                audit["route"] = "formal"
                audit["reviewer_notes"] = reviewer_notes
                audit["reviewed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                record["audit"] = audit
                conn.execute(
                    "delete from published_records where publish_key = ?",
                    (fallback_publish_key,),
                )
                conn.execute(
                    """
                    insert into published_records (
                        publish_key, run_id, entity_key, route, record_json, updated_at
                    ) values (?, ?, ?, 'formal', ?, current_timestamp)
                    """,
                    (
                        formal_publish_key,
                        row["run_id"],
                        entity_key,
                        json.dumps(record, ensure_ascii=False, sort_keys=True),
                    ),
                )
            conn.commit()
            return row["run_id"]

    def annotate_run(
        self,
        run_id: str,
        annotated_label: str,
        reviewer_notes: str,
        reviewer_name: str = "",
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                select run_id, entity_key, route
                from pipeline_runs
                where run_id = ?
                """,
                (run_id,),
            ).fetchone()
            if row is None:
                return None
            count = conn.execute(
                "select count(*) from annotations where run_id = ?",
                (run_id,),
            ).fetchone()[0]
            if count >= 3:
                return {
                    "run_id": run_id,
                    "annotated_label": annotated_label,
                    "status": "max_reached",
                    "annotation_count": count,
                }
            conn.execute(
                """
                insert into annotations (
                    run_id, entity_key, annotated_label, reviewer_notes, reviewer_name
                ) values (?, ?, ?, ?, ?)
                """,
                (run_id, row["entity_key"], annotated_label, reviewer_notes, reviewer_name),
            )
            if row["route"] == "fallback":
                conn.execute(
                    """
                    update pipeline_runs
                    set route = 'formal',
                        error_type = null,
                        updated_at = current_timestamp
                    where run_id = ?
                    """,
                    (run_id,),
                )
            conn.commit()
            return {
                "run_id": run_id,
                "annotated_label": annotated_label,
                "status": "annotated",
                "annotation_count": count + 1,
            }


# ---------------------------------------------------------------------------
# StatsService
# ---------------------------------------------------------------------------


class StatsService:
    """Compute aggregate statistics from formal / fallback stores."""

    def __init__(
        self,
        formal_store: MutableMapping[str, dict[str, Any]],
        fallback_store: MutableMapping[str, dict[str, Any]],
        sqlite_path: Path | None = None,
    ) -> None:
        self._formal = formal_store
        self._fallback = fallback_store
        self._sqlite = _SqliteResultReader(sqlite_path)

    def get_stats(self) -> StatsResponse:
        if self._sqlite.enabled:
            formal_count, fallback_count = self._sqlite.count_by_route()
            total = formal_count + fallback_count
            annotated_count = self._sqlite.count_annotated()
            label_dist = self._sqlite.get_label_distribution()
            return StatsResponse(
                total_processed=total,
                annotated_count=annotated_count,
                unannotated_count=total - annotated_count,
                label_distribution=label_dist,
            )
        formal_count = len(self._formal)
        fallback_count = len(self._fallback)
        total = formal_count + fallback_count
        annotated_count = sum(
            1 for r in list(self._formal.values()) + list(self._fallback.values())
            if r.get("annotations")
        )
        label_dist: dict[str, int] = {}
        for r in list(self._formal.values()) + list(self._fallback.values()):
            # 优先取顶层 final_label，再查嵌套的 decision_record
            label = r.get("final_label")
            if not label:
                dr = r.get("decision_record") or r.get("model_decision_record") or {}
                label = dr.get("final_label") if isinstance(dr, dict) else None
            label_dist[label or "未知"] = label_dist.get(label or "未知", 0) + 1
        return StatsResponse(
            total_processed=total,
            annotated_count=annotated_count,
            unannotated_count=total - annotated_count,
            label_distribution=label_dist,
        )


# ---------------------------------------------------------------------------
# RunService
# ---------------------------------------------------------------------------


class RunService:
    """Merge formal + fallback records and expose paginated listing / detail."""

    def __init__(
        self,
        formal_store: MutableMapping[str, dict[str, Any]],
        fallback_store: MutableMapping[str, dict[str, Any]],
        wide_row_index: dict[str, dict[str, Any]] | None = None,
        sqlite_path: Path | None = None,
    ) -> None:
        self._formal = formal_store
        self._fallback = fallback_store
        self._wide = wide_row_index or {}
        self._sqlite = _SqliteResultReader(sqlite_path)

    # -- helpers ----------------------------------------------------------

    def _to_summary(self, record: dict[str, Any], route: str) -> RunSummary:
        audit = _get_audit(record)
        annotations = record.get("annotations") or []
        if not isinstance(annotations, list):
            annotations = [annotations] if annotations else []
        entity_key = audit.get("entity_key") or _extract_entity_key(
            record.get("publish_key", "")
        )
        wide = self._wide.get(entity_key, {})
        if route == "formal":
            final_label = record.get("final_label")
            confidence = record.get("confidence_level")
        else:
            dr = record.get("decision_record") or {}
            final_label = dr.get("final_label") if isinstance(dr, dict) else None
            confidence = dr.get("confidence_level") if isinstance(dr, dict) else None
        if annotations:
            latest = annotations[-1]
            final_label = latest.get("annotated_label", final_label)

        return RunSummary(
            run_id=audit.get("run_id", ""),
            entity_key=entity_key,
            enterprise_name=record.get("enterprise_name") or wide.get("enterprise_name", entity_key),
            final_label=final_label,
            confidence_level=confidence,
            route=route,
            error_type=record.get("error_type"),
            timestamp=audit.get("timestamp"),
            annotations=annotations,
        )

    def _all_summaries(self) -> list[RunSummary]:
        items: list[RunSummary] = []
        for record in self._formal.values():
            items.append(self._to_summary(record, "formal"))
        for record in self._fallback.values():
            items.append(self._to_summary(record, "fallback"))
        return items

    # -- public API -------------------------------------------------------

    def list_runs(self, offset: int = 0, limit: int = 20) -> PaginatedRunList:
        if self._sqlite.enabled:
            items = [RunSummary(**item) for item in self._sqlite.list_runs(offset, limit)]
            total = sum(self._sqlite.count_by_route())
            return PaginatedRunList(items=items, total=total, offset=offset, limit=limit)
        all_items = self._all_summaries()
        total = len(all_items)
        page = all_items[offset : offset + limit]
        return PaginatedRunList(items=page, total=total, offset=offset, limit=limit)

    def get_run_detail(self, run_id: str) -> RunDetail | None:
        """Return the first record whose audit.run_id matches *run_id*."""
        if self._sqlite.enabled:
            detail = self._sqlite.get_run_detail(run_id)
            return RunDetail(**detail) if detail is not None else None
        for route, store in [("formal", self._formal), ("fallback", self._fallback)]:
            for record in store.values():
                audit = _get_audit(record)
                if audit.get("run_id") == run_id:
                    entity_key = audit.get("entity_key") or _extract_entity_key(
                        record.get("publish_key", "")
                    )
                    wide = self._wide.get(entity_key, {})
                    if route == "formal":
                        decision = record.get("model_decision_record") or {
                            k: record[k]
                            for k in (
                                "final_label",
                                "confidence_level",
                                "decision_reason",
                                "supporting_evidence",
                            )
                            if k in record
                        }
                    else:
                        decision = record.get("decision_record")

                    return RunDetail(
                        run_id=run_id,
                        entity_key=entity_key,
                        enterprise_name=record.get("enterprise_name") or wide.get("enterprise_name", entity_key),
                        business_scope=record.get("business_scope") or wide.get("business_scope", ""),
                        wide_row=wide,
                        static_profile=record.get("static_profile"),
                        dynamic_profile=record.get("dynamic_profile"),
                        decision_record=decision,
                        route=route,
                        error_type=record.get("error_type"),
                        audit=audit,
                        timing_ms=record.get("timing_ms"),
                        annotations=record.get("annotations") or [],
                    )
        return None

    def annotate(
        self,
        run_id: str,
        annotated_label: str,
        reviewer_notes: str = "",
        reviewer_name: str = "",
    ) -> AnnotationResponse | None:
        if self._sqlite.enabled:
            result = self._sqlite.annotate_run(run_id, annotated_label, reviewer_notes, reviewer_name)
            return AnnotationResponse(**result) if result is not None else None

        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        new_annotation = {
            "annotated_label": annotated_label,
            "reviewer_notes": reviewer_notes,
            "reviewer_name": reviewer_name,
            "created_at": timestamp,
        }

        for publish_key, record in list(self._formal.items()):
            audit = _get_audit(record)
            if audit.get("run_id") != run_id:
                continue
            annotations = record.get("annotations") or []
            if not isinstance(annotations, list):
                annotations = [annotations] if annotations else []
            if len(annotations) >= 3:
                return AnnotationResponse(
                    run_id=run_id, annotated_label=annotated_label,
                    status="max_reached", annotation_count=len(annotations),
                )
            annotations.append(new_annotation)
            record["annotations"] = annotations
            self._formal[publish_key] = record
            return AnnotationResponse(
                run_id=run_id, annotated_label=annotated_label,
                status="annotated", annotation_count=len(annotations),
            )

        for publish_key, record in list(self._fallback.items()):
            audit = _get_audit(record)
            if audit.get("run_id") != run_id:
                continue
            annotations = record.get("annotations") or []
            if not isinstance(annotations, list):
                annotations = [annotations] if annotations else []
            if len(annotations) >= 3:
                return AnnotationResponse(
                    run_id=run_id, annotated_label=annotated_label,
                    status="max_reached", annotation_count=len(annotations),
                )
            annotations.append(new_annotation)
            model_decision = record.get("decision_record") or {}
            formal_publish_key = (
                "::".join(publish_key.split("::")[:-1])
                if publish_key.endswith("::fallback")
                else publish_key
            )
            formal_record: dict[str, Any] = {
                **record,
                "publish_key": formal_publish_key,
                "final_label": annotated_label,
                "confidence_level": model_decision.get("confidence_level"),
                "decision_reason": f"Human review: {reviewer_notes}" if reviewer_notes else "Human review",
                "supporting_evidence": [],
                "audit": {
                    **audit,
                    "route": "formal",
                    "reviewed_at": timestamp,
                    "reviewer_notes": reviewer_notes,
                },
                "annotations": annotations,
                "model_decision_record": model_decision,
            }
            del self._fallback[publish_key]
            self._formal[formal_publish_key] = formal_record
            return AnnotationResponse(
                run_id=run_id, annotated_label=annotated_label,
                status="annotated", annotation_count=len(annotations),
            )

        return None

    def list_annotated_runs(self) -> list[dict[str, Any]]:
        if self._sqlite.enabled:
            return self._sqlite.list_annotated_runs()
        result: list[dict[str, Any]] = []
        for route, store in [("formal", self._formal), ("fallback", self._fallback)]:
            for record in store.values():
                annotations = record.get("annotations") or []
                if not isinstance(annotations, list) or not annotations:
                    continue
                audit = _get_audit(record)
                entity_key = audit.get("entity_key", "")
                wide = self._wide.get(entity_key, {})
                dr = record.get("model_decision_record") or record.get("decision_record") or {}
                model_label = dr.get("final_label") if isinstance(dr, dict) else None
                if not model_label:
                    model_label = record.get("final_label")
                latest = annotations[-1]
                result.append({
                    "run_id": audit.get("run_id", ""),
                    "entity_key": entity_key,
                    "enterprise_name": record.get("enterprise_name") or wide.get("enterprise_name", entity_key),
                    "model_label": model_label,
                    "annotated_label": latest.get("annotated_label"),
                    "annotation_count": len(annotations),
                    "latest_notes": latest.get("reviewer_notes", ""),
                    "latest_reviewer": latest.get("reviewer_name", ""),
                    "latest_time": latest.get("created_at", ""),
                    "annotations": annotations,
                })
        return result


# ---------------------------------------------------------------------------
# SearchService
# ---------------------------------------------------------------------------


class SearchService:
    """Substring search across entity_key and enterprise_name fields."""

    def __init__(
        self,
        formal_store: MutableMapping[str, dict[str, Any]],
        fallback_store: MutableMapping[str, dict[str, Any]],
        wide_row_index: dict[str, dict[str, Any]] | None = None,
        sqlite_path: Path | None = None,
    ) -> None:
        self._formal = formal_store
        self._fallback = fallback_store
        self._wide = wide_row_index or {}
        self._sqlite = _SqliteResultReader(sqlite_path)

    def search(self, query: str) -> list[SearchResult]:
        if not query:
            return []
        if self._sqlite.enabled:
            return [SearchResult(**item) for item in self._sqlite.search(query)]

        query_lower = query.lower()
        results: list[SearchResult] = []

        for route, store in [("formal", self._formal), ("fallback", self._fallback)]:
            for record in store.values():
                audit = _get_audit(record)
                entity_key = audit.get("entity_key") or _extract_entity_key(
                    record.get("publish_key", "")
                )
                wide = self._wide.get(entity_key, {})
                enterprise_name = record.get("enterprise_name") or wide.get("enterprise_name", entity_key)

                if (
                    query_lower in entity_key.lower()
                    or query_lower in enterprise_name.lower()
                ):
                    annotations = record.get("annotations") or []
                    if not isinstance(annotations, list):
                        annotations = [annotations] if annotations else []
                    if route == "formal":
                        final_label = record.get("final_label")
                    else:
                        dr = record.get("decision_record") or {}
                        final_label = (
                            dr.get("final_label") if isinstance(dr, dict) else None
                        )
                    if annotations:
                        final_label = annotations[-1].get("annotated_label", final_label)

                    results.append(
                        SearchResult(
                            entity_key=entity_key,
                            enterprise_name=enterprise_name,
                            final_label=final_label,
                            route=route,
                            run_id=audit.get("run_id", ""),
                        )
                    )

        return results


# ---------------------------------------------------------------------------
# FallbackService
# ---------------------------------------------------------------------------


class FallbackService:
    """List fallback records and handle review (migrate fallback → formal)."""

    def __init__(
        self,
        formal_store: MutableMapping[str, dict[str, Any]],
        fallback_store: MutableMapping[str, dict[str, Any]],
        wide_row_index: dict[str, dict[str, Any]] | None = None,
        sqlite_path: Path | None = None,
    ) -> None:
        self._formal = formal_store
        self._fallback = fallback_store
        self._wide = wide_row_index or {}
        self._sqlite = _SqliteResultReader(sqlite_path)

    def _to_fallback_record(self, record: dict[str, Any]) -> FallbackRecord:
        audit = _get_audit(record)
        entity_key = audit.get("entity_key") or _extract_entity_key(
            record.get("publish_key", "")
        )
        wide = self._wide.get(entity_key, {})
        dr = record.get("decision_record") or {}
        final_label = dr.get("final_label") if isinstance(dr, dict) else None
        confidence = dr.get("confidence_level") if isinstance(dr, dict) else None

        return FallbackRecord(
            entity_key=entity_key,
            enterprise_name=record.get("enterprise_name") or wide.get("enterprise_name", entity_key),
            final_label=final_label,
            confidence_level=confidence,
            error_type=record.get("error_type"),
            decision_record=record.get("decision_record"),
            audit=audit,
        )

    def list_fallbacks(
        self, offset: int = 0, limit: int = 20
    ) -> PaginatedFallbackList:
        if self._sqlite.enabled:
            items = [FallbackRecord(**item) for item in self._sqlite.list_fallbacks(offset, limit)]
            total = self._sqlite.count_by_route()[1]
            return PaginatedFallbackList(
                items=items, total=total, offset=offset, limit=limit
            )
        all_records = [
            self._to_fallback_record(r) for r in self._fallback.values()
        ]
        total = len(all_records)
        page = all_records[offset : offset + limit]
        return PaginatedFallbackList(
            items=page, total=total, offset=offset, limit=limit
        )

    def review(
        self,
        entity_key: str,
        approved_label: str,
        reviewer_notes: str = "",
    ) -> ReviewResponse | None:
        """Approve a fallback record: delete from fallback, write to formal."""
        if self._sqlite.enabled:
            run_id = self._sqlite.review_fallback(entity_key, approved_label, reviewer_notes)
            if run_id is None:
                return None
            return ReviewResponse(
                entity_key=entity_key,
                approved_label=approved_label,
                status="approved",
            )
        # Find the fallback record whose entity_key matches
        target_key: str | None = None
        target_record: dict[str, Any] | None = None

        for publish_key, record in self._fallback.items():
            audit = _get_audit(record)
            rec_entity = audit.get("entity_key") or _extract_entity_key(publish_key)
            if rec_entity == entity_key:
                target_key = publish_key
                target_record = record
                break

        if target_key is None or target_record is None:
            return None

        # Build a formal publish_key (strip trailing "::fallback")
        audit = _get_audit(target_record)
        parts = target_key.split("::")
        # fallback key: entity_key::fsv::tv::gv::fallback → formal: entity_key::fsv::tv::gv
        formal_publish_key = "::".join(parts[:-1]) if parts[-1] == "fallback" else target_key

        # Build the new formal record
        formal_record: dict[str, Any] = {
            **target_record,
            "final_label": approved_label,
            "confidence_level": "human_review",
            "decision_reason": f"Human review: {reviewer_notes}" if reviewer_notes else "Human review",
            "supporting_evidence": [],
            "audit": {
                **audit,
                "route": "formal",
                "reviewed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "reviewer_notes": reviewer_notes,
            },
        }

        # Delete from fallback, write to formal
        del self._fallback[target_key]
        self._formal[formal_publish_key] = formal_record

        return ReviewResponse(
            entity_key=entity_key,
            approved_label=approved_label,
            status="approved",
        )


# ---------------------------------------------------------------------------
# TaxonomyService
# ---------------------------------------------------------------------------


class TaxonomyService:
    """Thin wrapper around the existing ``load_taxonomy()`` function."""

    def get_taxonomy(self) -> TaxonomyResponse:
        cfg = load_taxonomy()
        labels = [
            TaxonomyLabelDTO(
                id=lbl.id,
                display_name=lbl.display_name,
                short_description=lbl.short_description,
                prompt_text=lbl.prompt_text,
                enabled=lbl.enabled,
            )
            for lbl in cfg.labels
        ]
        return TaxonomyResponse(version=cfg.version, labels=labels)


# ---------------------------------------------------------------------------
# SettingsService
# ---------------------------------------------------------------------------

# Mapping from SettingsUpdate field names → .env variable names
_SETTINGS_ENV_MAP: dict[str, str] = {
    "llm_model": "LLM_MODEL",
    "llm_timeout_sec": "LLM_TIMEOUT_SEC",
    "llm_max_retry": "LLM_MAX_RETRY",
    "worker_count": "WORKER_COUNT",
    "provider_rate_limit_per_minute": "PROVIDER_RATE_LIMIT_PER_MINUTE",
    "max_in_flight": "MAX_IN_FLIGHT",
}

# Defaults for runtime params that are not in load_llm_settings()
_RUNTIME_DEFAULTS: dict[str, int] = {
    "worker_count": 4,
    "provider_rate_limit_per_minute": 120,
    "max_in_flight": 8,
}

_ACCESS_SETTINGS_ENV_MAP: dict[str, str] = {
    "allowed_open_ids": "FEISHU_ALLOWED_OPEN_IDS",
    "allowed_emails": "FEISHU_ALLOWED_EMAILS",
    "admin_open_ids": "FEISHU_ADMIN_OPEN_IDS",
    "admin_emails": "FEISHU_ADMIN_EMAILS",
}


class SettingsService:
    """Read / write runtime configuration stored in the ``.env`` file."""

    def __init__(self, env_path: Path | None = None) -> None:
        self._env_path = env_path or _ENV_PATH
        self._uses_default_path = env_path is None

    # -- helpers ----------------------------------------------------------

    def _read_env(self) -> dict[str, str]:
        """Read env values from the configured ``.env`` file."""
        if self._uses_default_path:
            return dict(_load_env_values())
        # Custom path: read directly (used in tests)
        from dotenv import dotenv_values

        return {k: v for k, v in dotenv_values(self._env_path).items() if v is not None}

    # -- read -------------------------------------------------------------

    def get_settings(self) -> SettingsResponse:
        env = self._read_env()
        return SettingsResponse(
            llm_model=env.get("LLM_MODEL", "qwen3-max"),
            llm_timeout_sec=int(env.get("LLM_TIMEOUT_SEC", "30")),
            llm_max_retry=int(env.get("LLM_MAX_RETRY", "2")),
            worker_count=int(
                env.get("WORKER_COUNT", str(_RUNTIME_DEFAULTS["worker_count"]))
            ),
            provider_rate_limit_per_minute=int(
                env.get(
                    "PROVIDER_RATE_LIMIT_PER_MINUTE",
                    str(_RUNTIME_DEFAULTS["provider_rate_limit_per_minute"]),
                )
            ),
            max_in_flight=int(
                env.get(
                    "MAX_IN_FLIGHT", str(_RUNTIME_DEFAULTS["max_in_flight"])
                )
            ),
        )

    def get_access_settings(self) -> AccessSettingsResponse:
        env = self._read_env()
        return AccessSettingsResponse(
            allowed_open_ids=self._parse_csv_list(env.get("FEISHU_ALLOWED_OPEN_IDS", "")),
            allowed_emails=self._parse_csv_list(env.get("FEISHU_ALLOWED_EMAILS", ""), lowercase=True),
            admin_open_ids=self._parse_csv_list(env.get("FEISHU_ADMIN_OPEN_IDS", "")),
            admin_emails=self._parse_csv_list(env.get("FEISHU_ADMIN_EMAILS", ""), lowercase=True),
        )

    # -- write ------------------------------------------------------------

    def update_settings(self, update: SettingsUpdate) -> SettingsResponse:
        changes: dict[str, str] = {}
        for field_name, env_var in _SETTINGS_ENV_MAP.items():
            value = getattr(update, field_name, None)
            if value is not None:
                changes[env_var] = str(value)

        if changes:
            self._patch_env_file(changes)
            # Apply changes to current process env so subsequent reads pick
            # them up immediately.
            for env_var, val in changes.items():
                os.environ[env_var] = val
            # Clear the lru_cache so load_llm_settings() re-reads from .env.
            _load_env_values.cache_clear()
            load_llm_settings.cache_clear()

        return self.get_settings()

    def update_access_settings(self, update: AccessSettingsUpdate) -> AccessSettingsResponse:
        normalized = {
            "allowed_open_ids": self._normalize_items(update.allowed_open_ids),
            "allowed_emails": self._normalize_items(update.allowed_emails, lowercase=True),
            "admin_open_ids": self._normalize_items(update.admin_open_ids),
            "admin_emails": self._normalize_items(update.admin_emails, lowercase=True),
        }
        changes = {
            env_var: ",".join(normalized[field_name])
            for field_name, env_var in _ACCESS_SETTINGS_ENV_MAP.items()
        }
        self._patch_env_file(changes)
        _load_env_values.cache_clear()
        load_llm_settings.cache_clear()
        return AccessSettingsResponse(**normalized)

    # -- .env file manipulation -------------------------------------------

    def _patch_env_file(self, changes: dict[str, str]) -> None:
        """Update or append key=value pairs in the ``.env`` file."""
        if self._env_path.exists():
            lines = self._env_path.read_text(encoding="utf-8").splitlines()
        else:
            lines = []

        updated_keys: set[str] = set()
        new_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            # Skip empty / comment lines – keep them as-is
            if not stripped or stripped.startswith("#"):
                new_lines.append(line)
                continue

            key = stripped.split("=", 1)[0].strip()
            if key in changes:
                new_lines.append(f"{key}={changes[key]}")
                updated_keys.add(key)
            else:
                new_lines.append(line)

        # Append any keys that were not already present
        for key, val in changes.items():
            if key not in updated_keys:
                new_lines.append(f"{key}={val}")

        self._env_path.write_text(
            "\n".join(new_lines) + "\n", encoding="utf-8"
        )

    @staticmethod
    def _parse_csv_list(raw: str, lowercase: bool = False) -> list[str]:
        items = [item.strip() for item in raw.split(",") if item.strip()]
        if lowercase:
            return [item.lower() for item in items]
        return items

    @staticmethod
    def _normalize_items(items: list[str], lowercase: bool = False) -> list[str]:
        normalized: list[str] = []
        for item in items:
            value = item.strip()
            if not value:
                continue
            value = value.lower() if lowercase else value
            if value not in normalized:
                normalized.append(value)
        return normalized
