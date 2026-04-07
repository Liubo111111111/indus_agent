from __future__ import annotations

import json

from industry_classification.audit import enforce_prompt_budget
from industry_classification.graph_state import GraphState
from industry_classification.settings import load_prompt_asset, load_taxonomy


class FinalDecisionPromptBuilder:
    def __init__(self, prompt_version: str = "v1") -> None:
        self.prompt_version = prompt_version

    def build(self, state: GraphState) -> tuple[str, dict]:
        if state.static_profile is None or state.dynamic_profile is None:
            raise ValueError("final_decision_requires_profiles")

        taxonomy = load_taxonomy()
        payload = {
            "enterprise_name": state.wide_row.enterprise_name,
            "authentication_time": state.wide_row.authentication_time or "无",
            "latest_publish_time": state.wide_row.latest_publish_time or "无",
            "latest_publish_job_names": state.wide_row.latest_publish_job_names,
            "static_summary": state.static_profile.summary,
            "static_top3_labels": [item.model_dump() for item in state.static_profile.top3_labels],
            "dynamic_summary": state.dynamic_profile.summary,
            "dynamic_core_jobs": state.dynamic_profile.core_jobs,
            "dynamic_scene": state.dynamic_profile.scene,
            "dynamic_continuity": state.dynamic_profile.continuity,
            "taxonomy": [
                {
                    "label": label.display_name,
                    "prompt_text": label.prompt_text,
                }
                for label in taxonomy.labels
                if label.enabled
            ],
        }
        budget = enforce_prompt_budget("final_decision", payload)
        if not budget.allowed:
            raise ValueError(budget.reason or "final_prompt_budget_rejected")
        asset = load_prompt_asset("final_decision", version=self.prompt_version)
        user_content = asset.user_template.format(
            enterprise_name=state.wide_row.enterprise_name,
            authentication_time=payload['authentication_time'],
            latest_publish_time=payload['latest_publish_time'],
            latest_publish_job_names_json=json.dumps(payload['latest_publish_job_names'], ensure_ascii=False),
            static_summary=state.static_profile.summary,
            static_top3_labels_json=json.dumps(payload['static_top3_labels'], ensure_ascii=False, indent=2),
            dynamic_summary=state.dynamic_profile.summary,
            dynamic_core_jobs_json=json.dumps(payload['dynamic_core_jobs'], ensure_ascii=False, indent=2),
            dynamic_scene=state.dynamic_profile.scene,
            dynamic_continuity=state.dynamic_profile.continuity,
            taxonomy_json=json.dumps(payload['taxonomy'], ensure_ascii=False, indent=2),
        ).strip()
        prompt = (
            f"[TASK: final_decision]\n"
            f"[SYSTEM]\n{asset.system_prompt.strip()}\n\n"
            f"[USER]\n"
            f"{user_content}"
        )
        return prompt, payload
