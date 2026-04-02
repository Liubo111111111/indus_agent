from __future__ import annotations

import json

from industry_classification.audit import enforce_prompt_budget
from industry_classification.graph_state import GraphState
from industry_classification.settings import load_prompt_asset


class DynamicProfilePromptBuilder:
    def __init__(self, prompt_version: str = "v1") -> None:
        self.prompt_version = prompt_version

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
        asset = load_prompt_asset("dynamic_profile", version=self.prompt_version)
        prompt = (
            f"[TASK: dynamic_profile]\n"
            f"[SYSTEM]\n{asset.system_prompt.strip()}\n\n"
            f"[USER]\n"
            f"{asset.user_template.format(
                total_job_post_cnt_90d=payload['total_job_post_cnt_90d'],
                distinct_job_name_cnt_90d=payload['distinct_job_name_cnt_90d'],
                top_job_names_json=json.dumps(payload['top_job_names'], ensure_ascii=False, indent=2),
                jobs_recent_20_json=json.dumps(payload['jobs_recent_20'], ensure_ascii=False, indent=2),
            ).strip()}"
        )
        return prompt, payload
