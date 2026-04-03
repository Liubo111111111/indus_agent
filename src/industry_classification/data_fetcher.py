"""
ODPS 数据拉取模块
从 yuapo_dev.enterprise_industry_wide_table 拉取宽表数据，
输出 CSV 并转换为 Batch Loader 可消费的 JSON/JSONL。
"""
from __future__ import annotations

import csv
import json
import logging
import time
from pathlib import Path
from typing import Any

from industry_classification.settings import load_odps_settings

logger = logging.getLogger(__name__)

# ODPS 宽表列 → WideRow 字段映射
_WIDE_TABLE = "yuapo_dev.enterprise_industry_wide_table"
_COLUMNS = [
    "user_id",
    "social_credit_code",
    "enterprise_name",
    "business_scope",
    "total_job_post_cnt_90d",
    "distinct_job_name_cnt_90d",
    "top_job_names_json",
    "jobs_recent_20_json",
    "latest_publish_time",
    "latest_publish_job_names_json",
    "authentication_time",
]


def _get_odps_client():
    """延迟导入 odps，避免未安装时影响其他模块。"""
    try:
        from odps import ODPS
    except ImportError as exc:
        raise ImportError(
            "pyodps is required for ODPS data fetching. "
            "Install it with: pip install pyodps"
        ) from exc

    settings = load_odps_settings()
    if not settings.access_key_id or not settings.access_key_secret:
        raise ValueError(
            "ODPS credentials not configured. "
            "Set ODPS_ACCESS_KEY_ID and ODPS_ACCESS_KEY_SECRET in .env"
        )
    return ODPS(
        settings.access_key_id,
        settings.access_key_secret,
        settings.project,
        endpoint=settings.endpoint,
    )


