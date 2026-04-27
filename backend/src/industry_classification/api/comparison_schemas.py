"""新旧标签对比评估 API 请求/响应 Pydantic 模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class CreateComparisonRequest(BaseModel):
    """创建对比评估会话请求。"""

    model_config = ConfigDict(extra="forbid")

    bizdate: str
    max_rows: int | None = None
    lookback_days: int = 1
    prompt_version_static: str = "v1"
    prompt_version_dynamic: str = "v1"
    prompt_version_final: str = "v3"


class ComparisonAccepted(BaseModel):
    """对比评估会话已接受响应（202）。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    message: str


class ComparisonStatusResponse(BaseModel):
    """对比评估运行状态。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    status: str
    dataset_size: int
    completed_count: int
    error_count: int
    diff_count: int
    annotation_count: int
    current_entity: str | None
    consistency_rate: float | None


class DiffAnalysis(BaseModel):
    """差异指标分析结果。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    dataset_size: int
    diff_count: int
    consistency_rate: float
    change_matrix: dict[str, dict[str, int]]
    change_type_ranking: list[dict]
    net_changes: dict[str, int]


class DiffRecord(BaseModel):
    """差异记录条目。"""

    model_config = ConfigDict(extra="forbid")

    entity_key: str
    enterprise_name: str
    old_label: str
    new_label: str
    confidence_level: str | None = None
    decision_reason: str | None = None
    human_label: str | None = None


class RecordsResponse(BaseModel):
    """分页记录响应。"""

    model_config = ConfigDict(extra="forbid")

    records: list[DiffRecord]
    total: int
    page: int
    page_size: int
    annotation_progress: dict


class AnnotateRequest(BaseModel):
    """提交标注请求。"""

    model_config = ConfigDict(extra="forbid")

    annotations: list[dict]
    reviewer_name: str = ""


class LabelAccuracy(BaseModel):
    """单个标签维度的精确率/召回率/F1 指标。"""

    model_config = ConfigDict(extra="forbid")

    label: str
    old_precision: float
    old_recall: float
    old_f1: float
    new_precision: float
    new_recall: float
    new_f1: float
    recommendation: str


class ComparisonReport(BaseModel):
    """对比评估报告。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    old_accuracy: float
    new_accuracy: float
    improvement: float
    coverage: float
    coverage_warning: str | None = None
    label_metrics: list[LabelAccuracy]
    old_confusion_matrix: dict[str, dict[str, int]]
    new_confusion_matrix: dict[str, dict[str, int]]
    recommendations: list[dict]


class SessionSummary(BaseModel):
    """历史会话摘要。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    bizdate: str
    prompt_version_static: str
    prompt_version_dynamic: str
    prompt_version_final: str
    dataset_size: int
    completed_count: int
    diff_count: int
    annotation_count: int
    consistency_rate: float | None
    status: str
    created_at: str
