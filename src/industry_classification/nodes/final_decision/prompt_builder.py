from __future__ import annotations

from industry_classification.audit import enforce_prompt_budget
from industry_classification.graph_state import GraphState
from industry_classification.settings import load_taxonomy


class FinalDecisionPromptBuilder:
    def build(self, state: GraphState) -> tuple[str, dict]:
        if state.static_profile is None or state.dynamic_profile is None:
            raise ValueError("final_decision_requires_profiles")

        taxonomy = load_taxonomy()
        payload = {
            "enterprise_name": state.wide_row.enterprise_name,
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
        prompt = (
            "基于静态画像、动态画像和行业定义，做11选1行业裁决，"
            "输出最终标签、置信度、原因和支持证据。"
        )
        return prompt, payload

