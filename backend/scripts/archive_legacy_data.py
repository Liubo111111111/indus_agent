"""将 output/ 根目录下的历史遗留数据归档到 output/_legacy/。

用法: uv run python backend/scripts/archive_legacy_data.py [--output-dir backend/output]
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

TARGET_FILES = [
    "formal_output.jsonl",
    "fallback_output.jsonl",
    "pipeline_results.sqlite3",
]


def archive(output_dir: Path) -> None:
    """将 output_dir 根目录下的遗留文件移动到 output_dir/_legacy/。

    源文件不存在时跳过，不报错。
    """
    legacy_dir = output_dir / "_legacy"
    legacy_dir.mkdir(parents=True, exist_ok=True)

    for filename in TARGET_FILES:
        src = output_dir / filename
        if not src.exists():
            print(f"跳过（不存在）: {src}")
            continue
        dst = legacy_dir / filename
        shutil.move(str(src), str(dst))
        print(f"已移动: {src} → {dst}")


def main() -> None:
    parser = argparse.ArgumentParser(description="归档 output/ 根目录下的历史遗留数据到 _legacy 目录")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("backend/output"),
        help="output 根目录路径（默认: backend/output）",
    )
    args = parser.parse_args()
    archive(args.output_dir)


if __name__ == "__main__":
    main()
