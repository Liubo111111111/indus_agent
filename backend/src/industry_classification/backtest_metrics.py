"""回溯测试指标计算纯函数模块。

所有函数均为纯函数，无副作用、无 I/O。
输入为 list[dict]，每条记录包含:
  - annotated_label: str
  - predicted_label: str
  - error_type: str | None
  - entity_key: str
  - enterprise_name: str
  - confidence_level: str | None
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field


@dataclass
class LabelMetrics:
    """单个标签的精确率/召回率/F1 指标。"""

    label: str
    precision: float
    recall: float
    f1: float
    support: int  # 该标签的标注样本数


@dataclass
class AccuracyReport:
    """准确率报告，组合所有指标。"""

    accuracy: float
    total: int
    correct: int
    error_count: int
    label_metrics: list[LabelMetrics] = field(default_factory=list)
    confusion_matrix: dict[str, dict[str, int]] = field(default_factory=dict)
    misclassified: list[dict] = field(default_factory=list)


def _is_valid(record: dict) -> bool:
    """判断记录是否有效（error_type 为 falsy）。"""
    return not record.get("error_type")


def calculate_accuracy(results: list[dict]) -> float:
    """计算整体准确率。

    排除 error_type 非空的记录，计算 annotated == predicted 的比例。
    无有效记录时返回 0.0。
    """
    valid = [r for r in results if _is_valid(r)]
    if not valid:
        return 0.0
    correct = sum(
        1 for r in valid if r["annotated_label"] == r["predicted_label"]
    )
    return correct / len(valid)


def calculate_label_metrics(results: list[dict]) -> list[LabelMetrics]:
    """对每个标签计算 precision、recall、f1、support。

    仅使用有效记录（error_type 为 falsy）。
    返回按标签名排序的 LabelMetrics 列表。
    """
    valid = [r for r in results if _is_valid(r)]
    if not valid:
        return []

    # 收集所有出现过的标签（标注侧 + 预测侧）
    all_labels: set[str] = set()
    for r in valid:
        all_labels.add(r["annotated_label"])
        all_labels.add(r["predicted_label"])

    metrics: list[LabelMetrics] = []
    for label in sorted(all_labels):
        tp = sum(
            1
            for r in valid
            if r["annotated_label"] == label and r["predicted_label"] == label
        )
        fp = sum(
            1
            for r in valid
            if r["annotated_label"] != label and r["predicted_label"] == label
        )
        fn = sum(
            1
            for r in valid
            if r["annotated_label"] == label and r["predicted_label"] != label
        )
        support = tp + fn  # 该标签的标注样本数

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        denom = precision + recall
        f1 = 2 * precision * recall / denom if denom > 0 else 0.0

        metrics.append(
            LabelMetrics(
                label=label,
                precision=precision,
                recall=recall,
                f1=f1,
                support=support,
            )
        )

    return metrics


def build_confusion_matrix(results: list[dict]) -> dict[str, dict[str, int]]:
    """生成混淆矩阵 {annotated: {predicted: count}}。

    仅使用有效记录（error_type 为 falsy）。
    使用 collections.defaultdict 构建。
    """
    valid = [r for r in results if _is_valid(r)]

    matrix: dict[str, dict[str, int]] = collections.defaultdict(
        lambda: collections.defaultdict(int)
    )
    for r in valid:
        matrix[r["annotated_label"]][r["predicted_label"]] += 1

    # 转换为普通 dict 以便序列化
    return {k: dict(v) for k, v in matrix.items()}


def build_accuracy_report(results: list[dict]) -> AccuracyReport:
    """组合所有指标函数，返回完整的 AccuracyReport。"""
    valid = [r for r in results if _is_valid(r)]
    error_count = len(results) - len(valid)

    correct = sum(
        1 for r in valid if r["annotated_label"] == r["predicted_label"]
    )

    # 错误分类明细：有效记录中 annotated != predicted 的条目
    misclassified = [
        {
            "entity_key": r["entity_key"],
            "enterprise_name": r["enterprise_name"],
            "annotated_label": r["annotated_label"],
            "predicted_label": r["predicted_label"],
            "confidence_level": r.get("confidence_level"),
        }
        for r in valid
        if r["annotated_label"] != r["predicted_label"]
    ]

    return AccuracyReport(
        accuracy=calculate_accuracy(results),
        total=len(valid),
        correct=correct,
        error_count=error_count,
        label_metrics=calculate_label_metrics(results),
        confusion_matrix=build_confusion_matrix(results),
        misclassified=misclassified,
    )


@dataclass
class FlipDetail:
    """两次运行间单条企业的预测标签翻转明细。"""

    entity_key: str
    enterprise_name: str
    annotated_label: str
    label_a: str
    label_b: str
    direction: str  # "improved" / "degraded" / "changed"


@dataclass
class ComparisonReport:
    """两次回溯运行的对比报告。"""

    accuracy_a: float
    accuracy_b: float
    accuracy_diff: float  # accuracy_b - accuracy_a
    label_metrics_a: list[LabelMetrics] = field(default_factory=list)
    label_metrics_b: list[LabelMetrics] = field(default_factory=list)
    label_metrics_diff: list[dict] = field(default_factory=list)
    flips: list[FlipDetail] = field(default_factory=list)
    confusion_matrix_a: dict[str, dict[str, int]] = field(default_factory=dict)
    confusion_matrix_b: dict[str, dict[str, int]] = field(default_factory=dict)


def compare_runs(
    results_a: list[dict], results_b: list[dict]
) -> ComparisonReport:
    """对比两次回溯运行的结果，计算准确率差异、标签指标差异和翻转明细。

    两组结果通过 entity_key 匹配，仅对两者共有且均有效的记录计算翻转。

    翻转方向判定:
      - improved:  label_a != annotated 且 label_b == annotated（错误→正确）
      - degraded:  label_a == annotated 且 label_b != annotated（正确→错误）
      - changed:   label_a != annotated 且 label_b != annotated 且 label_a != label_b
                   （错误→错误但标签不同）
    """
    # 1. 准确率
    accuracy_a = calculate_accuracy(results_a)
    accuracy_b = calculate_accuracy(results_b)

    # 2. 标签指标
    label_metrics_a = calculate_label_metrics(results_a)
    label_metrics_b = calculate_label_metrics(results_b)

    # 3. 混淆矩阵
    confusion_matrix_a = build_confusion_matrix(results_a)
    confusion_matrix_b = build_confusion_matrix(results_b)

    # 4. 标签指标差异：按标签名对齐，计算 precision/recall/f1 差值
    metrics_a_map = {m.label: m for m in label_metrics_a}
    metrics_b_map = {m.label: m for m in label_metrics_b}
    all_labels = sorted(set(metrics_a_map) | set(metrics_b_map))

    label_metrics_diff: list[dict] = []
    for label in all_labels:
        m_a = metrics_a_map.get(label)
        m_b = metrics_b_map.get(label)
        p_a = m_a.precision if m_a else 0.0
        p_b = m_b.precision if m_b else 0.0
        r_a = m_a.recall if m_a else 0.0
        r_b = m_b.recall if m_b else 0.0
        f1_a = m_a.f1 if m_a else 0.0
        f1_b = m_b.f1 if m_b else 0.0
        label_metrics_diff.append(
            {
                "label": label,
                "precision_diff": p_b - p_a,
                "recall_diff": r_b - r_a,
                "f1_diff": f1_b - f1_a,
            }
        )

    # 5. 翻转明细：按 entity_key 匹配，仅考虑两组中均有效的记录
    valid_a_map: dict[str, dict] = {}
    for r in results_a:
        if _is_valid(r):
            valid_a_map[r["entity_key"]] = r

    valid_b_map: dict[str, dict] = {}
    for r in results_b:
        if _is_valid(r):
            valid_b_map[r["entity_key"]] = r

    common_keys = set(valid_a_map) & set(valid_b_map)

    flips: list[FlipDetail] = []
    for key in sorted(common_keys):
        r_a = valid_a_map[key]
        r_b = valid_b_map[key]
        label_a = r_a["predicted_label"]
        label_b = r_b["predicted_label"]

        if label_a == label_b:
            continue  # 预测未变化，不算翻转

        annotated = r_a["annotated_label"]

        if label_a != annotated and label_b == annotated:
            direction = "improved"
        elif label_a == annotated and label_b != annotated:
            direction = "degraded"
        else:
            # label_a != annotated 且 label_b != annotated 且 label_a != label_b
            direction = "changed"

        flips.append(
            FlipDetail(
                entity_key=key,
                enterprise_name=r_a.get("enterprise_name", ""),
                annotated_label=annotated,
                label_a=label_a,
                label_b=label_b,
                direction=direction,
            )
        )

    return ComparisonReport(
        accuracy_a=accuracy_a,
        accuracy_b=accuracy_b,
        accuracy_diff=accuracy_b - accuracy_a,
        label_metrics_a=label_metrics_a,
        label_metrics_b=label_metrics_b,
        label_metrics_diff=label_metrics_diff,
        flips=flips,
        confusion_matrix_a=confusion_matrix_a,
        confusion_matrix_b=confusion_matrix_b,
    )
