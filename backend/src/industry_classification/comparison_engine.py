"""新旧标签对比评估引擎模块。

对比"老标签"（旧系统 indus_enterprise_goss_label 表中的历史分类结果）
和"新标签"（当前 LLM 分类流水线重新运行的预测结果），
通过四阶段流程完成评估：数据拉取+LLM重跑 → 差异指标分析 → 人工标注差异 → 准确率评估。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from industry_classification.llm.client import HttpLLMClient
from industry_classification.main import RateLimitedLLMClient, run_once
from industry_classification.rate_limit import MinuteRateLimiter
from industry_classification.settings import load_llm_settings

logger = logging.getLogger(__name__)


# ODPS SQL：宽表 JOIN 老标签表
COMPARISON_SQL_TEMPLATE = """\
SELECT w.user_id, w.social_credit_code, w.enterprise_name, w.business_scope,
       w.total_job_post_cnt_90d, w.distinct_job_name_cnt_90d, w.top_job_names_json,
       w.jobs_recent_20_json, w.latest_publish_time, w.latest_publish_job_names_json,
       w.authentication_time,
       l.label as old_label
FROM yuapo_dev.enterprise_industry_wide_table w
INNER JOIN yuapo_dev.indus_enterprise_goss_label l
  ON w.user_id = l.user_id
  AND w.social_credit_code = l.social_credit_code
  AND l.pt = '${bizdate}'
WHERE w.pt = '${bizdate}'
  AND w.latest_publish_time >= '${publish_start}'
  AND w.latest_publish_time < '${publish_end}'
