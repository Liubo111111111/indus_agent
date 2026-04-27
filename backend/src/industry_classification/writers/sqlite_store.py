from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from industry_classification.graph_state import GraphState


class SqliteResultStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                create table if not exists pipeline_runs (
                    run_id text primary key,
                    entity_key text not null,
                    route text not null,
                    error_type text,
                    feature_schema_version text not null,
                    taxonomy_version text not null,
                    graph_version text not null,
                    prompt_version_static text not null,
                    prompt_version_dynamic text not null,
                    prompt_version_final text not null,
                    model_version_static text not null,
                    model_version_dynamic text not null,
                    model_version_final text not null,
                    wide_row_json text not null,
                    static_profile_json text,
                    dynamic_profile_json text,
                    decision_record_json text,
                    timing_ms_json text,
                    created_at text not null default current_timestamp,
                    updated_at text not null default current_timestamp
                );

                create table if not exists inference_steps (
                    run_id text not null,
                    step_name text not null,
                    entity_key text not null,
                    prompt_version text not null,
                    model_version text not null,
                    payload_json text not null,
                    result_json text not null,
                    error_type text,
                    created_at text not null default current_timestamp,
                    updated_at text not null default current_timestamp,
                    primary key (run_id, step_name)
                );

                create table if not exists published_records (
                    publish_key text primary key,
                    run_id text not null,
                    entity_key text not null,
                    route text not null,
                    record_json text not null,
                    created_at text not null default current_timestamp,
                    updated_at text not null default current_timestamp
                );

                create index if not exists idx_inference_steps_run_id
                on inference_steps (run_id);

                create index if not exists idx_published_records_run_id
                on published_records (run_id);

                create table if not exists annotations (
                    id integer primary key autoincrement,
                    run_id text not null,
                    entity_key text not null,
                    annotated_label text not null,
                    reviewer_notes text not null default '',
                    reviewer_name text not null default '',
                    created_at text not null default current_timestamp
                );

                create index if not exists idx_annotations_run_id
                on annotations (run_id);

                create table if not exists backtest_runs (
                    backtest_run_id text primary key,
                    prompt_version_static text,
                    prompt_version_dynamic text,
                    prompt_version_final text,
                    pt_dates_json text,
                    dataset_size integer,
                    completed_count integer,
                    error_count integer,
                    accuracy real,
                    status text,
                    current_entity text,
                    created_at text not null default current_timestamp,
                    updated_at text not null default current_timestamp
                );

                create table if not exists backtest_results (
                    backtest_run_id text not null,
                    entity_key text not null,
                    enterprise_name text,
                    annotated_label text,
                    original_label text,
                    predicted_label text,
                    confidence_level text,
                    decision_reason text,
                    decision_record_json text,
                    error_type text,
                    created_at text not null default current_timestamp,
                    primary key (backtest_run_id, entity_key)
                );

                create index if not exists idx_backtest_results_run_id
                on backtest_results (backtest_run_id);

                create index if not exists idx_backtest_runs_status
                on backtest_runs (status);

                create table if not exists comparison_sessions (
                    session_id text primary key,
                    bizdate text,
                    prompt_version_static text,
                    prompt_version_dynamic text,
                    prompt_version_final text,
                    dataset_size integer,
                    completed_count integer,
                    error_count integer,
                    diff_count integer,
                    annotation_count integer,
                    consistency_rate real,
                    status text,
                    current_entity text,
                    created_at text not null default current_timestamp,
                    updated_at text not null default current_timestamp
                );

                create table if not exists comparison_results (
                    session_id text not null,
                    entity_key text not null,
                    enterprise_name text,
                    old_label text,
                    new_label text,
                    confidence_level text,
                    decision_reason text,
                    decision_record_json text,
                    error_type text,
                    wide_row_json text,
                    static_profile_json text,
                    dynamic_profile_json text,
                    created_at text not null default current_timestamp,
                    primary key (session_id, entity_key)
                );

                create table if not exists comparison_annotations (
                    annotation_id integer primary key autoincrement,
                    session_id text not null,
                    entity_key text not null,
                    human_label text,
                    reviewer_name text not null default '',
                    created_at text not null default current_timestamp
                );

                create index if not exists idx_comparison_results_session_id
                on comparison_results (session_id);

                create index if not exists idx_comparison_annotations_session_id
                on comparison_annotations (session_id);
                """
            )
            # 兼容已有数据库：尝试添加新列（已存在则忽略）
            for col in ("enterprise_name", "original_label", "wide_row_json", "static_profile_json", "dynamic_profile_json"):
                try:
                    self._conn.execute(
                        f"ALTER TABLE backtest_results ADD COLUMN {col} text"
                    )
                except sqlite3.OperationalError:
                    pass  # 列已存在
            self._conn.commit()

    @staticmethod
    def _dump_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)

    def upsert_run(self, state: GraphState) -> None:
        with self._lock:
            self._conn.execute(
                """
                insert into pipeline_runs (
                    run_id,
                    entity_key,
                    route,
                    error_type,
                    feature_schema_version,
                    taxonomy_version,
                    graph_version,
                    prompt_version_static,
                    prompt_version_dynamic,
                    prompt_version_final,
                    model_version_static,
                    model_version_dynamic,
                    model_version_final,
                    wide_row_json,
                    static_profile_json,
                    dynamic_profile_json,
                    decision_record_json,
                    timing_ms_json,
                    updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
                on conflict(run_id) do update set
                    entity_key = excluded.entity_key,
                    route = excluded.route,
                    error_type = excluded.error_type,
                    feature_schema_version = excluded.feature_schema_version,
                    taxonomy_version = excluded.taxonomy_version,
                    graph_version = excluded.graph_version,
                    prompt_version_static = excluded.prompt_version_static,
                    prompt_version_dynamic = excluded.prompt_version_dynamic,
                    prompt_version_final = excluded.prompt_version_final,
                    model_version_static = excluded.model_version_static,
                    model_version_dynamic = excluded.model_version_dynamic,
                    model_version_final = excluded.model_version_final,
                    wide_row_json = excluded.wide_row_json,
                    static_profile_json = excluded.static_profile_json,
                    dynamic_profile_json = excluded.dynamic_profile_json,
                    decision_record_json = excluded.decision_record_json,
                    timing_ms_json = excluded.timing_ms_json,
                    updated_at = current_timestamp
                """,
                (
                    state.run_id,
                    state.entity_key,
                    state.route,
                    state.error_type,
                    state.feature_schema_version,
                    state.taxonomy_version,
                    state.graph_version,
                    state.prompt_version_static,
                    state.prompt_version_dynamic,
                    state.prompt_version_final,
                    state.model_version_static,
                    state.model_version_dynamic,
                    state.model_version_final,
                    self._dump_json(state.wide_row.model_dump()),
                    self._dump_json(state.static_profile.model_dump()) if state.static_profile else None,
                    self._dump_json(state.dynamic_profile.model_dump()) if state.dynamic_profile else None,
                    self._dump_json(state.decision_record.model_dump()) if state.decision_record else None,
                    self._dump_json(state.timing_ms),
                ),
            )
            self._conn.commit()

    def upsert_step(
        self,
        run_id: str,
        entity_key: str,
        step_name: str,
        prompt_version: str,
        model_version: str,
        payload: dict[str, Any],
        result: dict[str, Any],
        error_type: str | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                insert into inference_steps (
                    run_id,
                    step_name,
                    entity_key,
                    prompt_version,
                    model_version,
                    payload_json,
                    result_json,
                    error_type,
                    updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
                on conflict(run_id, step_name) do update set
                    entity_key = excluded.entity_key,
                    prompt_version = excluded.prompt_version,
                    model_version = excluded.model_version,
                    payload_json = excluded.payload_json,
                    result_json = excluded.result_json,
                    error_type = excluded.error_type,
                    updated_at = current_timestamp
                """,
                (
                    run_id,
                    step_name,
                    entity_key,
                    prompt_version,
                    model_version,
                    self._dump_json(payload),
                    self._dump_json(result),
                    error_type,
                ),
            )
            self._conn.commit()

    def upsert_published_record(
        self,
        publish_key: str,
        run_id: str,
        entity_key: str,
        route: str,
        record: dict[str, Any],
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                insert into published_records (
                    publish_key,
                    run_id,
                    entity_key,
                    route,
                    record_json,
                    updated_at
                ) values (?, ?, ?, ?, ?, current_timestamp)
                on conflict(publish_key) do update set
                    run_id = excluded.run_id,
                    entity_key = excluded.entity_key,
                    route = excluded.route,
                    record_json = excluded.record_json,
                    updated_at = current_timestamp
                """,
                (
                    publish_key,
                    run_id,
                    entity_key,
                    route,
                    self._dump_json(record),
                ),
            )
            self._conn.commit()

    def add_annotation(
        self,
        run_id: str,
        entity_key: str,
        annotated_label: str,
        reviewer_notes: str,
        reviewer_name: str = "",
    ) -> None:
        with self._lock:
            count = self._conn.execute(
                "select count(*) from annotations where run_id = ?",
                (run_id,),
            ).fetchone()[0]
            if count >= 3:
                raise ValueError("max_3_annotations_per_run")
            self._conn.execute(
                """
                insert into annotations (
                    run_id,
                    entity_key,
                    annotated_label,
                    reviewer_notes,
                    reviewer_name
                ) values (?, ?, ?, ?, ?)
                """,
                (run_id, entity_key, annotated_label, reviewer_notes, reviewer_name),
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
