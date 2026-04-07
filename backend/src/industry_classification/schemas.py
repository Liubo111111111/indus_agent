from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# 所有可能的 error_type 枚举值
ErrorType = Literal[
    "parse_error",                   # LLM 返回非 JSON，解析失败
    "schema_validation_error",       # JSON 结构不符合 Pydantic schema
    "unknown_static_profile_error",  # 静态画像节点未知异常
    "unknown_dynamic_profile_error", # 动态画像节点未知异常
    "unknown_final_decision_error",  # 最终裁决节点未知异常
]


class JobFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_name: str
    desc: str = ""
    add_time: str


class TopJobStat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_name: str
    cnt: int = Field(ge=0)
    ratio: float = Field(ge=0.0, le=1.0)


class WideRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: int
    social_credit_code: str
    enterprise_name: str
    business_scope: str = ""
    total_job_post_cnt_90d: int = Field(ge=0)
    distinct_job_name_cnt_90d: int = Field(ge=0)
    top_job_names: list[TopJobStat] = Field(default_factory=list)
    jobs_recent_20: list[JobFact] = Field(default_factory=list)
    latest_publish_time: str | None = None
    latest_publish_job_names: list[str] = Field(default_factory=list)
    authentication_time: str | None = None


class LabelReason(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    reason: str


class StaticProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top3_labels: list[LabelReason] = Field(default_factory=list, max_length=3)
    summary: str


class DynamicProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    core_jobs: list[str] = Field(default_factory=list)
    scene: str
    continuity: str
    summary: str


class DecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    final_label: str
    confidence_level: Literal["high", "medium", "low"]
    low_confidence: bool
    decision_reason: str
    supporting_evidence: list[str] = Field(default_factory=list)
    conflict_note: str | None = None