def fetch_wide_table(
    pt: str,
    output_dir: str | Path = "data",
    max_rows: int | None = None,
    batch_size: int = 1000,
    max_retries: int = 3,
    retry_delay: int = 5,
) -> Path:
    """
    从 ODPS 拉取宽表数据，保存为 CSV。

    Args:
        pt: 业务日期分区，格式 yyyymmdd
        output_dir: 输出目录
        max_rows: 最大拉取条数，None 表示不限
        batch_size: 每批查询条数
        max_retries: 查询失败重试次数
        retry_delay: 重试间隔秒数

    Returns:
        CSV 文件路径
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    csv_path = output_path / f"wide_table_{pt}.csv"

    odps = _get_odps_client()
    columns_str = ", ".join(_COLUMNS)
    offset = 0
    total_rows = 0
    header_written = False

    logger.info("开始从 ODPS 拉取宽表数据 pt=%s", pt)

    while True:
        if max_rows is not None and total_rows >= max_rows:
            break

        current_limit = batch_size
        if max_rows is not None:
            current_limit = min(batch_size, max_rows - total_rows)

        sql = (
            f"SELECT {columns_str} FROM {_WIDE_TABLE} "
            f"WHERE pt = '{pt}' "
            f"ORDER BY user_id "
            f"LIMIT {current_limit} OFFSET {offset};"
        )

        rows = _execute_with_retry(odps, sql, max_retries, retry_delay)
        if not rows:
            break

        _write_csv_batch(csv_path, rows, header_written)
        header_written = True
        total_rows += len(rows)
        logger.info("已拉取 %d 条（累计 %d）", len(rows), total_rows)

        if len(rows) < current_limit:
            break
        offset += batch_size

    if total_rows == 0:
        logger.warning("pt=%s 未拉取到任何数据", pt)
        raise RuntimeError(f"No data found for pt={pt}")

    logger.info("CSV 拉取完成: %s (%d 条)", csv_path, total_rows)
    return csv_path


def _execute_with_retry(
    odps, sql: str, max_retries: int, retry_delay: int
) -> list[dict[str, Any]]:
    """执行 ODPS SQL，带重试。"""
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            results = []
            with odps.execute_sql(sql).open_reader() as reader:
                for record in reader:
                    row = {}
                    for col in record._columns:
                        row[col.name] = record.get_by_name(col.name)
                    results.append(row)
            return results
        except Exception as exc:
            last_error = exc
            logger.warning(
                "ODPS 查询失败 attempt=%d/%d: %s",
                attempt + 1, max_retries, exc,
            )
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
    raise RuntimeError(f"ODPS query failed after {max_retries} attempts: {last_error}")


def _write_csv_batch(
    csv_path: Path, rows: list[dict[str, Any]], append: bool
) -> None:
    """将一批数据写入 CSV。"""
    mode = "a" if append else "w"
    with csv_path.open(mode, encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=_COLUMNS,
            quoting=csv.QUOTE_ALL,
            escapechar="\\",
        )
        if not append:
            writer.writeheader()
        writer.writerows(rows)


def csv_to_json(
    csv_path: str | Path,
    output_path: str | Path | None = None,
    format: str = "json",
) -> Path:
    """
    将 ODPS 宽表 CSV 转换为 WideRow 兼容的 JSON/JSONL。

    CSV 中 top_job_names_json 和 jobs_recent_20_json 是 JSON 字符串，
    需要解析后映射为 WideRow 的 top_job_names 和 jobs_recent_20 字段。

    Args:
        csv_path: CSV 文件路径
        output_path: 输出路径，默认与 CSV 同目录
        format: "json" 输出 JSON 数组，"jsonl" 输出每行一条

    Returns:
        输出文件路径
    """
    csv_file = Path(csv_path)
    if output_path is None:
        suffix = ".jsonl" if format == "jsonl" else ".json"
        out_file = csv_file.with_suffix(suffix)
    else:
        out_file = Path(output_path)

    records: list[dict[str, Any]] = []

    with csv_file.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            record = _csv_row_to_wide_row(row)
            records.append(record)

    out_file.parent.mkdir(parents=True, exist_ok=True)

    if format == "jsonl":
        with out_file.open("w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    else:
        with out_file.open("w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    logger.info("CSV → %s 转换完成: %s (%d 条)", format.upper(), out_file, len(records))
    return out_file


def _csv_row_to_wide_row(row: dict[str, str]) -> dict[str, Any]:
    """将 CSV 行转换为 WideRow 兼容的 dict。"""
    # 解析 JSON 字符串字段
    top_job_names_raw = _safe_json_parse(row.get("top_job_names_json", "[]"))
    jobs_recent_20_raw = _safe_json_parse(row.get("jobs_recent_20_json", "[]"))

    return {
        "user_id": int(row.get("user_id", 0)),
        "social_credit_code": row.get("social_credit_code", ""),
        "enterprise_name": row.get("enterprise_name", ""),
        "business_scope": row.get("business_scope", ""),
        "total_job_post_cnt_90d": int(row.get("total_job_post_cnt_90d", 0)),
        "distinct_job_name_cnt_90d": int(row.get("distinct_job_name_cnt_90d", 0)),
        "top_job_names": _normalize_top_jobs(top_job_names_raw),
        "jobs_recent_20": _normalize_job_facts(jobs_recent_20_raw),
        "latest_publish_time": row.get("latest_publish_time") or None,
        "latest_publish_job_names": _normalize_string_list(
            _safe_json_parse(row.get("latest_publish_job_names_json", "[]"))
        ),
        "authentication_time": row.get("authentication_time") or None,
    }


def _safe_json_parse(text: str) -> list:
    """安全解析 JSON 字符串，失败返回空列表。"""
    if not text or text.strip() in ("", "[]", "null", "None"):
        return []
    try:
        result = json.loads(text)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        logger.warning("JSON 解析失败，返回空列表: %.100s", text)
        return []


def _normalize_top_jobs(raw: list) -> list[dict[str, Any]]:
    """标准化 top_job_names，确保字段名和类型与 TopJobStat 一致。"""
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        result.append({
            "job_name": str(item.get("job_name", "")),
            "cnt": int(item.get("cnt", 0)),
            "ratio": float(item.get("ratio", 0.0)),
        })
    return result


def _normalize_job_facts(raw: list) -> list[dict[str, Any]]:
    """标准化 jobs_recent_20，确保字段名和类型与 JobFact 一致。"""
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        result.append({
            "job_name": str(item.get("job_name", "")),
            "desc": str(item.get("desc", "")),
            "add_time": str(item.get("add_time", "")),
        })
    return result


def _normalize_string_list(raw: list) -> list[str]:
    """标准化字符串列表，过滤空值。"""
    return [str(item) for item in raw if item and str(item).strip()]


def fetch_and_convert(
    pt: str,
    output_dir: str | Path = "data",
    format: str = "json",
    max_rows: int | None = None,
) -> Path:
    """
    一站式：ODPS 拉取 → CSV → JSON/JSONL。

    返回最终 JSON/JSONL 文件路径，可直接传给 Batch Loader。
    """
    csv_path = fetch_wide_table(pt=pt, output_dir=output_dir, max_rows=max_rows)
    json_path = csv_to_json(csv_path, format=format)
    logger.info("数据准备完成: %s", json_path)
    return json_path
