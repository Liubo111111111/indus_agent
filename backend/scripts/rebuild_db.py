"""
从 frontend/output 的 SQLite 迁移完整数据到 backend/output，
并用 JSON 源文件刷新 wide_row_json 确保字段完整。

用法:
    python backend/scripts/rebuild_db.py
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DB = ROOT / "frontend" / "output" / "pipeline_results.sqlite3"
BACKEND_DB = ROOT / "backend" / "output" / "pipeline_results.sqlite3"
JSON_SOURCE = ROOT / "frontend" / "output" / "data" / "wide_table_20260402.json"


def load_wide_index(json_path: Path) -> dict[str, dict]:
    """从 JSON 文件构建 social_credit_code → wide_row 索引。"""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    return {row["social_credit_code"]: row for row in data if "social_credit_code" in row}


def main() -> None:
    # 1. 备份现有 backend db
    if BACKEND_DB.exists():
        backup = BACKEND_DB.with_suffix(".sqlite3.bak")
        shutil.copy2(BACKEND_DB, backup)
        print(f"已备份: {backup}")

    # 2. 复制 frontend db → backend db（保留 pipeline_runs + 推理结果）
    if FRONTEND_DB.exists():
        shutil.copy2(FRONTEND_DB, BACKEND_DB)
        print(f"已复制 frontend DB → backend DB")
    else:
        print(f"错误: 找不到 {FRONTEND_DB}")
        return

    # 3. 用 JSON 源文件刷新 wide_row_json
    if not JSON_SOURCE.exists():
        print(f"警告: 找不到 JSON 源文件 {JSON_SOURCE}，跳过 wide_row 刷新")
        return

    wide_index = load_wide_index(JSON_SOURCE)
    print(f"JSON 源文件加载了 {len(wide_index)} 条企业数据")

    conn = sqlite3.connect(BACKEND_DB)
    conn.row_factory = sqlite3.Row

    # 修复 schema：确保 annotations 表有 reviewer_name 列
    cols = conn.execute("PRAGMA table_info(annotations)").fetchall()
    col_names = [c[1] for c in cols]
    if "reviewer_name" not in col_names:
        conn.execute('ALTER TABLE annotations ADD COLUMN reviewer_name text NOT NULL DEFAULT ""')
        conn.commit()
        print("已修复: annotations 表添加 reviewer_name 列")

    rows = conn.execute("SELECT run_id, entity_key, wide_row_json FROM pipeline_runs").fetchall()

    updated = 0
    for row in rows:
        entity_key = row["entity_key"]
        if entity_key in wide_index:
            new_wide = json.dumps(wide_index[entity_key], ensure_ascii=False, sort_keys=True)
            conn.execute(
                "UPDATE pipeline_runs SET wide_row_json = ?, updated_at = CURRENT_TIMESTAMP WHERE run_id = ?",
                (new_wide, row["run_id"]),
            )
            updated += 1

    conn.commit()

    # 验证
    sample = conn.execute("SELECT wide_row_json FROM pipeline_runs LIMIT 1").fetchone()
    if sample:
        wide = json.loads(sample["wide_row_json"])
        print(f"\n验证 - 字段列表: {list(wide.keys())}")
        print(f"  authentication_time: {wide.get('authentication_time')}")
        print(f"  latest_publish_time: {wide.get('latest_publish_time')}")
        print(f"  latest_publish_job_names: {wide.get('latest_publish_job_names')}")

    total = conn.execute("SELECT count(*) FROM pipeline_runs").fetchone()[0]
    conn.close()

    print(f"\n完成: 共 {total} 条记录，更新了 {updated} 条 wide_row_json")


if __name__ == "__main__":
    main()
