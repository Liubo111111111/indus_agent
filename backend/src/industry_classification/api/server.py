"""FastAPI application entry point.

Start with::

    uvicorn industry_classification.api.server:app --reload --port 8000
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from industry_classification.api.auth import AuthAuditStore, FeishuAuthService, load_feishu_auth_settings
from industry_classification.api.routes import create_router
from industry_classification.api.services import (
    FallbackService,
    RunService,
    SearchService,
    SettingsService,
    StatsService,
    TaxonomyService,
)
from industry_classification.writers.jsonl_store import JsonlKeyedStore

logger = logging.getLogger(__name__)

# Default output directory – three levels up from this file
_OUTPUT_DIR = Path(__file__).resolve().parents[3] / "output"

# In-memory task status tracker
_task_store: dict[str, dict[str, Any]] = {}


def _load_wide_row_index(output_dir: Path) -> dict[str, dict[str, Any]]:
    """Build a social_credit_code → row dict from available input files."""
    index: dict[str, dict[str, Any]] = {}
    # Try JSON files in output dir and output/data/
    for search_dir in [output_dir, output_dir / "data"]:
        if not search_dir.exists():
            continue
        for f in search_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for row in data:
                        key = row.get("social_credit_code", "")
                        if key:
                            index[key] = row
            except Exception:
                continue
    # Also try JSONL files
    for search_dir in [output_dir, output_dir / "data"]:
        if not search_dir.exists():
            continue
        for f in search_dir.glob("*.jsonl"):
            if f.name in ("formal_output.jsonl", "fallback_output.jsonl"):
                continue
            try:
                for line in f.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    key = row.get("social_credit_code", "")
                    if key:
                        index[key] = row
            except Exception:
                continue
    logger.info("Loaded %d wide rows into index", len(index))
    return index


def create_app(output_dir: Path | None = None) -> FastAPI:
    """Build a fully-wired :class:`FastAPI` application."""

    out = output_dir or _OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)

    # -- data stores ------------------------------------------------------
    formal_store = JsonlKeyedStore(out / "formal_output.jsonl")
    fallback_store = JsonlKeyedStore(out / "fallback_output.jsonl")
    sqlite_path = out / "pipeline_results.sqlite3"
    wide_index = _load_wide_row_index(out)

    # -- services ---------------------------------------------------------
    stats_svc = StatsService(formal_store, fallback_store, sqlite_path=sqlite_path)
    run_svc = RunService(formal_store, fallback_store, wide_row_index=wide_index, sqlite_path=sqlite_path)
    search_svc = SearchService(formal_store, fallback_store, wide_row_index=wide_index, sqlite_path=sqlite_path)
    fallback_svc = FallbackService(formal_store, fallback_store, wide_row_index=wide_index, sqlite_path=sqlite_path)
    taxonomy_svc = TaxonomyService()
    settings_svc = SettingsService()
    auth_settings = load_feishu_auth_settings()
    auth_svc = FeishuAuthService(auth_settings, audit_store=AuthAuditStore(sqlite_path))

    # -- batch trigger (background thread) --------------------------------
    def batch_trigger_fn(req, task_id: str) -> None:
        def _run() -> None:
            logger.info("Batch task %s started (pt=%s, input_path=%s, workers=%d)", task_id, req.pt, req.input_path, req.worker_count)
            logger.info("Batch task %s finished", task_id)
        thread = threading.Thread(target=_run, daemon=True, name=f"batch-{task_id}")
        thread.start()

    def classify_single_fn(query: str, task_id: str, pt: str = "") -> None:
        """单条分类：查询 ODPS 宽表 → 跑分类流水线，带阶段状态追踪。"""
        import time as _time

        # Default pt to yesterday if not provided
        if not pt:
            pt = "20260402"

        stages = [
            {"name": "ODPS 数据查询", "status": "pending", "elapsed_ms": None, "message": ""},
            {"name": "静态画像", "status": "pending", "elapsed_ms": None, "message": ""},
            {"name": "动态画像", "status": "pending", "elapsed_ms": None, "message": ""},
            {"name": "最终裁决", "status": "pending", "elapsed_ms": None, "message": ""},
        ]
        _task_store[task_id] = {"task_id": task_id, "status": "running", "stages": stages, "result_run_id": None, "error": None}

        def _update(idx: int, status: str, elapsed: float | None = None, msg: str = "") -> None:
            stages[idx]["status"] = status
            if elapsed is not None:
                stages[idx]["elapsed_ms"] = round(elapsed, 1)
            stages[idx]["message"] = msg

        def _run() -> None:
            try:
                # Stage 0: ODPS query
                _update(0, "running")
                t0 = _time.perf_counter()
                try:
                    from industry_classification.data_fetcher import _get_odps_client, _WIDE_TABLE, _COLUMNS, _csv_row_to_wide_row
                    odps = _get_odps_client()
                    columns_str = ", ".join(_COLUMNS)
                    sql = (
                        f"SELECT {columns_str} FROM {_WIDE_TABLE} "
                        f"WHERE pt = '{pt}' AND ("
                        f"social_credit_code = '{query}' "
                        f"OR enterprise_name LIKE '%{query}%') "
                        f"LIMIT 1;"
                    )
                    rows = []
                    with odps.execute_sql(sql).open_reader() as reader:
                        for record in reader:
                            row = {col.name: record.get_by_name(col.name) for col in record._columns}
                            rows.append(row)
                    if not rows:
                        _update(0, "error", (_time.perf_counter() - t0) * 1000, f"未找到企业: {query}")
                        _task_store[task_id]["status"] = "error"
                        _task_store[task_id]["error"] = f"未找到企业: {query}"
                        return
                    wide_row = _csv_row_to_wide_row(rows[0])
                    wide_index[wide_row["social_credit_code"]] = wide_row
                    _update(0, "done", (_time.perf_counter() - t0) * 1000, wide_row.get("enterprise_name", ""))
                except Exception as exc:
                    _update(0, "error", (_time.perf_counter() - t0) * 1000, str(exc))
                    _task_store[task_id]["status"] = "error"
                    _task_store[task_id]["error"] = str(exc)
                    return

                # Stages 1-3: run pipeline
                run_id = f"single-{task_id}"
                from industry_classification.llm.client import HttpLLMClient
                from industry_classification.main import run_once
                llm_client = HttpLLMClient()
                try:
                    # Mark stages as running sequentially
                    for i in range(1, 4):
                        _update(i, "running")
                    state = run_once(
                        row_dict=wide_row,
                        run_id=run_id,
                        client=llm_client,
                        formal_store=formal_store,
                        fallback_store=fallback_store,
                        sqlite_path=sqlite_path,
                    )
                    # Extract timing from state
                    timing = state.timing_ms or {}
                    _update(1, "done", timing.get("static_profile"), "完成")
                    _update(2, "done", timing.get("dynamic_profile"), "完成")
                    _update(3, "done", timing.get("final_decision"),
                            f"{state.decision_record.final_label if state.decision_record else '未知'}")
                    _task_store[task_id]["status"] = "done"
                    _task_store[task_id]["result_run_id"] = run_id
                finally:
                    llm_client.close()
            except Exception as exc:
                logger.error("Single classify %s failed: %s", task_id, exc)
                _task_store[task_id]["status"] = "error"
                _task_store[task_id]["error"] = str(exc)

        thread = threading.Thread(target=_run, daemon=True, name=f"classify-{task_id}")
        thread.start()

    def classify_csv_fn(csv_path: str, task_id: str, total_rows: int) -> None:
        """批量分类：从 CSV 读取信用代码列表 → 查询 ODPS → 跑分类流水线。"""
        def _run() -> None:
            try:
                import csv as csv_mod
                from datetime import datetime, timedelta
                logger.info("CSV classify %s: reading %d rows from %s", task_id, total_rows, csv_path)

                # Default pt to yesterday
                default_pt = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

                # 读取 CSV 中的信用代码
                codes: list[str] = []
                with open(csv_path, "r", encoding="utf-8") as f:
                    reader = csv_mod.DictReader(f)
                    for row in reader:
                        code = row.get("social_credit_code", "").strip()
                        if code:
                            codes.append(code)

                if not codes:
                    logger.warning("CSV classify %s: no valid social_credit_code found", task_id)
                    return

                logger.info("CSV classify %s: querying ODPS for %d enterprises", task_id, len(codes))
                from industry_classification.data_fetcher import _get_odps_client, _WIDE_TABLE, _COLUMNS, _csv_row_to_wide_row

                odps = _get_odps_client()
                columns_str = ", ".join(_COLUMNS)
                codes_str = ", ".join(f"'{c}'" for c in codes)
                sql = (
                    f"SELECT {columns_str} FROM {_WIDE_TABLE} "
                    f"WHERE pt = '{default_pt}' AND social_credit_code IN ({codes_str});"
                )
                rows = []
                with odps.execute_sql(sql).open_reader() as reader:
                    for record in reader:
                        row = {col.name: record.get_by_name(col.name) for col in record._columns}
                        rows.append(row)

                if not rows:
                    logger.warning("CSV classify %s: no ODPS data found", task_id)
                    return

                # 转换并跑分类
                from industry_classification.llm.client import HttpLLMClient
                from industry_classification.main import run_once

                llm_client = HttpLLMClient()
                try:
                    for idx, raw_row in enumerate(rows, 1):
                        wide_row = _csv_row_to_wide_row(raw_row)
                        wide_index[wide_row["social_credit_code"]] = wide_row
                        run_once(
                            row_dict=wide_row,
                            run_id=f"csv-{task_id}-{idx}",
                            client=llm_client,
                            formal_store=formal_store,
                            fallback_store=fallback_store,
                            sqlite_path=sqlite_path,
                        )
                        logger.info("CSV classify %s: %d/%d done", task_id, idx, len(rows))
                finally:
                    llm_client.close()

                logger.info("CSV classify %s: completed %d enterprises", task_id, len(rows))
            except Exception as exc:
                logger.error("CSV classify %s failed: %s", task_id, exc)

        thread = threading.Thread(target=_run, daemon=True, name=f"csv-{task_id}")
        thread.start()

    # -- router -----------------------------------------------------------
    router = create_router(
        stats_service=stats_svc,
        run_service=run_svc,
        search_service=search_svc,
        fallback_service=fallback_svc,
        taxonomy_service=taxonomy_svc,
        settings_service=settings_svc,
        auth_service=auth_svc,
        batch_trigger_fn=batch_trigger_fn,
        classify_single_fn=classify_single_fn,
        classify_csv_fn=classify_csv_fn,
    )

    # -- app --------------------------------------------------------------
    app = FastAPI(title="Industry Classification API", version="1.0.0")
    allow_origins = ["http://localhost:3000"]
    parsed_frontend = urlsplit(auth_settings.frontend_base_url)
    frontend_origin = ""
    if parsed_frontend.scheme and parsed_frontend.netloc:
        frontend_origin = f"{parsed_frontend.scheme}://{parsed_frontend.netloc}"
    if frontend_origin and frontend_origin not in allow_origins:
        allow_origins.append(frontend_origin)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")

    return app


app = create_app()
