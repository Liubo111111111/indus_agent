"""回溯测试 API 路由模块。

提供 /api/backtest/* 下的所有端点，包括：
- 可用日期查询、标注数据集摘要
- 回溯测试启动/进度/报告
- 历史运行列表、对比、删除
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from industry_classification.api.backtest_schemas import (
    AccuracyReportResponse,
    AnnotationDatasetSummary,
    BacktestResultDetail,
    BacktestRunAccepted,
    BacktestRunRequest,
    BacktestRunSummary,
    BacktestStatusResponse,
    ComparisonResponse,
    FlipItem,
    LabelMetricsResponse,
    MisclassifiedItem,
)
from industry_classification.backtest_engine import BacktestConfig, BacktestEngine
from industry_classification.backtest_metrics import (
    build_accuracy_report,
    compare_runs as compare_runs_fn,
)
from industry_classification.writers.sqlite_store import SqliteResultStore

logger = logging.getLogger(__name__)

_PT_DATE_RE = re.compile(r"^\d{8}$")

# Prompt 节点名称列表
_PROMPT_NODES = ("static_profile", "dynamic_profile", "final_decision")

# prompts 目录路径
_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"


def _validate_pt_dates(pt_dates: list[str]) -> None:
    """校验 pt_dates 格式，不合法时抛出 HTTPException。"""
    if not pt_dates:
        raise HTTPException(status_code=400, detail="pt_dates 不能为空，请至少选择一个业务日期")
    for d in pt_dates:
        if not _PT_DATE_RE.match(d):
            raise HTTPException(
                status_code=422,
                detail=f"日期格式不合法: '{d}'，要求 yyyymmdd（8 位数字）",
            )


def _validate_prompt_versions(
    static: str, dynamic: str, final: str
) -> None:
    """校验 Prompt 版本文件是否存在，不存在时抛出 HTTPException 422。"""
    versions = {
        "static_profile": static,
        "dynamic_profile": dynamic,
        "final_decision": final,
    }
    for node, version in versions.items():
        yaml_path = _PROMPTS_DIR / f"{node}_{version}.yaml"
        if not yaml_path.exists():
            raise HTTPException(
                status_code=422,
                detail=f"Prompt 版本不存在: {node}_{version}.yaml",
            )


def _get_run_summary_row(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    """从 backtest_runs 表查询单条运行记录，返回 dict 或 None。"""
    row = conn.execute(
        "SELECT * FROM backtest_runs WHERE backtest_run_id = ?", (run_id,)
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def _row_to_run_summary(row: dict[str, Any]) -> BacktestRunSummary:
    """将 backtest_runs 行转换为 BacktestRunSummary。"""
    pt_dates: list[str] = []
    try:
        pt_dates = json.loads(row.get("pt_dates_json") or "[]")
    except (json.JSONDecodeError, TypeError):
        pass
    return BacktestRunSummary(
        backtest_run_id=row["backtest_run_id"],
        prompt_version_static=row["prompt_version_static"],
        prompt_version_dynamic=row["prompt_version_dynamic"],
        prompt_version_final=row["prompt_version_final"],
        pt_dates=pt_dates,
        dataset_size=row["dataset_size"],
        accuracy=row.get("accuracy"),
        status=row["status"],
        created_at=row["created_at"],
    )


def create_backtest_router(sqlite_path: Path) -> APIRouter:
    """创建并返回回溯测试 APIRouter，挂载到 /api/backtest 前缀。"""

    # 确保 backtest_runs / backtest_results 表存在（兼容已有数据库）
    _store = SqliteResultStore(sqlite_path)
    _store.close()

    router = APIRouter()

    # ------------------------------------------------------------------
    # GET /prompt-versions
    # ------------------------------------------------------------------
    @router.get("/prompt-versions")
    def get_prompt_versions() -> dict[str, list[str]]:
        """扫描 prompts 目录，返回各节点可用的版本列表。"""
        result: dict[str, list[str]] = {}
        for node in _PROMPT_NODES:
            versions: list[str] = []
            for p in sorted(_PROMPTS_DIR.glob(f"{node}_*.yaml")):
                # 从文件名提取版本号，如 final_decision_v2.yaml → v2
                stem = p.stem  # e.g. "final_decision_v2"
                prefix = f"{node}_"
                if stem.startswith(prefix):
                    ver = stem[len(prefix):]
                    if ver:
                        versions.append(ver)
            result[node] = versions
        return result

    # ------------------------------------------------------------------
    # GET /prompt-versions
    # ------------------------------------------------------------------
    @router.get("/prompt-versions")
    def get_prompt_versions() -> dict:
        """返回各节点的可用 Prompt 版本配置。"""
        import yaml
        config_path = Path(__file__).resolve().parents[1] / "prompt_versions.yaml"
        if not config_path.exists():
            return {"nodes": {}}
        with config_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    # ------------------------------------------------------------------
    # GET /available-dates
    # ------------------------------------------------------------------
    @router.get("/available-dates")
    def get_available_dates() -> list[dict]:
        """返回所有可用业务日期及标注数量。"""
        return BacktestEngine.get_available_dates(sqlite_path)

    # ------------------------------------------------------------------
    # GET /annotations
    # ------------------------------------------------------------------
    @router.get("/annotations", response_model=AnnotationDatasetSummary)
    def get_annotations(
        pt_dates: str = Query(..., description="逗号分隔的业务日期列表，如 20250101,20250115"),
    ) -> AnnotationDatasetSummary:
        """按 pt_dates 查询标注数据集摘要。"""
        dates = [d.strip() for d in pt_dates.split(",") if d.strip()]
        _validate_pt_dates(dates)
        summary = BacktestEngine.get_annotation_summary(sqlite_path, dates)
        return AnnotationDatasetSummary(**summary)

    # ------------------------------------------------------------------
    # GET /baseline-report
    # ------------------------------------------------------------------
    @router.get("/baseline-report")
    def get_baseline_report(
        pt_dates: str = Query(..., description="逗号分隔的业务日期列表"),
    ) -> dict:
        """返回原模型基线报告（不需要跑回溯）。"""
        dates = [d.strip() for d in pt_dates.split(",") if d.strip()]
        _validate_pt_dates(dates)
        return BacktestEngine.get_baseline_report(sqlite_path, dates)

    # ------------------------------------------------------------------
    # GET /original-detail/{run_id}
    # ------------------------------------------------------------------
    @router.get("/original-detail/{run_id}")
    def get_original_detail(run_id: str) -> dict:
        """查询原始 pipeline_run 详情（搜索所有分区数据库）。"""
        from industry_classification.backtest_engine import _discover_all_sqlite_paths, _query_all_dbs

        all_paths = _discover_all_sqlite_paths(sqlite_path)
        rows = _query_all_dbs(
            all_paths,
            """
            SELECT run_id, entity_key, route, error_type,
                   wide_row_json, static_profile_json,
                   dynamic_profile_json, decision_record_json,
                   created_at
            FROM pipeline_runs WHERE run_id = ?
            """,
            (run_id,),
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"运行记录不存在: {run_id}")
        row = rows[0]
        # 解析 JSON 字段
        def _parse(val: str | None) -> dict | None:
            if not val:
                return None
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return None
        return {
            "run_id": row["run_id"],
            "entity_key": row["entity_key"],
            "enterprise_name": (_parse(row.get("wide_row_json")) or {}).get("enterprise_name", ""),
            "route": row["route"],
            "error_type": row.get("error_type"),
            "wide_row": _parse(row.get("wide_row_json")),
            "static_profile": _parse(row.get("static_profile_json")),
            "dynamic_profile": _parse(row.get("dynamic_profile_json")),
            "decision_record": _parse(row.get("decision_record_json")),
            "created_at": row.get("created_at"),
        }

    # ------------------------------------------------------------------
    # POST /run
    # ------------------------------------------------------------------
    @router.post("/run", response_model=BacktestRunAccepted, status_code=202)
    def start_backtest_run(req: BacktestRunRequest) -> BacktestRunAccepted:
        """启动异步回溯测试，返回 202 + backtest_run_id。"""
        _validate_pt_dates(req.pt_dates)
        _validate_prompt_versions(
            req.prompt_version_static,
            req.prompt_version_dynamic,
            req.prompt_version_final,
        )

        backtest_run_id = str(uuid4())
        config = BacktestConfig(
            backtest_run_id=backtest_run_id,
            pt_dates=req.pt_dates,
            prompt_version_static=req.prompt_version_static,
            prompt_version_dynamic=req.prompt_version_dynamic,
            prompt_version_final=req.prompt_version_final,
        )

        engine = BacktestEngine(sqlite_path, config)

        # 先加载数据集获取 dataset_size
        dataset = engine.load_annotation_dataset()
        dataset_size = len(dataset)

        # 在后台线程中执行回溯
        def _run_backtest() -> None:
            try:
                engine.run()
            except Exception:
                logger.exception("回溯运行异常 backtest_run_id=%s", backtest_run_id)

        thread = threading.Thread(
            target=_run_backtest, daemon=True, name=f"backtest-{backtest_run_id[:8]}"
        )
        thread.start()

        return BacktestRunAccepted(
            backtest_run_id=backtest_run_id,
            message="效果评估已启动",
            dataset_size=dataset_size,
        )

    # ------------------------------------------------------------------
    # GET /run/{backtest_run_id}/status
    # ------------------------------------------------------------------
    @router.get("/run/{backtest_run_id}/status", response_model=BacktestStatusResponse)
    def get_run_status(backtest_run_id: str) -> BacktestStatusResponse:
        """查询回溯运行进度。"""
        conn = sqlite3.connect(str(sqlite_path))
        conn.row_factory = sqlite3.Row
        try:
            row = _get_run_summary_row(conn, backtest_run_id)
            if row is None:
                raise HTTPException(status_code=404, detail=f"运行记录不存在: {backtest_run_id}")
            return BacktestStatusResponse(
                backtest_run_id=row["backtest_run_id"],
                status=row["status"],
                dataset_size=row["dataset_size"],
                completed_count=row["completed_count"],
                error_count=row["error_count"],
                current_entity=row.get("current_entity"),
                accuracy=row.get("accuracy"),
            )
        finally:
            conn.close()


    # ------------------------------------------------------------------
    # GET /run/{backtest_run_id}/report
    # ------------------------------------------------------------------
    @router.get("/run/{backtest_run_id}/report", response_model=AccuracyReportResponse)
    def get_run_report(backtest_run_id: str) -> AccuracyReportResponse:
        """获取准确率报告。运行未完成返回 409。"""
        conn = sqlite3.connect(str(sqlite_path))
        conn.row_factory = sqlite3.Row
        try:
            run_row = _get_run_summary_row(conn, backtest_run_id)
            if run_row is None:
                raise HTTPException(status_code=404, detail=f"运行记录不存在: {backtest_run_id}")
            if run_row["status"] != "done":
                raise HTTPException(
                    status_code=409,
                    detail=f"运行尚未完成，当前状态: {run_row['status']}",
                )

            # 查询所有回溯结果
            rows = conn.execute(
                "SELECT * FROM backtest_results WHERE backtest_run_id = ?",
                (backtest_run_id,),
            ).fetchall()

            results: list[dict[str, Any]] = []
            for r in rows:
                results.append({
                    "entity_key": r["entity_key"],
                    "enterprise_name": r["enterprise_name"] or "",
                    "annotated_label": r["annotated_label"],
                    "original_label": r["original_label"],
                    "predicted_label": r["predicted_label"],
                    "confidence_level": r["confidence_level"],
                    "error_type": r["error_type"],
                })

            report = build_accuracy_report(results)

            # 计算原模型指标（original_label vs annotated_label）
            # 构造一个"伪结果列表"，把 original_label 当作 predicted_label
            original_results = [
                {
                    **r,
                    "predicted_label": r.get("original_label"),
                }
                for r in results
                if r.get("original_label")
            ]
            original_report = build_accuracy_report(original_results) if original_results else None
            original_accuracy: float | None = original_report.accuracy if original_report else None
            original_correct_count = original_report.correct if original_report else 0

            # 构建逐条明细列表
            details = [
                BacktestResultDetail(
                    entity_key=r["entity_key"],
                    enterprise_name=r.get("enterprise_name") or "",
                    original_label=r.get("original_label"),
                    annotated_label=r["annotated_label"] or "",
                    predicted_label=r.get("predicted_label"),
                    confidence_level=r.get("confidence_level"),
                    error_type=r.get("error_type"),
                    match=bool(
                        r.get("predicted_label")
                        and r["predicted_label"] == r["annotated_label"]
                        and not r.get("error_type")
                    ),
                )
                for r in results
            ]

            return AccuracyReportResponse(
                backtest_run_id=backtest_run_id,
                accuracy=report.accuracy,
                original_accuracy=original_accuracy,
                total=report.total,
                correct=report.correct,
                error_count=report.error_count,
                label_metrics=[
                    LabelMetricsResponse(
                        label=m.label,
                        precision=m.precision,
                        recall=m.recall,
                        f1=m.f1,
                        support=m.support,
                    )
                    for m in report.label_metrics
                ],
                confusion_matrix=report.confusion_matrix,
                misclassified=[
                    MisclassifiedItem(
                        entity_key=item["entity_key"],
                        enterprise_name=item.get("enterprise_name", ""),
                        annotated_label=item["annotated_label"],
                        predicted_label=item["predicted_label"],
                        confidence_level=item.get("confidence_level"),
                    )
                    for item in report.misclassified
                ],
                details=details,
            )
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # GET /runs
    # ------------------------------------------------------------------
    @router.get("/runs", response_model=list[BacktestRunSummary])
    def list_runs() -> list[BacktestRunSummary]:
        """返回历史运行列表，按创建时间倒序。"""
        conn = sqlite3.connect(str(sqlite_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM backtest_runs ORDER BY created_at DESC"
            ).fetchall()
            return [_row_to_run_summary(dict(r)) for r in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # GET /compare
    # ------------------------------------------------------------------
    @router.get("/compare", response_model=ComparisonResponse)
    def compare_runs(
        run_a: str = Query(..., description="第一次运行 ID"),
        run_b: str = Query(..., description="第二次运行 ID"),
    ) -> ComparisonResponse:
        """两次运行对比。"""
        conn = sqlite3.connect(str(sqlite_path))
        conn.row_factory = sqlite3.Row
        try:
            row_a = _get_run_summary_row(conn, run_a)
            row_b = _get_run_summary_row(conn, run_b)
            if row_a is None:
                raise HTTPException(status_code=404, detail=f"运行记录不存在: {run_a}")
            if row_b is None:
                raise HTTPException(status_code=404, detail=f"运行记录不存在: {run_b}")

            # 查询两次运行的结果
            def _load_results(rid: str) -> list[dict[str, Any]]:
                rows = conn.execute(
                    "SELECT * FROM backtest_results WHERE backtest_run_id = ?",
                    (rid,),
                ).fetchall()
                return [
                    {
                        "entity_key": r["entity_key"],
                        "enterprise_name": "",
                        "annotated_label": r["annotated_label"],
                        "predicted_label": r["predicted_label"],
                        "confidence_level": r["confidence_level"],
                        "error_type": r["error_type"],
                    }
                    for r in rows
                ]

            results_a = _load_results(run_a)
            results_b = _load_results(run_b)

            comparison = compare_runs_fn(results_a, results_b)

            return ComparisonResponse(
                run_a=_row_to_run_summary(row_a),
                run_b=_row_to_run_summary(row_b),
                accuracy_diff=comparison.accuracy_diff,
                label_metrics_diff=comparison.label_metrics_diff,
                flips=[
                    FlipItem(
                        entity_key=f.entity_key,
                        enterprise_name=f.enterprise_name,
                        annotated_label=f.annotated_label,
                        label_a=f.label_a,
                        label_b=f.label_b,
                        direction=f.direction,
                    )
                    for f in comparison.flips
                ],
                confusion_matrix_a=comparison.confusion_matrix_a,
                confusion_matrix_b=comparison.confusion_matrix_b,
            )
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # GET /run/{backtest_run_id}/result/{entity_key}
    # ------------------------------------------------------------------
    @router.get("/run/{backtest_run_id}/result/{entity_key}")
    def get_result_detail(backtest_run_id: str, entity_key: str) -> dict:
        """获取单条回溯结果详情，返回格式兼容 RunDetail。"""
        conn = sqlite3.connect(str(sqlite_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM backtest_results WHERE backtest_run_id = ? AND entity_key = ?",
                (backtest_run_id, entity_key),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail=f"结果不存在: {entity_key}")
            result = dict(row)

            def _parse(val: str | None) -> dict | None:
                if not val:
                    return None
                try:
                    return json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    return None

            wide_row = _parse(result.get("wide_row_json")) or {}
            static_profile = _parse(result.get("static_profile_json"))
            dynamic_profile = _parse(result.get("dynamic_profile_json"))
            decision_record = _parse(result.get("decision_record_json"))

            # 返回格式兼容 RunDetail，供 DetailView 直接使用
            return {
                "run_id": f"bt-{backtest_run_id}-{entity_key}",
                "entity_key": result["entity_key"],
                "enterprise_name": result.get("enterprise_name") or wide_row.get("enterprise_name", ""),
                "business_scope": wide_row.get("business_scope", ""),
                "wide_row": wide_row,
                "static_profile": static_profile,
                "dynamic_profile": dynamic_profile,
                "decision_record": decision_record,
                "route": "backtest",
                "error_type": result.get("error_type"),
                "audit": {},
                "timing_ms": None,
                "annotations": [],
            }
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # DELETE /run/{backtest_run_id}
    # ------------------------------------------------------------------
    @router.delete("/run/{backtest_run_id}")
    def delete_run(backtest_run_id: str) -> dict[str, str]:
        """删除运行记录（级联删除 backtest_runs + backtest_results）。"""
        deleted = BacktestEngine.delete_backtest_run(sqlite_path, backtest_run_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"运行记录不存在: {backtest_run_id}")
        return {"message": f"已删除运行记录: {backtest_run_id}"}

    return router
