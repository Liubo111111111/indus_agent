"""新旧标签对比评估 API 路由模块。

提供 /api/comparison/* 下的所有端点，包括：
- 创建对比会话（启动异步 ODPS 拉取 + LLM 重跑）
- 查询运行进度
- 差异指标分析
- 分页记录查询（支持标注状态筛选）
- 提交人工标注
- 生成评估报告
- 历史会话列表
- 删除会话
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from industry_classification.api.comparison_schemas import (
    AnnotateRequest,
    ComparisonAccepted,
    ComparisonReport,
    ComparisonStatusResponse,
    CreateComparisonRequest,
    DiffAnalysis,
    RecordsResponse,
    SessionSummary,
)
from industry_classification.comparison_engine import ComparisonConfig, ComparisonEngine

logger = logging.getLogger(__name__)


def create_comparison_router(sqlite_path: Path) -> APIRouter:
    """创建并返回对比评估 APIRouter，挂载到 /api/comparison 前缀。"""

    router = APIRouter()

    # ------------------------------------------------------------------
    # POST /session - 创建对比会话，启动异步 ODPS 拉取 + LLM 重跑
    # ------------------------------------------------------------------
    @router.post("/session", response_model=ComparisonAccepted, status_code=202)
    def create_session(req: CreateComparisonRequest) -> ComparisonAccepted:
        """创建对比评估会话，在后台线程中启动数据拉取和 LLM 重跑。"""
        session_id = str(uuid4())

        config = ComparisonConfig(
            session_id=session_id,
            bizdate=req.bizdate,
            max_rows=req.max_rows,
            lookback_days=req.lookback_days,
            prompt_version_static=req.prompt_version_static,
            prompt_version_dynamic=req.prompt_version_dynamic,
            prompt_version_final=req.prompt_version_final,
        )

        engine = ComparisonEngine(sqlite_path, config)

        # 先创建 session 记录，前端可以立即轮询到状态
        engine._create_session_record(dataset_size=0)

        def _run_comparison() -> None:
            try:
                engine.run()
            except Exception:
                logger.exception("对比运行异常 session_id=%s", session_id)
                # 确保异常时 session 状态更新为 error
                try:
                    conn = sqlite3.connect(str(sqlite_path))
                    conn.execute(
                        "UPDATE comparison_sessions SET status = 'error', current_entity = '运行异常' WHERE session_id = ? AND status = 'running'",
                        (session_id,),
                    )
                    conn.commit()
                    conn.close()
                except Exception:
                    pass

        thread = threading.Thread(
            target=_run_comparison, daemon=True, name=f"comparison-{session_id[:8]}"
        )
        thread.start()

        return ComparisonAccepted(
            session_id=session_id,
            message="对比评估已启动",
        )


    # ------------------------------------------------------------------
    # GET /session/{session_id}/status - 查询运行进度
    # ------------------------------------------------------------------
    @router.get("/session/{session_id}/status", response_model=ComparisonStatusResponse)
    def get_session_status(session_id: str) -> ComparisonStatusResponse:
        """查询对比评估运行进度。"""
        conn = sqlite3.connect(str(sqlite_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM comparison_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
            return ComparisonStatusResponse(
                session_id=row["session_id"],
                status=row["status"],
                dataset_size=row["dataset_size"],
                completed_count=row["completed_count"],
                error_count=row["error_count"],
                diff_count=row["diff_count"],
                annotation_count=row["annotation_count"],
                current_entity=row["current_entity"],
                consistency_rate=row["consistency_rate"],
            )
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # GET /session/{session_id}/diff - 差异指标分析
    # ------------------------------------------------------------------
    @router.get("/session/{session_id}/diff", response_model=DiffAnalysis)
    def get_diff_analysis(session_id: str) -> DiffAnalysis:
        """获取差异指标分析结果。运行未完成返回 409。"""
        # 先检查会话状态
        conn = sqlite3.connect(str(sqlite_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT status FROM comparison_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
            if row["status"] == "running":
                raise HTTPException(
                    status_code=409,
                    detail="LLM 分类流水线尚未完成",
                )
        finally:
            conn.close()

        config = ComparisonConfig(session_id=session_id, bizdate="")
        engine = ComparisonEngine(sqlite_path, config)
        try:
            result = engine.get_diff_analysis(session_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return DiffAnalysis(**result)

    # ------------------------------------------------------------------
    # GET /session/{session_id}/records - 分页记录查询
    # ------------------------------------------------------------------
    @router.get("/session/{session_id}/records", response_model=RecordsResponse)
    def get_records(
        session_id: str,
        status: str = Query(default="all", description="筛选状态: all / annotated / unannotated"),
        page: int = Query(default=1, ge=1, description="页码"),
        page_size: int = Query(default=20, ge=1, le=100, description="每页记录数"),
    ) -> RecordsResponse:
        """分页获取差异记录，支持按标注状态筛选。"""
        # 检查会话是否存在
        conn = sqlite3.connect(str(sqlite_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT session_id FROM comparison_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
        finally:
            conn.close()

        config = ComparisonConfig(session_id=session_id, bizdate="")
        engine = ComparisonEngine(sqlite_path, config)
        result = engine.get_records(session_id, status, page, page_size)
        return RecordsResponse(**result)

    # ------------------------------------------------------------------
    # GET /session/{session_id}/record/{entity_key} - 单条记录详情
    # ------------------------------------------------------------------
    @router.get("/session/{session_id}/record/{entity_key}")
    def get_record_detail(session_id: str, entity_key: str) -> dict:
        """获取单条对比记录的完整详情（含宽表数据、画像、决策记录、全部标注历史）。"""
        conn = sqlite3.connect(str(sqlite_path))
        conn.row_factory = sqlite3.Row
        try:
            # 获取对比结果
            row = conn.execute(
                "SELECT * FROM comparison_results WHERE session_id = ? AND entity_key = ?",
                (session_id, entity_key),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail=f"记录不存在: {entity_key}")
            result = dict(row)

            # 获取全部标注历史（按时间正序）
            annotations = conn.execute(
                """
                SELECT human_label, reviewer_name, created_at
                FROM comparison_annotations
                WHERE session_id = ? AND entity_key = ?
                ORDER BY annotation_id ASC
                """,
                (session_id, entity_key),
            ).fetchall()
            result["annotations"] = [dict(a) for a in annotations]

            # 最新标注
            if annotations:
                latest = annotations[-1]
                result["human_label"] = latest["human_label"]
                result["annotation_reviewer"] = latest["reviewer_name"]
            else:
                result["human_label"] = None
                result["annotation_reviewer"] = None

            return result
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # POST /session/{session_id}/annotate - 提交标注
    # ------------------------------------------------------------------
    @router.post("/session/{session_id}/annotate")
    def annotate_records(session_id: str, req: AnnotateRequest) -> dict:
        """提交人工标注（单条或批量）。"""
        # 检查会话是否存在
        conn = sqlite3.connect(str(sqlite_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT session_id FROM comparison_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
        finally:
            conn.close()

        config = ComparisonConfig(session_id=session_id, bizdate="")
        engine = ComparisonEngine(sqlite_path, config)
        try:
            engine.annotate(session_id, req.annotations, req.reviewer_name)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return {"message": "标注成功", "count": len(req.annotations)}

    # ------------------------------------------------------------------
    # GET /session/{session_id}/report - 生成评估报告
    # ------------------------------------------------------------------
    @router.get("/session/{session_id}/report", response_model=ComparisonReport)
    def get_report(session_id: str) -> ComparisonReport:
        """生成完整评估报告。无标注时返回 409。"""
        # 检查会话是否存在
        conn = sqlite3.connect(str(sqlite_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT status FROM comparison_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
            if row["status"] == "running":
                raise HTTPException(
                    status_code=409,
                    detail="LLM 分类流水线尚未完成",
                )
        finally:
            conn.close()

        config = ComparisonConfig(session_id=session_id, bizdate="")
        engine = ComparisonEngine(sqlite_path, config)
        try:
            result = engine.generate_report(session_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return ComparisonReport(**result)

    # ------------------------------------------------------------------
    # GET /sessions - 历史会话列表
    # ------------------------------------------------------------------
    @router.get("/sessions", response_model=list[SessionSummary])
    def list_sessions() -> list[SessionSummary]:
        """返回历史会话列表，按创建时间倒序。"""
        conn = sqlite3.connect(str(sqlite_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM comparison_sessions ORDER BY created_at DESC"
            ).fetchall()
            return [
                SessionSummary(
                    session_id=row["session_id"],
                    bizdate=row["bizdate"],
                    prompt_version_static=row["prompt_version_static"],
                    prompt_version_dynamic=row["prompt_version_dynamic"],
                    prompt_version_final=row["prompt_version_final"],
                    dataset_size=row["dataset_size"],
                    completed_count=row["completed_count"],
                    diff_count=row["diff_count"],
                    annotation_count=row["annotation_count"],
                    consistency_rate=row["consistency_rate"],
                    status=row["status"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]
        except sqlite3.OperationalError:
            # 表尚未创建时返回空列表
            return []
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # DELETE /session/{session_id} - 删除会话
    # ------------------------------------------------------------------
    @router.delete("/session/{session_id}")
    def delete_session(session_id: str) -> dict:
        """删除会话及其关联数据（级联删除）。"""
        config = ComparisonConfig(session_id=session_id, bizdate="")
        engine = ComparisonEngine(sqlite_path, config)
        deleted = engine.delete_session(session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
        return {"message": f"已删除会话: {session_id}"}

    return router
