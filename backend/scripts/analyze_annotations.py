"""分析审核标注情况：总准确率、各行业标签准确率。

用法:
    python backend/scripts/analyze_annotations.py backend/output/20260421
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path


def _load_annotation_pairs(db_path: Path) -> list[dict]:
    """从 SQLite 加载标注与预测的配对数据。"""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT
            a.entity_key,
            a.annotated_label,
            a.reviewer_name,
            a.reviewer_notes,
            p.route,
            json_extract(p.decision_record_json, '$.final_label') AS predicted_label,
            json_extract(p.decision_record_json, '$.confidence_level') AS confidence_level
        FROM annotations a
        JOIN pipeline_runs p ON a.run_id = p.run_id AND a.entity_key = p.entity_key
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def _analyze(pairs: list[dict]) -> dict:
    """计算总准确率和各行业标签的准确率。"""
    total = len(pairs)
    correct = sum(1 for p in pairs if p["predicted_label"] == p["annotated_label"])

    # 按标注标签（真实标签）分组统计
    by_label: dict[str, dict] = defaultdict(lambda: {"total": 0, "correct": 0})
    for p in pairs:
        label = p["annotated_label"]
        by_label[label]["total"] += 1
        if p["predicted_label"] == p["annotated_label"]:
            by_label[label]["correct"] += 1

    # 按预测标签分组统计（查看模型对每个标签的精确率）
    by_pred: dict[str, dict] = defaultdict(lambda: {"total": 0, "correct": 0})
    for p in pairs:
        label = p["predicted_label"]
        by_pred[label]["total"] += 1
        if p["predicted_label"] == p["annotated_label"]:
            by_pred[label]["correct"] += 1

    # 混淆矩阵
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for p in pairs:
        confusion[p["annotated_label"]][p["predicted_label"]] += 1

    # 按审核人统计
    by_reviewer: dict[str, dict] = defaultdict(lambda: {"total": 0, "correct": 0})
    for p in pairs:
        reviewer = p["reviewer_name"] or "未知"
        by_reviewer[reviewer]["total"] += 1
        if p["predicted_label"] == p["annotated_label"]:
            by_reviewer[reviewer]["correct"] += 1

    # 错误案例
    errors = [p for p in pairs if p["predicted_label"] != p["annotated_label"]]

    return {
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total else 0,
        "by_annotated_label": dict(by_label),
        "by_predicted_label": dict(by_pred),
        "confusion": {k: dict(v) for k, v in confusion.items()},
        "by_reviewer": dict(by_reviewer),
        "errors": errors,
    }


def _deep_analyze_errors(pairs: list[dict], db_path: Path) -> list[dict]:
    """深入分析错误案例的推理过程，归纳错误模式。"""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    errors = []
    for p in pairs:
        if p["predicted_label"] == p["annotated_label"]:
            continue

        cur.execute("""
            SELECT
                decision_record_json,
                static_profile_json,
                dynamic_profile_json,
                wide_row_json
            FROM pipeline_runs
            WHERE entity_key = ? AND run_id = (
                SELECT run_id FROM annotations WHERE entity_key = ? LIMIT 1
            )
        """, (p["entity_key"], p["entity_key"]))
        row = cur.fetchone()
        if not row:
            continue

        dec = json.loads(row["decision_record_json"]) if row["decision_record_json"] else {}
        sp = json.loads(row["static_profile_json"]) if row["static_profile_json"] else {}
        dp = json.loads(row["dynamic_profile_json"]) if row["dynamic_profile_json"] else {}
        wr = json.loads(row["wide_row_json"]) if row["wide_row_json"] else {}

        # 判断静态画像是否正确
        static_top1 = ""
        if sp.get("top3_labels"):
            static_top1 = sp["top3_labels"][0].get("label", "")

        errors.append({
            "entity_key": p["entity_key"],
            "enterprise_name": wr.get("enterprise_name", ""),
            "predicted_label": p["predicted_label"],
            "annotated_label": p["annotated_label"],
            "confidence_level": dec.get("confidence_level", ""),
            "decision_reason": dec.get("decision_reason", ""),
            "static_top1": static_top1,
            "static_correct": static_top1 == p["annotated_label"],
            "dynamic_core_jobs": dp.get("core_jobs", []),
            "dynamic_scene": dp.get("scene", ""),
            "dynamic_continuity": dp.get("continuity", ""),
            "reviewer_notes": p.get("reviewer_notes", ""),
        })

    conn.close()
    return errors


def _print_error_pattern_analysis(errors: list[dict]) -> None:
    """打印错误模式分析。"""
    if not errors:
        return

    print(f"\n{'=' * 70}")
    print(f"  错误模式深度分析")
    print(f"{'=' * 70}")

    # 1. 静态画像本来正确但被动态画像覆盖的比例
    static_was_correct = [e for e in errors if e["static_correct"]]
    print(f"\n【模式一】静态画像正确但被动态画像覆盖: {len(static_was_correct)}/{len(errors)} ({len(static_was_correct)/len(errors):.0%})")
    if static_was_correct:
        for e in static_was_correct:
            print(f"  · {e['enterprise_name'][:20]:<22} 静态={e['static_top1']:<8} 动态→{e['predicted_label']:<8} 标注={e['annotated_label']:<8} 动态岗位={e['dynamic_core_jobs']}")

    # 2. 低置信度错误
    low_conf = [e for e in errors if e["confidence_level"] in ("low",)]
    med_conf = [e for e in errors if e["confidence_level"] in ("medium",)]
    print(f"\n【模式二】按置信度分布:")
    print(f"  · low 置信度错误: {len(low_conf)} 条")
    print(f"  · medium 置信度错误: {len(med_conf)} 条")

    # 3. 稀疏招聘导致的误判
    sparse = [e for e in errors if "稀疏" in e["dynamic_continuity"] or "仅发布1" in e["dynamic_continuity"]]
    print(f"\n【模式三】稀疏招聘导致误判: {len(sparse)}/{len(errors)} ({len(sparse)/len(errors):.0%})")

    # 4. 按错误方向分类
    print(f"\n【模式四】错误方向分类:")
    direction_counts: dict[str, int] = defaultdict(int)
    for e in errors:
        key = f"{e['predicted_label']} → 实际应为 {e['annotated_label']}"
        direction_counts[key] += 1
    for direction, count in sorted(direction_counts.items(), key=lambda x: -x[1]):
        print(f"  · {direction}: {count} 条")

    # 5. 典型错误场景归纳
    print(f"\n【模式五】典型错误场景:")

    # 非主营业务的临时招聘
    temp_hire = [e for e in errors if any(kw in e["dynamic_scene"] for kw in ("临时", "偶发", "零星"))]
    if temp_hire:
        print(f"\n  ▸ 非主营业务的临时/偶发招聘被过度解读 ({len(temp_hire)} 条):")
        for e in temp_hire:
            print(f"    {e['enterprise_name'][:20]:<22} 预测={e['predicted_label']:<8} 场景: {e['dynamic_scene'][:60]}")

    # 旅游/代驾等边界场景
    boundary = [e for e in errors if any(kw in (e.get("reviewer_notes", "") + e["dynamic_scene"] + e["decision_reason"])
                for kw in ("旅游", "代驾", "自动驾驶", "商务接待", "通勤", "驾校"))]
    if boundary:
        print(f"\n  ▸ 边界场景误判（旅游客运/代驾/商务接待/自动驾驶等）({len(boundary)} 条):")
        for e in boundary:
            notes = e.get("reviewer_notes", "")
            print(f"    {e['enterprise_name'][:20]:<22} 预测={e['predicted_label']:<8} 标注={e['annotated_label']:<8} 备注={notes}")

    # 制造/贸易企业招聘司机
    mfg_driver = [e for e in errors if any(kw in e["dynamic_scene"] for kw in ("制造", "工厂", "配送", "送货", "运输瓷砖", "豆制品"))]
    if mfg_driver:
        print(f"\n  ▸ 制造/贸易企业自有物流需求被误判为货运物流 ({len(mfg_driver)} 条):")
        for e in mfg_driver:
            print(f"    {e['enterprise_name'][:20]:<22} 预测={e['predicted_label']:<8} 场景: {e['dynamic_scene'][:60]}")

    # 美容/健康被误判为娱乐服务
    beauty = [e for e in errors if "娱乐服务" in e["predicted_label"] and e["annotated_label"] == "其他"]
    if beauty:
        print(f"\n  ▸ 健康管理/美容/游乐被误判为娱乐服务 ({len(beauty)} 条):")
        for e in beauty:
            print(f"    {e['enterprise_name'][:20]:<22} 场景: {e['dynamic_scene'][:60]}")

    # 6. 改进建议
    print(f"\n{'─' * 70}")
    print(f"  改进建议")
    print(f"{'─' * 70}")
    suggestions = []
    if len(static_was_correct) > len(errors) * 0.5:
        suggestions.append("1. 动态画像优先规则过于激进：当招聘行为稀疏（≤2次/90天）且与静态画像矛盾时，应降低动态画像权重或回退到静态画像判断")
    if len(sparse) > len(errors) * 0.5:
        suggestions.append("2. 稀疏招聘阈值：建议对近90天仅发布1-2个岗位的企业，不以单一岗位覆盖主营业务判断，而是标记为低置信度并倾向'其他'")
    if direction_counts.get("网约车 → 实际应为 其他", 0) > 3:
        suggestions.append("3. 网约车边界收紧：旅游客运、代驾、商务接待、自动驾驶测试等场景不应直接归入网约车，需增加排除规则")
    if direction_counts.get("货运物流 → 实际应为 其他", 0) > 3:
        suggestions.append("4. 货运物流边界收紧：制造/贸易/食品企业自有物流需求（招聘1-2名司机）不应归入货运物流，需区分'自有物流'与'物流主营'")
    if beauty:
        suggestions.append("5. 娱乐服务边界：医疗美容、健康管理、儿童游乐等场景与典型娱乐服务（KTV/酒吧/足浴）有本质区别，需细化判定标准")

    if not suggestions:
        suggestions.append("暂无明确改进建议，错误分布较分散")

    for s in suggestions:
        print(f"  {s}")


def _print_report(result: dict) -> None:
    """打印分析报告。"""
    total = result["total"]
    correct = result["correct"]
    accuracy = result["accuracy"]

    print("=" * 70)
    print(f"  审核标注分析报告")
    print("=" * 70)
    print(f"\n总标注数: {total}")
    print(f"预测正确: {correct}")
    print(f"预测错误: {total - correct}")
    print(f"总准确率: {accuracy:.1%}")

    # 各行业标签的召回率（按真实标签）
    print(f"\n{'─' * 70}")
    print(f"  按真实标签（标注标签）统计 — 召回率 (Recall)")
    print(f"{'─' * 70}")
    print(f"{'标注标签':<16} {'标注数':>6} {'预测正确':>8} {'召回率':>8}")
    print(f"{'─' * 46}")
    by_label = result["by_annotated_label"]
    for label in sorted(by_label, key=lambda k: by_label[k]["total"], reverse=True):
        info = by_label[label]
        rate = info["correct"] / info["total"] if info["total"] else 0
        print(f"{label:<16} {info['total']:>6} {info['correct']:>8} {rate:>8.1%}")

    # 各行业标签的精确率（按预测标签）
    print(f"\n{'─' * 70}")
    print(f"  按预测标签统计 — 精确率 (Precision)")
    print(f"{'─' * 70}")
    print(f"{'预测标签':<16} {'预测数':>6} {'预测正确':>8} {'精确率':>8}")
    print(f"{'─' * 46}")
    by_pred = result["by_predicted_label"]
    for label in sorted(by_pred, key=lambda k: by_pred[k]["total"], reverse=True):
        info = by_pred[label]
        rate = info["correct"] / info["total"] if info["total"] else 0
        print(f"{label:<16} {info['total']:>6} {info['correct']:>8} {rate:>8.1%}")

    # 混淆矩阵
    print(f"\n{'─' * 70}")
    print(f"  混淆矩阵 (行=真实标签, 列=预测标签)")
    print(f"{'─' * 70}")
    confusion = result["confusion"]
    all_labels = sorted(set(
        list(confusion.keys())
        + [pred for row in confusion.values() for pred in row]
    ))
    # 表头
    col_title = "真实\\预测"
    header = f"{col_title:<14}" + "".join(f"{l[:6]:>8}" for l in all_labels)
    print(header)
    for true_label in all_labels:
        row_data = confusion.get(true_label, {})
        cells = "".join(f"{row_data.get(pl, 0):>8}" for pl in all_labels)
        print(f"{true_label:<14}{cells}")

    # 按审核人统计
    print(f"\n{'─' * 70}")
    print(f"  按审核人统计")
    print(f"{'─' * 70}")
    print(f"{'审核人':<12} {'标注数':>6} {'模型正确':>8} {'准确率':>8}")
    print(f"{'─' * 40}")
    by_reviewer = result["by_reviewer"]
    for name in sorted(by_reviewer, key=lambda k: by_reviewer[k]["total"], reverse=True):
        info = by_reviewer[name]
        rate = info["correct"] / info["total"] if info["total"] else 0
        print(f"{name:<12} {info['total']:>6} {info['correct']:>8} {rate:>8.1%}")

    # 错误案例
    errors = result["errors"]
    if errors:
        print(f"\n{'─' * 70}")
        print(f"  错误案例明细 (共 {len(errors)} 条)")
        print(f"{'─' * 70}")
        print(f"{'entity_key':<28} {'预测标签':<12} {'标注标签':<12} {'审核备注'}")
        print(f"{'─' * 70}")
        for e in errors:
            notes = (e.get("reviewer_notes") or "")[:30]
            print(f"{e['entity_key']:<28} {e['predicted_label']:<12} {e['annotated_label']:<12} {notes}")

    print(f"\n{'=' * 70}")


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python analyze_annotations.py <output_dir>")
        print("示例: python analyze_annotations.py backend/output/20260421")
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    db_path = output_dir / "pipeline_results.sqlite3"

    if not db_path.exists():
        print(f"错误: 数据库文件不存在: {db_path}")
        sys.exit(1)

    pairs = _load_annotation_pairs(db_path)
    if not pairs:
        print("未找到标注数据，请先在前端完成审核标注。")
        sys.exit(0)

    result = _analyze(pairs)
    _print_report(result)

    # 深度错误分析
    error_details = _deep_analyze_errors(pairs, db_path)
    _print_error_pattern_analysis(error_details)


if __name__ == "__main__":
    main()
