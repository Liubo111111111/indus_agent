"""回溯测试引擎模块。

复用现有分类流水线 run_once，对标注数据集逐条重新运行分类，
收集预测结果并写入 backtest_runs / backtest_results 表。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from industry_classification.backtest_metrics import calculate_accuracy
from industry_classification.llm.client import HttpLLMClient
from industry_classification.main import RateLimitedLLMClient, run_once
from industry_classification.rate_limit import MinuteRateLimiter
from industry_classification.settings import load_llm_settings, load_prompt_version_defaults
from industry_classification.writers.sqlite_store import SqliteResultStore

logger = logging.getLogger(__name__)

# 从配置文件加载默认 Prompt 版本
_PROMPT_DEFAULTS = load_prompt_version_defaults()


@dataclass
class BacktestConfig:
    """回溯测试运行配置。"""

    backtest_run_id: str
    pt_dates: list[str] = field(default_factory=list)
    prompt_version_static: str = field(default_factory=lambda: _PROMPT_DEFAULTS.get("static_profile", "v1"))
    prompt_version_dynamic: str = field(default_factory=lambda: _PROMPT_DEFAULTS.get("dynamic_profile", "v1"))
    prompt_version_final: str = field(default_factory=lambda: _PROMPT_DEFAULTS.get("final_decision", "v2"))
    worker_count: int = 4
    provider_rate_limit_per_minute: int = 120
    max_in_flight: int = 8


def _discover_all_sqlite_paths(sqlite_path: Path) -> list[Path]:
    """发现所有分区目录下的 pipeline_results.sqlite3 文件。

    sqlite_path 通常指向 output/_legacy/pipeline_results.sqlite3，
    其父目录的父目录（output/）下可能有多个分区子目录，
    每个都包含独立的 pipeline_results.sqlite3。
    """
    base_output_dir = sqlite_path.parent.parent  # output/
    all_paths: list[Path] = []
    if not base_output_dir.is_dir():
        # 回退：只用传入的路径
        if sqlite_path.exists():
            return [sqlite_path]
        return []

    for child in base_output_dir.iterdir():
        if not child.is_dir():
            continue
        candidate = child / "pipeline_results.sqlite3"
        if candidate.exists():
            all_paths.append(candidate)

    # 确保传入的路径也在列表中
    if sqlite_path.exists() and sqlite_path not in all_paths:
        all_paths.append(sqlite_path)

    return sorted(all_paths)


def _query_all_dbs(
    all_paths: list[Path],
    sql: str,
    params: tuple | list = (),
) -> list[dict]:
    """对多个 SQLite 数据库执行相同查询，合并结果。

    跳过没有 annotations 表的数据库。
    """
    results: list[dict] = []
    for db_path in all_paths:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            # 检查是否有 annotations 表
            has_table = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='annotations'"
            ).fetchone()[0]
            if not has_table:
                continue
            rows = conn.execute(sql, params).fetchall()
            results.extend(dict(r) for r in rows)
        except sqlite3.OperationalError:
            continue
        finally:
            conn.close()
    return results


class BacktestEngine:
    """回溯测试引擎，加载标注数据并逐条调用 run_once 收集结果。"""

    def __init__(self, sqlite_path: Path, config: BacktestConfig) -> None:
        self.sqlite_path = sqlite_path
        self.config = config
        self._lock = threading.Lock()

    def load_annotation_dataset(self) -> list[dict]:
        """从所有分区 SQLite 加载指定多个业务日期内的标注数据集。

        扫描 output/ 下所有分区的 pipeline_results.sqlite3，
        联合查询 annotations + pipeline_runs，按 pt_dates 过滤
        （使用 pipeline_runs.created_at 提取 yyyymmdd 格式日期），
        同一企业取最新标注去重。

        返回包含 entity_key、enterprise_name、wide_row、annotated_label 的记录列表。
        """
        if not self.config.pt_dates:
            return []

        all_paths = _discover_all_sqlite_paths(self.sqlite_path)
        if not all_paths:
            return []

        placeholders = ",".join("?" for _ in self.config.pt_dates)
        sql = f"""
            SELECT
                a.entity_key,
                a.annotated_label,
                a.created_at AS annotation_created_at,
                p.wide_row_json,
                p.decision_record_json,
                p.created_at AS run_created_at
            FROM annotations a
            JOIN pipeline_runs p ON a.run_id = p.run_id
            WHERE strftime('%Y%m%d', p.created_at) IN ({placeholders})
            ORDER BY a.entity_key, a.created_at DESC
        """

        all_rows = _query_all_dbs(all_paths, sql, self.config.pt_dates)

        # 按 annotation_created_at 降序排列，确保去重时保留最新标注
        all_rows.sort(
            key=lambda r: (r["entity_key"], r.get("annotation_created_at", "")),
            reverse=True,
        )

        # 按 entity_key 去重，保留最新标注
        seen: dict[str, dict] = {}
        for row in all_rows:
            entity_key = row["entity_key"]
            if entity_key in seen:
                continue

            try:
                wide_row = json.loads(row["wide_row_json"])
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    "wide_row_json 解析失败，跳过 entity_key=%s", entity_key
                )
                continue

            enterprise_name = wide_row.get("enterprise_name", "")

            # 提取原模型标签
            original_label = None
            dr_json = row.get("decision_record_json")
            if dr_json:
                try:
                    dr = json.loads(dr_json)
                    original_label = dr.get("final_label")
                except (json.JSONDecodeError, TypeError):
                    pass

            seen[entity_key] = {
                "entity_key": entity_key,
                "enterprise_name": enterprise_name,
                "wide_row": wide_row,
                "annotated_label": row["annotated_label"],
                "original_label": original_label,
            }

        return list(seen.values())

    def _create_backtest_run_record(self, dataset_size: int) -> None:
        """在 backtest_runs 表中创建运行记录。"""
        conn = sqlite3.connect(str(self.sqlite_path))
        try:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                INSERT INTO backtest_runs (
                    backtest_run_id, prompt_version_static, prompt_version_dynamic,
                    prompt_version_final, pt_dates_json, dataset_size,
                    completed_count, error_count, accuracy, status,
                    current_entity, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, NULL, 'running', NULL, ?, ?)
                """,
                (
                    self.config.backtest_run_id,
                    self.config.prompt_version_static,
                    self.config.prompt_version_dynamic,
                    self.config.prompt_version_final,
                    json.dumps(self.config.pt_dates, ensure_ascii=False),
                    dataset_size,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _update_backtest_progress(
        self,
        completed_count: int,
        error_count: int,
        current_entity: str | None,
    ) -> None:
        """更新 backtest_runs 表中的进度信息。"""
        conn = sqlite3.connect(str(self.sqlite_path))
        try:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                UPDATE backtest_runs
                SET completed_count = ?, error_count = ?, current_entity = ?,
                    updated_at = ?
                WHERE backtest_run_id = ?
                """,
                (
                    completed_count,
                    error_count,
                    current_entity,
                    now,
                    self.config.backtest_run_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _finalize_backtest_run(
        self, status: str, accuracy: float | None
    ) -> None:
        """完成回溯运行，更新最终状态和准确率。"""
        conn = sqlite3.connect(str(self.sqlite_path))
        try:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                UPDATE backtest_runs
                SET status = ?, accuracy = ?, current_entity = NULL,
                    updated_at = ?
                WHERE backtest_run_id = ?
                """,
                (status, accuracy, now, self.config.backtest_run_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _insert_backtest_result(self, result: dict[str, Any]) -> None:
        """将单条回溯结果写入 backtest_results 表。"""
        conn = sqlite3.connect(str(self.sqlite_path))
        try:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                INSERT OR REPLACE INTO backtest_results (
                    backtest_run_id, entity_key, enterprise_name,
                    annotated_label, original_label, predicted_label,
                    confidence_level, decision_reason,
                    decision_record_json, error_type,
                    wide_row_json, static_profile_json, dynamic_profile_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.config.backtest_run_id,
                    result["entity_key"],
                    result.get("enterprise_name"),
                    result["annotated_label"],
                    result.get("original_label"),
                    result.get("predicted_label"),
                    result.get("confidence_level"),
                    result.get("decision_reason"),
                    result.get("decision_record_json"),
                    result.get("error_type"),
                    result.get("wide_row_json"),
                    result.get("static_profile_json"),
                    result.get("dynamic_profile_json"),
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def run(
        self,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> None:
        """执行回溯测试，并行调用 run_once 并记录结果。

        使用 ThreadPoolExecutor 并行处理，并发度由 config.max_in_flight 控制。
        速率限制由 RateLimitedLLMClient + MinuteRateLimiter 保证。

        Args:
            on_progress: 可选回调 (completed, total, current_entity)
        """
        dataset = self.load_annotation_dataset()
        total = len(dataset)

        # 创建运行记录
        self._create_backtest_run_record(dataset_size=total)

        if total == 0:
            self._finalize_backtest_run(status="done", accuracy=None)
            return

        # 构建 LLM 客户端 + 速率限制（所有线程共享同一个限流器）
        llm_settings = load_llm_settings()
        http_client = HttpLLMClient(settings=llm_settings)
        limiter = MinuteRateLimiter(self.config.provider_rate_limit_per_minute)
        client = RateLimitedLLMClient(http_client, limiter)

        completed_count = 0
        error_count = 0
        all_results: list[dict] = []
        progress_lock = threading.Lock()

        def _classify_one(record: dict) -> dict[str, Any]:
            """单条企业的回溯分类（在工作线程中执行）。"""
            entity_key = record["entity_key"]
            enterprise_name = record["enterprise_name"]
            wide_row = record["wide_row"]

            run_id = f"bt-{self.config.backtest_run_id}-{entity_key}"
            result_record: dict[str, Any] = {
                "entity_key": entity_key,
                "enterprise_name": enterprise_name,
                "annotated_label": record["annotated_label"],
                "original_label": record.get("original_label"),
                "predicted_label": None,
                "confidence_level": None,
                "decision_reason": None,
                "decision_record_json": None,
                "error_type": None,
            }

            try:
                state = run_once(
                    row_dict=wide_row,
                    run_id=run_id,
                    client=client,
                    formal_store={},
                    fallback_store={},
                    sqlite_store=None,
                    sqlite_path=None,
                    prompt_version_static=self.config.prompt_version_static,
                    prompt_version_dynamic=self.config.prompt_version_dynamic,
                    prompt_version_final=self.config.prompt_version_final,
                )

                if state.decision_record:
                    dr = state.decision_record
                    result_record["predicted_label"] = dr.final_label
                    result_record["confidence_level"] = dr.confidence_level
                    result_record["decision_reason"] = dr.decision_reason
                    result_record["decision_record_json"] = json.dumps(
                        dr.model_dump(), ensure_ascii=False
                    )
                elif state.error_type:
                    result_record["error_type"] = state.error_type
                else:
                    result_record["error_type"] = "no_decision_record"

                # 保存完整画像数据，供明细查看
                result_record["wide_row_json"] = json.dumps(
                    wide_row, ensure_ascii=False, default=str
                )
                if state.static_profile:
                    result_record["static_profile_json"] = json.dumps(
                        state.static_profile.model_dump(), ensure_ascii=False
                    )
                if state.dynamic_profile:
                    result_record["dynamic_profile_json"] = json.dumps(
                        state.dynamic_profile.model_dump(), ensure_ascii=False
                    )

            except Exception as exc:
                error_type = type(exc).__name__
                logger.warning(
                    "回溯单条失败 entity_key=%s error=%s: %s",
                    entity_key, error_type, exc,
                )
                result_record["error_type"] = error_type

            return result_record

        max_workers = min(self.config.max_in_flight, total)

        try:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {
                    pool.submit(_classify_one, record): record
                    for record in dataset
                }

                for future in as_completed(futures):
                    record = futures[future]
                    result_record = future.result()

                    # 写入结果
                    self._insert_backtest_result(result_record)

                    with progress_lock:
                        all_results.append(result_record)
                        if result_record.get("error_type"):
                            error_count += 1
                        completed_count += 1

                        # 更新进度
                        self._update_backtest_progress(
                            completed_count, error_count,
                            record["enterprise_name"],
                        )
                        if on_progress:
                            on_progress(
                                completed_count, total,
                                record["enterprise_name"],
                            )

            # 计算准确率并完成运行
            accuracy = calculate_accuracy(all_results)
            self._update_backtest_progress(completed_count, error_count, None)
            self._finalize_backtest_run(status="done", accuracy=accuracy)

        except Exception as exc:
            logger.error("回溯运行整体异常: %s", exc)
            self._finalize_backtest_run(status="error", accuracy=None)
            raise
        finally:
            if hasattr(http_client, "close"):
                http_client.close()

    @staticmethod
    def get_available_dates(sqlite_path: Path) -> list[dict]:
        """查询所有分区数据库中存在标注数据的业务日期及数量。

        扫描 output/ 下所有分区的 pipeline_results.sqlite3。
        返回 [{"date": "20250101", "count": 15}, ...] 格式列表。
        """
        all_paths = _discover_all_sqlite_paths(sqlite_path)
        if not all_paths:
            return []

        sql = """
            SELECT strftime('%Y%m%d', p.created_at) AS pt_date,
                   COUNT(*) AS cnt
            FROM annotations a
            JOIN pipeline_runs p ON a.run_id = p.run_id
            GROUP BY pt_date
        """

        all_rows = _query_all_dbs(all_paths, sql)

        # 合并来自不同数据库的同一日期的计数
        date_counts: dict[str, int] = {}
        for row in all_rows:
            d = row["pt_date"]
            date_counts[d] = date_counts.get(d, 0) + row["cnt"]

        return [
            {"date": d, "count": c}
            for d, c in sorted(date_counts.items())
        ]

    @staticmethod
    def get_annotation_summary(
        sqlite_path: Path, pt_dates: list[str]
    ) -> dict[str, Any]:
        """按 pt_dates 返回数据集摘要（扫描所有分区数据库）。

        返回 {"total": N, "label_distribution": {...}, "entities": [...]}。
        """
        if not pt_dates:
            return {"total": 0, "label_distribution": {}, "entities": []}

        all_paths = _discover_all_sqlite_paths(sqlite_path)
        if not all_paths:
            return {"total": 0, "label_distribution": {}, "entities": []}

        placeholders = ",".join("?" for _ in pt_dates)
        sql = f"""
            SELECT
                a.entity_key,
                a.annotated_label,
                a.created_at AS annotation_created_at,
                p.wide_row_json
            FROM annotations a
            JOIN pipeline_runs p ON a.run_id = p.run_id
            WHERE strftime('%Y%m%d', p.created_at) IN ({placeholders})
            ORDER BY a.entity_key, a.created_at DESC
        """

        all_rows = _query_all_dbs(all_paths, sql, pt_dates)

        # 按 annotation_created_at 降序排列
        all_rows.sort(
            key=lambda r: (r["entity_key"], r.get("annotation_created_at", "")),
            reverse=True,
        )

        # 去重：同一 entity_key 取最新标注
        seen: dict[str, dict] = {}
        for row in all_rows:
            ek = row["entity_key"]
            if ek in seen:
                continue
            try:
                wide_row = json.loads(row["wide_row_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            seen[ek] = {
                "entity_key": ek,
                "enterprise_name": wide_row.get("enterprise_name", ""),
                "annotated_label": row["annotated_label"],
            }

        records = list(seen.values())
        label_dist: dict[str, int] = {}
        for rec in records:
            lbl = rec["annotated_label"]
            label_dist[lbl] = label_dist.get(lbl, 0) + 1

        entities = [
            {
                "entity_key": r["entity_key"],
                "enterprise_name": r["enterprise_name"],
                "annotated_label": r["annotated_label"],
            }
            for r in records
        ]

        return {
            "total": len(records),
            "label_distribution": label_dist,
            "entities": entities,
        }

    @staticmethod
    def get_baseline_report(
        sqlite_path: Path, pt_dates: list[str]
    ) -> dict[str, Any]:
        """计算原模型的基线报告（original_label vs annotated_label）。

        不需要跑回溯，直接从 pipeline_runs.decision_record_json 提取原模型标签，
        与 annotations 中的人工标注对比，计算准确率、各标签指标、混淆矩阵和明细。
        """
        from industry_classification.backtest_metrics import (
            build_accuracy_report,
        )

        if not pt_dates:
            return {"total": 0, "accuracy": 0.0, "correct": 0, "label_metrics": [],
                    "confusion_matrix": {}, "details": []}

        all_paths = _discover_all_sqlite_paths(sqlite_path)
        if not all_paths:
            return {"total": 0, "accuracy": 0.0, "correct": 0, "label_metrics": [],
                    "confusion_matrix": {}, "details": []}

        placeholders = ",".join("?" for _ in pt_dates)
        sql = f"""
            SELECT
                a.entity_key,
                a.annotated_label,
                a.created_at AS annotation_created_at,
                a.run_id,
                p.wide_row_json,
                p.decision_record_json,
                strftime('%Y%m%d', p.created_at) AS pt
            FROM annotations a
            JOIN pipeline_runs p ON a.run_id = p.run_id
            WHERE strftime('%Y%m%d', p.created_at) IN ({placeholders})
            ORDER BY a.entity_key, a.created_at DESC
        """

        all_rows = _query_all_dbs(all_paths, sql, pt_dates)
        all_rows.sort(
            key=lambda r: (r["entity_key"], r.get("annotation_created_at", "")),
            reverse=True,
        )

        # 去重 + 提取原模型标签
        seen: dict[str, dict] = {}
        for row in all_rows:
            ek = row["entity_key"]
            if ek in seen:
                continue
            try:
                wide_row = json.loads(row["wide_row_json"])
            except (json.JSONDecodeError, TypeError):
                continue

            original_label = None
            confidence_level = None
            dr_json = row.get("decision_record_json")
            if dr_json:
                try:
                    dr = json.loads(dr_json)
                    original_label = dr.get("final_label")
                    confidence_level = dr.get("confidence_level")
                except (json.JSONDecodeError, TypeError):
                    pass

            seen[ek] = {
                "entity_key": ek,
                "enterprise_name": wide_row.get("enterprise_name", ""),
                "annotated_label": row["annotated_label"],
                "predicted_label": original_label,
                "confidence_level": confidence_level,
                "error_type": None if original_label else "no_original_label",
                "run_id": row.get("run_id"),
                "pt": row.get("pt"),
            }

        records = list(seen.values())
        report = build_accuracy_report(records)

        details = [
            {
                "entity_key": r["entity_key"],
                "enterprise_name": r["enterprise_name"],
                "annotated_label": r["annotated_label"],
                "original_label": r["predicted_label"],
                "confidence_level": r.get("confidence_level"),
                "run_id": r.get("run_id"),
                "pt": r.get("pt"),
                "match": bool(
                    r["predicted_label"]
                    and r["predicted_label"] == r["annotated_label"]
                    and not r.get("error_type")
                ),
            }
            for r in records
        ]

        return {
            "total": report.total,
            "accuracy": report.accuracy,
            "correct": report.correct,
            "error_count": report.error_count,
            "label_metrics": [
                {
                    "label": m.label,
                    "precision": m.precision,
                    "recall": m.recall,
                    "f1": m.f1,
                    "support": m.support,
                }
                for m in report.label_metrics
            ],
            "confusion_matrix": report.confusion_matrix,
            "details": details,
        }

    @staticmethod
    def delete_backtest_run(sqlite_path: Path, backtest_run_id: str) -> bool:
        """级联删除 backtest_runs 和 backtest_results 中的关联数据。

        返回 True 表示找到并删除了记录，False 表示未找到。
        """
        conn = sqlite3.connect(str(sqlite_path))
        try:
            cursor = conn.execute(
                "DELETE FROM backtest_results WHERE backtest_run_id = ?",
                (backtest_run_id,),
            )
            cursor2 = conn.execute(
                "DELETE FROM backtest_runs WHERE backtest_run_id = ?",
                (backtest_run_id,),
            )
            conn.commit()
            return cursor2.rowcount > 0
        finally:
            conn.close()
