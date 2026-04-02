from __future__ import annotations

from industry_classification.audit import enforce_prompt_budget
from industry_classification.graph_state import GraphState


class DynamicProfilePromptBuilder:
    def build(self, state: GraphState) -> tuple[str, dict]:
        payload = {
            "total_job_post_cnt_90d": state.wide_row.total_job_post_cnt_90d,
            "distinct_job_name_cnt_90d": state.wide_row.distinct_job_name_cnt_90d,
            "top_job_names": [item.model_dump() for item in state.wide_row.top_job_names],
            "jobs_recent_20": [item.model_dump() for item in state.wide_row.jobs_recent_20],
        }
        budget = enforce_prompt_budget("dynamic_profile", payload)
        if not budget.allowed:
            raise ValueError(budget.reason or "dynamic_prompt_budget_rejected")
        prompt = (
            "基于近90天岗位统计和近30天招聘样本，总结主岗位、持续性、场景，"
            "输出动态招聘画像。"
        )
        return prompt, payload

