from __future__ import annotations

from pydantic import BaseModel, Field


# --- 统计 ---


class StatsResponse(BaseModel):
    total_processed: int
    annotated_count: int = 0
    unannotated_count: int = 0
    label_distribution: dict[str, int] = Field(default_factory=dict)


# --- 运行记录 ---


class RunSummary(BaseModel):
    """列表中的运行记录摘要"""

    run_id: str
    entity_key: str  # social_credit_code
    enterprise_name: str
    final_label: str | None
    confidence_level: str | None  # "high" / "medium" / "low"
    route: str  # "formal" / "fallback"
    error_type: str | None
    timestamp: str | None  # 来自 audit 记录
    annotations: list[dict] = Field(default_factory=list)
    annotation: dict | None = None


class PaginatedRunList(BaseModel):
    items: list[RunSummary]
    total: int
    offset: int
    limit: int


class RunDetail(BaseModel):
    """单条运行记录完整详情"""

    run_id: str
    entity_key: str
    enterprise_name: str
    business_scope: str
    wide_row: dict  # 完整 WideRow 数据
    static_profile: dict | None
    dynamic_profile: dict | None
    decision_record: dict | None
    route: str
    error_type: str | None
    audit: dict  # 完整审计元数据
    timing_ms: dict | None = None  # 各阶段耗时(毫秒)
    annotations: list[dict] = Field(default_factory=list)


# --- 搜索 ---


class SearchResult(BaseModel):
    entity_key: str
    enterprise_name: str
    final_label: str | None
    route: str
    run_id: str


# --- 批量任务 ---


class BatchRequest(BaseModel):
    pt: str  # 业务日期 yyyymmdd
    input_path: str
    worker_count: int = Field(default=4, ge=1, le=32)
    provider_rate_limit_per_minute: int = Field(default=120, ge=1)
    max_in_flight: int = Field(default=8, ge=1)


class BatchAccepted(BaseModel):
    task_id: str
    message: str
    status: str = "accepted"


# --- Fallback / 审核 ---


class FallbackRecord(BaseModel):
    entity_key: str
    enterprise_name: str
    final_label: str | None
    confidence_level: str | None
    error_type: str | None
    decision_record: dict | None
    audit: dict


class PaginatedFallbackList(BaseModel):
    items: list[FallbackRecord]
    total: int
    offset: int
    limit: int


class ReviewRequest(BaseModel):
    approved_label: str
    reviewer_notes: str = ""


class ReviewResponse(BaseModel):
    entity_key: str
    approved_label: str
    status: str = "approved"


class AnnotationRequest(BaseModel):
    annotated_label: str
    reviewer_notes: str = ""
    reviewer_name: str = ""


class AnnotationResponse(BaseModel):
    run_id: str
    annotated_label: str
    status: str = "annotated"
    annotation_count: int = 1


# --- Auth ---


class AuthUserResponse(BaseModel):
    open_id: str
    name: str = ""
    en_name: str = ""
    avatar_url: str = ""
    email: str = ""
    enterprise_email: str = ""
    user_id: str = ""
    tenant_key: str = ""
    is_admin: bool = False


class AuthSessionResponse(BaseModel):
    enabled: bool
    authenticated: bool
    access_denied: bool = False
    request_status: str | None = None
    user: AuthUserResponse | None = None
    login_url: str | None = None


class AdminOverviewResponse(BaseModel):
    auth_enabled: bool
    admin_mode: str
    access_scope: str
    frontend_base_url: str
    redirect_uri: str
    host_consistent: bool
    allowed_open_id_count: int
    allowed_email_count: int
    admin_open_id_count: int
    admin_email_count: int
    warnings: list[str] = Field(default_factory=list)


class AccessSettingsResponse(BaseModel):
    allowed_open_ids: list[str] = Field(default_factory=list)
    allowed_emails: list[str] = Field(default_factory=list)
    admin_open_ids: list[str] = Field(default_factory=list)
    admin_emails: list[str] = Field(default_factory=list)


class AccessSettingsUpdate(BaseModel):
    allowed_open_ids: list[str] = Field(default_factory=list)
    allowed_emails: list[str] = Field(default_factory=list)
    admin_open_ids: list[str] = Field(default_factory=list)
    admin_emails: list[str] = Field(default_factory=list)


class AdminAuthAuditEventResponse(BaseModel):
    event_type: str
    open_id: str
    name: str = ""
    email: str = ""
    enterprise_email: str = ""
    user_id: str = ""
    tenant_key: str = ""
    is_admin: bool = False
    created_at: str


class AdminAuthAuditUserResponse(BaseModel):
    open_id: str
    name: str = ""
    email: str = ""
    enterprise_email: str = ""
    user_id: str = ""
    tenant_key: str = ""
    is_admin: bool = False
    last_event_type: str
    last_event_at: str
    event_count: int


class AdminAuthAuditResponse(BaseModel):
    events: list[AdminAuthAuditEventResponse] = Field(default_factory=list)
    users: list[AdminAuthAuditUserResponse] = Field(default_factory=list)


# --- Taxonomy ---


class TaxonomyLabelDTO(BaseModel):
    id: str
    display_name: str
    short_description: str
    prompt_text: str
    enabled: bool


class TaxonomyResponse(BaseModel):
    version: str
    labels: list[TaxonomyLabelDTO]


# --- 系统配置 ---


class SettingsResponse(BaseModel):
    llm_model: str
    llm_timeout_sec: int
    llm_max_retry: int
    worker_count: int
    provider_rate_limit_per_minute: int
    max_in_flight: int


class SettingsUpdate(BaseModel):
    llm_model: str | None = None
    llm_timeout_sec: int | None = Field(default=None, ge=1)
    llm_max_retry: int | None = Field(default=None, ge=0)
    worker_count: int | None = Field(default=None, ge=1, le=32)
    provider_rate_limit_per_minute: int | None = Field(default=None, ge=1)
    max_in_flight: int | None = Field(default=None, ge=1)


# --- 分类任务 ---


class ClassifySingleRequest(BaseModel):
    """单条分类请求：输入企业名称或信用代码"""
    query: str = Field(..., min_length=1, description="企业名称或统一社会信用代码")
    pt: str = Field(default="", description="业务日期分区 yyyymmdd，为空则使用最新分区")


class ClassifyByJobNameRequest(BaseModel):
    """按工种批量分类请求"""
    job_name: str = Field(..., min_length=1, description="工种名称，用于模糊匹配")
    pt: str = Field(default="", description="业务日期分区 yyyymmdd，为空则使用最新分区")


class ClassifyBatchUploadAccepted(BaseModel):
    task_id: str
    message: str
    total_rows: int
    status: str = "accepted"


# --- 任务状态追踪 ---


class TaskStageStatus(BaseModel):
    name: str
    status: str = "pending"  # pending | running | done | error
    elapsed_ms: float | None = None
    message: str = ""


class TaskStatus(BaseModel):
    task_id: str
    status: str = "pending"  # pending | running | done | error
    stages: list[TaskStageStatus] = []
    result_run_id: str | None = None
    error: str | None = None