"""

# 老标签映射表：旧体系标签 → 新体系标签
# 1. 去掉 "_老" 后缀
# 2. 特殊映射（旧体系类目名 → 新体系类目名）
_OLD_LABEL_SPECIAL_MAP: dict[str, str] = {
    "汽车租赁": "货运物流",
}


def normalize_old_label(raw_label: str) -> str:
    """将老标签映射到新体系标签名。

    规则：
    1. 去掉 "_老" 后缀
    2. 查特殊映射表，命中则替换
    """
    label = raw_label.removesuffix("_老")
    return _OLD_LABEL_SPECIAL_MAP.get(label, label)


@dataclass
class ComparisonConfig:
    """对比评估运行配置。"""

    session_id: str
    bizdate: str                              # ODPS 分区日期 yyyymmdd
    max_rows: int | None = None               # 最大拉取条数
    lookback_days: int = 1                    # 回溯天数，publish_start = bizdate - lookback_days
    prompt_version_static: str = "v1"
    prompt_version_dynamic: str = "v1"
    prompt_version_final: str = "v3"
    worker_count: int = 4
    provider_rate_limit_per_minute: int = 120
    max_in_flight: int = 8


class ComparisonEngine:
    """新旧标签对比评估引擎。

    流程：
    1. 从 ODPS 拉取数据（宽表 JOIN 老标签表），每条记录带 old_label
    2. 用当前 LLM 分类流水线（run_once）重新跑一遍，得到 new_label
    3. 存储结果到 SQLite，供后续差异分析和人工标注使用
    """

    def __init__(self, sqlite_path: Path, config: ComparisonConfig) -> None:
        self.sqlite_path = sqlite_path
        self.config = config
        self._lock = threading.Lock()

    def fetch_comparison_dataset(self) -> list[dict]:
        """从 ODPS 拉取宽表 JOIN 老标签表的数据。

        使用 data_fetcher.fetch_by_sql，返回的每条记录包含:
        - wide_row 字段（WideRow 兼容格式）
        - old_label 字段（老标签）
        - entity_key（user_id::social_credit_code）
        """
        from industry_classification.data_fetcher import (
            _csv_row_to_wide_row,
            _execute_with_retry,
            _get_odps_client,
        )
        from industry_classification.sql_template import render_sql

        # 渲染 SQL 模板
        # 根据 lookback_days 计算 publish_start（yyyymmdd 格式）
        from datetime import datetime, timedelta

        biz_dt = datetime.strptime(self.config.bizdate, "%Y%m%d")
        publish_start_dt = biz_dt - timedelta(days=self.config.lookback_days)
        publish_start = publish_start_dt.strftime("%Y%m%d")

        sql = render_sql(
            template=COMPARISON_SQL_TEMPLATE,
            bizdate=self.config.bizdate,
            max_rows=self.config.max_rows,
            publish_start=publish_start,
        )

        # 执行 SQL 获取原始记录
        odps = _get_odps_client()
        raw_rows = _execute_with_retry(odps, sql, max_retries=3, retry_delay=5)

        logger.info("ODPS 返回 %d 条原始记录", len(raw_rows))

        # 分区：有效记录 vs 跳过记录
        valid_records: list[dict] = []
        skipped_count = 0

        for row in raw_rows:
            # 统一转为字符串以兼容 _csv_row_to_wide_row
            str_row = {k: str(v) if v is not None else "" for k, v in row.items()}

            user_id = str_row.get("user_id", "").strip()
            social_credit_code = str_row.get("social_credit_code", "").strip()
            old_label = normalize_old_label(str_row.get("old_label", "").strip())

            # 构建 entity_key
            entity_key = f"{user_id}::{social_credit_code}" if user_id and social_credit_code else ""

            # 有效性检查：需要非空 entity_key 和 old_label
            if not entity_key or not old_label:
                skipped_count += 1
                continue

            # 转换为 WideRow 格式（不含 old_label）
            wide_row = _csv_row_to_wide_row(str_row)

            valid_records.append({
                "entity_key": entity_key,
                "wide_row": wide_row,
                "old_label": old_label,
                "enterprise_name": wide_row.get("enterprise_name", ""),
            })

        if skipped_count > 0:
            logger.info("跳过 %d 条无效记录（缺少 entity_key 或 old_label）", skipped_count)

        # 按 entity_key 去重，保留最后一条
        seen: dict[str, dict] = {}
        for record in valid_records:
            seen[record["entity_key"]] = record

        deduped_records = list(seen.values())

        if len(deduped_records) < len(valid_records):
            logger.info(
                "去重：%d → %d 条（移除 %d 条重复 entity_key）",
                len(valid_records),
                len(deduped_records),
                len(valid_records) - len(deduped_records),
            )

        if not deduped_records:
            raise ValueError("无有效数据记录")

        logger.info("最终有效记录 %d 条", len(deduped_records))
        return deduped_records

    def _create_session_record(self, dataset_size: int) -> None:
        """在 comparison_sessions 表中创建或更新运行记录。"""
        conn = sqlite3.connect(str(self.sqlite_path))
        try:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                INSERT OR REPLACE INTO comparison_sessions (
                    session_id, bizdate, prompt_version_static, prompt_version_dynamic,
                    prompt_version_final, dataset_size, completed_count, error_count,
                    diff_count, annotation_count, consistency_rate, status,
                    current_entity, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, 0, NULL, 'running', NULL, ?, ?)
                """,
                (
                    self.config.session_id,
                    self.config.bizdate,
                    self.config.prompt_version_static,
                    self.config.prompt_version_dynamic,
                    self.config.prompt_version_final,
                    dataset_size,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _update_session_progress(
        self,
        completed_count: int,
        error_count: int,
        current_entity: str | None,
    ) -> None:
        """更新 comparison_sessions 表中的进度信息。"""
        conn = sqlite3.connect(str(self.sqlite_path))
        try:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                UPDATE comparison_sessions
                SET completed_count = ?, error_count = ?, current_entity = ?,
                    updated_at = ?
                WHERE session_id = ?
                """,
                (
                    completed_count,
                    error_count,
                    current_entity,
                    now,
                    self.config.session_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _finalize_session(
        self, status: str, diff_count: int, dataset_size: int
    ) -> None:
        """完成对比运行，更新最终状态、diff_count 和 consistency_rate。"""
        consistency_rate = (
            1.0 - diff_count / dataset_size if dataset_size > 0 else None
        )
        conn = sqlite3.connect(str(self.sqlite_path))
        try:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                UPDATE comparison_sessions
                SET status = ?, diff_count = ?, consistency_rate = ?,
                    current_entity = NULL, updated_at = ?
                WHERE session_id = ?
                """,
                (status, diff_count, consistency_rate, now, self.config.session_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _auto_annotate_consistent_records(self) -> None:
        """自动为一致记录（old_label == new_label）插入标注，视为已标注。"""
        conn = sqlite3.connect(str(self.sqlite_path))
        try:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            # 对所有 old_label == new_label 且无错误的记录，自动插入标注
            conn.execute(
                """
                INSERT INTO comparison_annotations
                    (session_id, entity_key, human_label, reviewer_name, created_at)
                SELECT session_id, entity_key, new_label, '系统自动', ?
                FROM comparison_results
                WHERE session_id = ?
                  AND new_label IS NOT NULL
                  AND error_type IS NULL
                  AND old_label = new_label
                  AND entity_key NOT IN (
                    SELECT entity_key FROM comparison_annotations WHERE session_id = ?
                  )
                """,
                (now, self.config.session_id, self.config.session_id),
            )
            # 更新 annotation_count
            cursor = conn.execute(
                "SELECT COUNT(*) as cnt FROM comparison_annotations WHERE session_id = ?",
                (self.config.session_id,),
            )
            annotation_count = cursor.fetchone()[0]
            conn.execute(
                "UPDATE comparison_sessions SET annotation_count = ?, updated_at = ? WHERE session_id = ?",
                (annotation_count, now, self.config.session_id),
            )
            conn.commit()
            logger.info(
                "自动标注一致记录完成 session_id=%s, 标注数=%d",
                self.config.session_id, annotation_count,
            )
        finally:
            conn.close()

    def _insert_comparison_result(self, result: dict[str, Any]) -> None:
        """将单条对比结果写入 comparison_results 表。"""
        conn = sqlite3.connect(str(self.sqlite_path))
        try:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                INSERT OR REPLACE INTO comparison_results (
                    session_id, entity_key, enterprise_name,
                    old_label, new_label, confidence_level, decision_reason,
                    decision_record_json, error_type,
                    wide_row_json, static_profile_json, dynamic_profile_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.config.session_id,
                    result["entity_key"],
                    result.get("enterprise_name"),
                    result["old_label"],
                    result.get("new_label"),
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
        """执行对比评估，并行调用 run_once 并记录结果。

        与 backtest_engine.py 的 run() 方法模式完全一致：
        - ThreadPoolExecutor 并行处理
        - RateLimitedLLMClient + MinuteRateLimiter 速率限制
        - 逐条写入 comparison_results 表
        - 实时更新进度
        """
        # 更新状态提示：正在拉取数据
        self._update_session_progress(0, 0, "正在从 ODPS 拉取数据...")

        dataset = self.fetch_comparison_dataset()
        total = len(dataset)

        # 更新 dataset_size（路由层已预创建记录，这里用 UPDATE 更新）
        self._create_session_record(dataset_size=total)

        if total == 0:
            self._finalize_session(status="diff_ready", diff_count=0, dataset_size=0)
            return

        # 构建 LLM 客户端 + 速率限制（所有线程共享同一个限流器）
        llm_settings = load_llm_settings()
        http_client = HttpLLMClient(settings=llm_settings)
        limiter = MinuteRateLimiter(self.config.provider_rate_limit_per_minute)
        client = RateLimitedLLMClient(http_client, limiter)

        completed_count = 0
        error_count = 0
        diff_count = 0
        progress_lock = threading.Lock()

        def _classify_one(record: dict) -> dict[str, Any]:
            """单条企业的对比分类（在工作线程中执行）。"""
            entity_key = record["entity_key"]
            enterprise_name = record.get("enterprise_name", "")
            wide_row = record["wide_row"]
            old_label = record["old_label"]

            run_id = f"cmp-{self.config.session_id}-{entity_key}"
            result_record: dict[str, Any] = {
                "entity_key": entity_key,
                "enterprise_name": enterprise_name,
                "old_label": old_label,
                "new_label": None,
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
                    result_record["new_label"] = dr.final_label
                    result_record["confidence_level"] = dr.confidence_level
                    result_record["decision_reason"] = dr.decision_reason
                    result_record["decision_record_json"] = json.dumps(
                        dr.model_dump(), ensure_ascii=False
                    )
                elif state.error_type:
                    result_record["error_type"] = state.error_type
                else:
                    result_record["error_type"] = "no_decision_record"

                # 保存完整画像数据
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
                    "对比单条失败 entity_key=%s error=%s: %s",
                    entity_key, error_type, exc,
                )
                result_record["error_type"] = error_type

            return result_record

        max_workers = min(self.config.worker_count, total)

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
                    self._insert_comparison_result(result_record)

                    with progress_lock:
                        if result_record.get("error_type"):
                            error_count += 1
                        completed_count += 1

                        # 计算 diff：new_label 与 old_label 不一致
                        new_label = result_record.get("new_label")
                        old_label = result_record.get("old_label")
                        if new_label and new_label != old_label:
                            diff_count += 1
                        elif not new_label and result_record.get("error_type"):
                            # LLM 失败无 new_label，也算差异
                            diff_count += 1

                        # 更新进度
                        self._update_session_progress(
                            completed_count, error_count,
                            record.get("enterprise_name"),
                        )
                        if on_progress:
                            on_progress(
                                completed_count, total,
                                record.get("enterprise_name", ""),
                            )

            # 完成运行：更新状态为 diff_ready
            self._update_session_progress(completed_count, error_count, None)
            self._finalize_session(
                status="diff_ready", diff_count=diff_count, dataset_size=total
            )

            # 自动标注一致记录：old_label == new_label 的记录自动设置 human_label
            self._auto_annotate_consistent_records()

        except Exception as exc:
            logger.error("对比运行整体异常: %s", exc)
            self._finalize_session(
                status="error", diff_count=diff_count, dataset_size=total
            )
            raise
        finally:
            if hasattr(http_client, "close"):
                http_client.close()

    def get_diff_analysis(self, session_id: str) -> dict:
        """计算差异指标：一致率、变更矩阵、Diff_Record 列表、变更统计。

        从 comparison_results 读取数据，计算：
        - consistency_rate: 一致率（old_label == new_label 的比例）
        - change_matrix: 变更矩阵 {old_label: {new_label: count}}
        - change_type_ranking: 变更类型排行（按数量降序）
        - net_changes: 各标签净变化量
        - diff_list: 差异记录列表（仅 old_label != new_label 的记录）

        Records with error_type（无 new_label）排除在矩阵计算之外，但计入 dataset_size。
        """
        import collections

        conn = sqlite3.connect(str(self.sqlite_path))
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT entity_key, enterprise_name, old_label, new_label,
                       confidence_level, decision_reason, error_type
                FROM comparison_results
                WHERE session_id = ?
                """,
                (session_id,),
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        if not rows:
            raise ValueError(f"会话 {session_id} 不存在或无对比结果")

        dataset_size = len(rows)

        # 分离有效记录（有 new_label）和错误记录（有 error_type，无 new_label）
        valid_rows = [r for r in rows if r["new_label"] and not r["error_type"]]

        # 计算一致率：基于有效记录中 old_label == new_label 的比例占总 dataset_size
        consistent_count = sum(
            1 for r in valid_rows if r["old_label"] == r["new_label"]
        )
        consistency_rate = consistent_count / dataset_size if dataset_size > 0 else 0.0

        # 构建变更矩阵（仅有效记录参与）
        change_matrix: dict[str, dict[str, int]] = collections.defaultdict(
            lambda: collections.defaultdict(int)
        )
        for r in valid_rows:
            change_matrix[r["old_label"]][r["new_label"]] += 1

        # 转换为普通 dict 以便序列化
        change_matrix_dict: dict[str, dict[str, int]] = {
            k: dict(v) for k, v in change_matrix.items()
        }

        # 生成 diff_list：仅有效记录中 old_label != new_label 的记录
        diff_list: list[dict] = []
        for r in valid_rows:
            if r["old_label"] != r["new_label"]:
                diff_list.append({
                    "entity_key": r["entity_key"],
                    "enterprise_name": r["enterprise_name"],
                    "old_label": r["old_label"],
                    "new_label": r["new_label"],
                    "confidence_level": r["confidence_level"],
                    "decision_reason": r["decision_reason"],
                })

        diff_count = len(diff_list)

        # 计算 change_type_ranking：按 (old_label, new_label) 分组统计，按数量降序
        change_type_counter: dict[tuple[str, str], int] = collections.Counter()
        for r in valid_rows:
            if r["old_label"] != r["new_label"]:
                change_type_counter[(r["old_label"], r["new_label"])] += 1

        change_type_ranking: list[dict] = sorted(
            [
                {"old_label": k[0], "new_label": k[1], "count": v}
                for k, v in change_type_counter.items()
            ],
            key=lambda x: x["count"],
            reverse=True,
        )

        # 计算 net_changes：net_changes[label] = count(new_label==label) - count(old_label==label)
        new_label_counter: dict[str, int] = collections.Counter()
        old_label_counter: dict[str, int] = collections.Counter()
        for r in valid_rows:
            new_label_counter[r["new_label"]] += 1
            old_label_counter[r["old_label"]] += 1

        all_labels = set(new_label_counter.keys()) | set(old_label_counter.keys())
        net_changes: dict[str, int] = {
            label: new_label_counter.get(label, 0) - old_label_counter.get(label, 0)
            for label in sorted(all_labels)
        }

        return {
            "session_id": session_id,
            "dataset_size": dataset_size,
            "diff_count": diff_count,
            "consistency_rate": consistency_rate,
            "change_matrix": change_matrix_dict,
            "change_type_ranking": change_type_ranking,
            "net_changes": net_changes,
        }

    def annotate(
        self,
        session_id: str,
        annotations: list[dict],
        reviewer_name: str = "",
    ) -> None:
        """存储人工标注（支持单条和批量）。

        参数:
            session_id: 会话 ID
            annotations: 标注列表，每条为 {entity_key: str, human_label: str}
            reviewer_name: 标注人名称（可选）

        异常:
            ValueError: entity_key 不属于该 session 的差异记录，或 human_label 不在合法标签列表中
        """
        from industry_classification.settings import load_taxonomy

        # 加载合法标签列表（同时接受 id 和 display_name）
        taxonomy = load_taxonomy()
        valid_labels: set[str] = set()
        for label in taxonomy.labels:
            if label.enabled:
                valid_labels.add(label.id)
                valid_labels.add(label.display_name)

        conn = sqlite3.connect(str(self.sqlite_path))
        try:
            conn.row_factory = sqlite3.Row

            # 获取该 session 中所有差异记录的 entity_key 集合
            cursor = conn.execute(
                """
                SELECT entity_key FROM comparison_results
                WHERE session_id = ?
                  AND new_label IS NOT NULL
                """,
                (session_id,),
            )
            diff_entity_keys: set[str] = {row["entity_key"] for row in cursor.fetchall()}

            # 校验每条标注
            for ann in annotations:
                entity_key = ann.get("entity_key", "")
                human_label = ann.get("human_label", "")

                if entity_key not in diff_entity_keys:
                    raise ValueError(
                        f"entity_key '{entity_key}' 不属于会话 {session_id} 的差异记录"
                    )
                if human_label not in valid_labels:
                    raise ValueError(
                        f"human_label '{human_label}' 不在合法标签列表中"
                    )

            # UPSERT 标注记录
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            for ann in annotations:
                conn.execute(
                    """
                    INSERT INTO comparison_annotations
                        (session_id, entity_key, human_label, reviewer_name, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        ann["entity_key"],
                        ann["human_label"],
                        reviewer_name,
                        now,
                    ),
                )

            # 更新 annotation_count：统计该 session 当前标注总数
            cursor = conn.execute(
                "SELECT COUNT(*) as cnt FROM comparison_annotations WHERE session_id = ?",
                (session_id,),
            )
            annotation_count = cursor.fetchone()["cnt"]

            conn.execute(
                """
                UPDATE comparison_sessions
                SET annotation_count = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (annotation_count, now, session_id),
            )

            conn.commit()
        finally:
            conn.close()

    def get_records(self, session_id: str, status: str, page: int, page_size: int) -> dict:
        """分页获取记录，支持按标注状态筛选。

        参数:
            session_id: 会话 ID
            status: 筛选状态 "all" | "annotated" | "unannotated"
            page: 页码（1-indexed）
            page_size: 每页记录数

        返回:
            匹配 RecordsResponse schema 的字典:
            - records: DiffRecord 列表
            - total: 匹配记录总数（分页前）
            - page: 当前页码
            - page_size: 每页大小
            - annotation_progress: {annotated: int, total_diff: int}
        """
        conn = sqlite3.connect(str(self.sqlite_path))
        try:
            conn.row_factory = sqlite3.Row

            # 基础查询：所有有效记录 LEFT JOIN 最新标注
            base_from = """
                FROM comparison_results cr
                LEFT JOIN (
                  SELECT session_id, entity_key, human_label, reviewer_name,
                         ROW_NUMBER() OVER (PARTITION BY session_id, entity_key ORDER BY annotation_id DESC) as rn
                  FROM comparison_annotations
                ) ca ON cr.session_id = ca.session_id AND cr.entity_key = ca.entity_key AND ca.rn = 1
                WHERE cr.session_id = ?
                  AND cr.new_label IS NOT NULL
                  AND cr.error_type IS NULL
            """

            # 根据 status 添加筛选条件
            if status == "annotated":
                filter_clause = " AND ca.human_label IS NOT NULL"
            elif status == "unannotated":
                filter_clause = " AND ca.human_label IS NULL"
            else:
                filter_clause = ""

            # 查询匹配记录总数
            count_sql = f"SELECT COUNT(*) as cnt {base_from}{filter_clause}"
            cursor = conn.execute(count_sql, (session_id,))
            total = cursor.fetchone()["cnt"]

            # 分页查询记录
            offset = (page - 1) * page_size
            select_sql = f"""
                SELECT cr.entity_key, cr.enterprise_name, cr.old_label, cr.new_label,
                       cr.confidence_level, cr.decision_reason, ca.human_label
                {base_from}{filter_clause}
                LIMIT ? OFFSET ?
            """
            cursor = conn.execute(select_sql, (session_id, page_size, offset))
            rows = cursor.fetchall()

            records = [
                {
                    "entity_key": row["entity_key"],
                    "enterprise_name": row["enterprise_name"],
                    "old_label": row["old_label"],
                    "new_label": row["new_label"],
                    "confidence_level": row["confidence_level"],
                    "decision_reason": row["decision_reason"],
                    "human_label": row["human_label"],
                }
                for row in rows
            ]

            # 计算 annotation_progress
            # total_diff: 该 session 所有有效记录数
            cursor = conn.execute(
                """
                SELECT COUNT(*) as cnt FROM comparison_results
                WHERE session_id = ?
                  AND new_label IS NOT NULL
                  AND error_type IS NULL
                """,
                (session_id,),
            )
            total_diff = cursor.fetchone()["cnt"]

            # annotated: 该 session 已标注的差异记录数
            cursor = conn.execute(
                """
                SELECT COUNT(*) as cnt FROM comparison_annotations
                WHERE session_id = ?
                """,
                (session_id,),
            )
            annotated = cursor.fetchone()["cnt"]

            return {
                "records": records,
                "total": total,
                "page": page,
                "page_size": page_size,
                "annotation_progress": {
                    "annotated": annotated,
                    "total_diff": total_diff,
                },
            }
        finally:
            conn.close()

    def generate_report(self, session_id: str) -> dict:
        """生成完整评估报告：准确率、指标、混淆矩阵、系统建议。

        从 comparison_results LEFT JOIN comparison_annotations 读取数据，
        仅对差异记录（old_label != new_label）中已标注的部分计算指标。

        返回 ComparisonReport schema 格式的字典。

        异常:
            ValueError: 无任何标注记录时抛出
        """
        import collections

        conn = sqlite3.connect(str(self.sqlite_path))
        try:
            conn.row_factory = sqlite3.Row

            # 读取所有有效记录 LEFT JOIN 最新标注
            cursor = conn.execute(
                """
                SELECT cr.entity_key, cr.old_label, cr.new_label, ca.human_label
                FROM comparison_results cr
                LEFT JOIN (
                  SELECT session_id, entity_key, human_label,
                         ROW_NUMBER() OVER (PARTITION BY session_id, entity_key ORDER BY annotation_id DESC) as rn
                  FROM comparison_annotations
                ) ca ON cr.session_id = ca.session_id AND cr.entity_key = ca.entity_key AND ca.rn = 1
                WHERE cr.session_id = ?
                  AND cr.new_label IS NOT NULL
                  AND cr.error_type IS NULL
                """,
                (session_id,),
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        # 总有效记录数
        total_diff_count = len(rows)

        # 已标注的记录
        annotated_rows = [r for r in rows if r["human_label"] is not None]
        total_annotated = len(annotated_rows)

        if total_annotated == 0:
            raise ValueError("请先完成至少一条记录的标注")

        # --- 整体准确率 ---
        old_correct = sum(
            1 for r in annotated_rows if r["old_label"] == r["human_label"]
        )
        new_correct = sum(
            1 for r in annotated_rows if r["new_label"] == r["human_label"]
        )
        old_accuracy = old_correct / total_annotated
        new_accuracy = new_correct / total_annotated
        improvement = new_accuracy - old_accuracy

        # --- 覆盖率 ---
        coverage = total_annotated / total_diff_count if total_diff_count > 0 else 0.0
        coverage_warning: str | None = None
        if coverage < 1.0:
            coverage_warning = "部分差异记录未标注，评估结果可能不完整"

        # --- 收集所有出现的标签 ---
        all_labels: set[str] = set()
        for r in annotated_rows:
            all_labels.add(r["human_label"])
            all_labels.add(r["old_label"])
            all_labels.add(r["new_label"])

        # --- 每个标签的指标 ---
        label_metrics: list[dict] = []
        recommendations: list[dict] = []

        for label in sorted(all_labels):
            # 老标签指标
            tp_old = sum(
                1 for r in annotated_rows
                if r["human_label"] == label and r["old_label"] == label
            )
            fp_old = sum(
                1 for r in annotated_rows
                if r["human_label"] != label and r["old_label"] == label
            )
            fn_old = sum(
                1 for r in annotated_rows
                if r["human_label"] == label and r["old_label"] != label
            )

            old_precision = tp_old / (tp_old + fp_old) if (tp_old + fp_old) > 0 else 0.0
            old_recall = tp_old / (tp_old + fn_old) if (tp_old + fn_old) > 0 else 0.0
            old_f1 = (
                2 * old_precision * old_recall / (old_precision + old_recall)
                if (old_precision + old_recall) > 0
                else 0.0
            )

            # 新标签指标
            tp_new = sum(
                1 for r in annotated_rows
                if r["human_label"] == label and r["new_label"] == label
            )
            fp_new = sum(
                1 for r in annotated_rows
                if r["human_label"] != label and r["new_label"] == label
            )
            fn_new = sum(
                1 for r in annotated_rows
                if r["human_label"] == label and r["new_label"] != label
            )

            new_precision = tp_new / (tp_new + fp_new) if (tp_new + fp_new) > 0 else 0.0
            new_recall = tp_new / (tp_new + fn_new) if (tp_new + fn_new) > 0 else 0.0
            new_f1 = (
                2 * new_precision * new_recall / (new_precision + new_recall)
                if (new_precision + new_recall) > 0
                else 0.0
            )

            # 每个标签的准确率（该标签相关记录中正确的比例）
            # old_acc_L: 在 human_label == L 的记录中，old_label == L 的比例
            # new_acc_L: 在 human_label == L 的记录中，new_label == L 的比例
            label_support = tp_old + fn_old  # count(human_label == label)
            old_acc_l = tp_old / label_support if label_support > 0 else 0.0
            new_acc_l = tp_new / label_support if label_support > 0 else 0.0

            # 建议
            if new_acc_l > old_acc_l:
                recommendation = "adopt_new"
                reason = f"新标签准确率({new_acc_l:.2%})高于老标签({old_acc_l:.2%})，建议采用新标签"
            elif new_acc_l < old_acc_l:
                recommendation = "keep_old"
                reason = f"新标签准确率({new_acc_l:.2%})低于老标签({old_acc_l:.2%})，建议保留老标签，需进一步优化"
            else:
                recommendation = "no_change"
                reason = f"新旧标签准确率相同({old_acc_l:.2%})，无显著变化"

            label_metrics.append({
                "label": label,
                "old_precision": old_precision,
                "old_recall": old_recall,
                "old_f1": old_f1,
                "new_precision": new_precision,
                "new_recall": new_recall,
                "new_f1": new_f1,
                "recommendation": recommendation,
            })

            recommendations.append({
                "label": label,
                "recommendation": recommendation,
                "reason": reason,
            })

        # --- 混淆矩阵 ---
        # old_confusion_matrix: {human_label: {old_label: count}}
        old_confusion: dict[str, dict[str, int]] = collections.defaultdict(
            lambda: collections.defaultdict(int)
        )
        # new_confusion_matrix: {human_label: {new_label: count}}
        new_confusion: dict[str, dict[str, int]] = collections.defaultdict(
            lambda: collections.defaultdict(int)
        )

        for r in annotated_rows:
            old_confusion[r["human_label"]][r["old_label"]] += 1
            new_confusion[r["human_label"]][r["new_label"]] += 1

        # 转换为普通 dict
        old_confusion_matrix = {k: dict(v) for k, v in old_confusion.items()}
        new_confusion_matrix = {k: dict(v) for k, v in new_confusion.items()}

        return {
            "session_id": session_id,
            "old_accuracy": old_accuracy,
            "new_accuracy": new_accuracy,
            "improvement": improvement,
            "coverage": coverage,
            "coverage_warning": coverage_warning,
            "label_metrics": label_metrics,
            "old_confusion_matrix": old_confusion_matrix,
            "new_confusion_matrix": new_confusion_matrix,
            "recommendations": recommendations,
        }

    def delete_session(self, session_id: str) -> bool:
        """级联删除会话及关联数据。

        按顺序删除 annotations → results → sessions，在单个事务中提交。
        返回 True 表示会话存在且已删除，False 表示 session_id 不存在。
        """
        conn = sqlite3.connect(str(self.sqlite_path))
        try:
            # 删除标注记录
            conn.execute(
                "DELETE FROM comparison_annotations WHERE session_id = ?",
                (session_id,),
            )
            # 删除对比结果记录
            conn.execute(
                "DELETE FROM comparison_results WHERE session_id = ?",
                (session_id,),
            )
            # 删除会话记录
            cursor = conn.execute(
                "DELETE FROM comparison_sessions WHERE session_id = ?",
                (session_id,),
            )
            # 判断会话是否存在
            session_existed = cursor.rowcount > 0
            conn.commit()
            return session_existed
        finally:
            conn.close()
