"""MaxCompute 结果写入器 — 将 SQLite 中的分类结果同步到 MC 结果表。

用法（独立运行）::

    uv run python -m industry_classification.writers.mc_writer \
        --output-dir output/20260412 --pt 20260412

也可在 batch_scheduler 完成后自动调用。
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# MC 结果表名
_RESULT_TABLE = "yuapo_dev.enterprise_industry_label_llm"

# 建表 DDL
_TABLE_DDL = f"""\
CREATE TABLE IF NOT EXISTS {_RESULT_TABLE} (
    social_credit_code STRING COMMENT '统一社会信用代码',
    enterprise_name    STRING COMMENT '企业名称',
    final_label        STRING COMMENT '最终行业标签',
    confidence_level   STRING COMMENT '置信度等级',
    decision_reason    STRING COMMENT '裁决理由',
    run_id             STRING COMMENT '运行ID',
    route              STRING COMMENT '路由(formal/fallback)',
    schedule_mode      STRING COMMENT '调度模式',
    processing_time    STRING COMMENT '处理时间'
)
PARTITIONED BY (pt STRING COMMENT '业务日期分区')
LIFECYCLE 365
"""


def _get_odps_client():
    """复用 data_fetcher 的 ODPS 连接逻辑。"""
    from industry_classification.data_fetcher import _get_odps_client as _get
    return _get()


def _read_results_from_sqlite(sqlite_path: Path) -> list[dict[str, Any]]:
    """从 pipeline_results.sqlite3 读取分类结果。"""
    if not sqlite_path.is_file():
        logger.warning("SQLite 文件不存在: %s", sqlite_path)
        return []

    conn = sqlite3.connect(str(sqlite_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT run_id, entity_key, route, decision_record_json, wide_row_json "
            "FROM pipeline_runs"
        ).fetchall()
    finally:
        conn.close()

    results: list[dict[str, Any]] = []
    for row in rows:
        dr = json.loads(row["decision_record_json"]) if row["decision_record_json"] else {}
        wr = json.loads(row["wide_row_json"]) if row["wide_row_json"] else {}
        results.append({
            "social_credit_code": row["entity_key"],
            "enterprise_name": wr.get("enterprise_name", ""),
            "final_label": dr.get("final_label", ""),
            "confidence_level": dr.get("confidence_level", ""),
            "decision_reason": dr.get("decision_reason", ""),
            "run_id": row["run_id"],
            "route": row["route"] or "",
        })
    return results


def sync_to_mc(
    output_dir: str | Path,
    pt: str,
    schedule_mode: str = "single-day",
    batch_size: int = 500,
    dry_run: bool = False,
) -> dict[str, Any]:
    """将 SQLite 分类结果同步到 MC 结果表。

    Args:
        output_dir: 包含 pipeline_results.sqlite3 的目录
        pt: 业务日期分区
        schedule_mode: 调度模式标记
        batch_size: 每批写入条数
        dry_run: 试运行，不实际写入

    Returns:
        写入统计 dict
    """
    output_path = Path(output_dir)
    sqlite_path = output_path / "pipeline_results.sqlite3"

    results = _read_results_from_sqlite(sqlite_path)
    if not results:
        logger.info("无分类结果需要同步")
        return {"total": 0, "success": 0, "failed": 0}

    logger.info("读取到 %d 条分类结果，准备同步到 MC (pt=%s)", len(results), pt)

    if dry_run:
        logger.info("[DRY RUN] 跳过 MC 写入，共 %d 条", len(results))
        for r in results[:3]:
            logger.info("  %s | %s | %s | %s",
                        r["social_credit_code"], r["enterprise_name"],
                        r["final_label"], r["confidence_level"])
        return {"total": len(results), "success": 0, "failed": 0, "dry_run": True}

    odps = _get_odps_client()

    # 确保表存在
    if not odps.exist_table(_RESULT_TABLE):
        logger.info("创建结果表 %s", _RESULT_TABLE)
        odps.execute_sql(_TABLE_DDL)

    # 确保分区存在，overwrite 模式先删旧数据
    table = odps.get_table(_RESULT_TABLE)
    partition_spec = f"pt='{pt}'"
    if table.exist_partition(partition_spec):
        table.delete_partition(partition_spec)
        logger.info("已删除旧分区 %s（overwrite 模式）", partition_spec)
    table.create_partition(partition_spec)
    logger.info("创建分区: %s", partition_spec)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    success = 0
    failed = 0

    for i in range(0, len(results), batch_size):
        batch = results[i:i + batch_size]
        try:
            with table.open_writer(partition=partition_spec, create_partition=True) as writer:
                for r in batch:
                    writer.write([
                        r["social_credit_code"],
                        r["enterprise_name"],
                        r["final_label"],
                        r["confidence_level"],
                        r["decision_reason"],
                        r["run_id"],
                        r["route"],
                        schedule_mode,
                        now_str,
                    ])
            success += len(batch)
        except Exception as exc:
            failed += len(batch)
            logger.error("批次 %d 写入失败: %s", i // batch_size + 1, exc)

    logger.info("MC 同步完成: 总计 %d, 成功 %d, 失败 %d", len(results), success, failed)
    return {"total": len(results), "success": success, "failed": failed}


# CLI 入口
if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="同步分类结果到 MaxCompute")
    parser.add_argument("--output-dir", required=True, help="包含 pipeline_results.sqlite3 的目录")
    parser.add_argument("--pt", required=True, help="业务日期分区 (yyyymmdd)")
    parser.add_argument("--schedule-mode", default="single-day", help="调度模式标记")
    parser.add_argument("--dry-run", action="store_true", help="试运行，不写入 MC")
    args = parser.parse_args()

    result = sync_to_mc(
        output_dir=args.output_dir,
        pt=args.pt,
        schedule_mode=args.schedule_mode,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("failed", 0) == 0 else 1)
