"""回溯测试 API 请求/响应 Pydantic 模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BacktestRunRequest(BaseModel):
    """启动回溯测试请求。"""

    model_config = ConfigDict(extra="forbid")

    pt_dates: list[str]  # e.g. ["20250101", "20250115", "20250201"]
    prompt_version_static: str = "v1"
    prompt_version_dynamic: str = "v1"
    prompt_version_final: str = "v2"


class BacktestRunAccepted(BaseModel):
    """回溯测试已接受响应（202）。"""

    model_config = ConfigDict(extra="forbid")

    backtest_run_id: str
    message: str
    dataset_size: int


class BacktestStatusResponse(BaseModel):
    """回溯测试运行状态。"""

    model_config = ConfigDict(extra="forbid")

    backtest_run_id: str
    status: str  # pending / running / done / error
    dataset_size: int
    completed_count: int
    error_count: int
    current_entity: str | None
    accuracy: float | None


class LabelMetricsResponse(BaseModel):
    """单个标签的精确率/召回率/F1 指标。"""

    model_config = ConfigDict(extra="forbid")

    label: str
    precision: float
    recall: float
    f1: float
    support: int


class MisclassifiedItem(BaseModel):
    """错误分类明细条目。"""

    model_config = ConfigDict(extra="forbid")

    entity_key: str
    enterprise_name: str
    annotated_label: str
    predicted_label: str
    confidence_level: str | None


class BacktestResultDetail(BaseModel):
    """回溯结果逐条明细（企业名称 | 原模型标签 | 人工标注 | 新预测标签）。"""

    model_config = ConfigDict(extra="forbid")

    entity_key: str
    enterprise_name: str
    original_label: str | None
    annotated_label: str
    predicted_label: str | None
    confidence_level: str | None
    error_type: str | None
    match: bool  # predicted == annotated


class AccuracyReportResponse(BaseModel):
    """准确率报告响应。"""

    model_config = ConfigDict(extra="forbid")

    backtest_run_id: str
    accuracy: float
    original_accuracy: float | None  # 原模型标签 vs 人工标注的准确率
    total: int
    correct: int
    error_count: int
    label_metrics: list[LabelMetricsResponse] = Field(default_factory=list)
    confusion_matrix: dict[str, dict[str, int]] = Field(default_factory=dict)
    # 原模型指标（基于 original_label vs annotated_label）
    original_correct: int = 0
    original_label_metrics: list[LabelMetricsResponse] = Field(default_factory=list)
    original_confusion_matrix: dict[str, dict[str, int]] = Field(default_factory=dict)
    misclassified: list[MisclassifiedItem] = Field(default_factory=list)
    details: list[BacktestResultDetail] = Field(default_factory=list)


class BacktestRunSummary(BaseModel):
    """历史运行列表中的运行摘要。"""

    model_config = ConfigDict(extra="forbid")

    backtest_run_id: str
    prompt_version_static: str
    prompt_version_dynamic: str
    prompt_version_final: str
    pt_dates: list[str] = Field(default_factory=list)
    dataset_size: int
    accuracy: float | None
    status: str
    created_at: str


class FlipItem(BaseModel):
    """翻转明细条目：两次运行中分类结果发生变化的企业。"""

    model_config = ConfigDict(extra="forbid")

    entity_key: str
    enterprise_name: str
    annotated_label: str
    label_a: str
    label_b: str
    direction: str  # "improved" / "degraded" / "changed"


class ComparisonResponse(BaseModel):
    """两次回溯运行对比响应。"""

    model_config = ConfigDict(extra="forbid")

    run_a: BacktestRunSummary
    run_b: BacktestRunSummary
    accuracy_diff: float
    label_metrics_diff: list[dict] = Field(default_factory=list)
    flips: list[FlipItem] = Field(default_factory=list)
    confusion_matrix_a: dict[str, dict[str, int]] = Field(default_factory=dict)
    confusion_matrix_b: dict[str, dict[str, int]] = Field(default_factory=dict)


class AnnotationDatasetSummary(BaseModel):
    """标注数据集摘要。"""

    model_config = ConfigDict(extra="forbid")

    total: int
    label_distribution: dict[str, int] = Field(default_factory=dict)
    entities: list[dict] = Field(default_factory=list)  # 简要列表
