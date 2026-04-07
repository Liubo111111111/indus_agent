from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
