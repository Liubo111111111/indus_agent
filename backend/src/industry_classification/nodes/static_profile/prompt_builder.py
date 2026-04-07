from __future__ import annotations

import json

from industry_classification.graph_state import GraphState
from industry_classification.settings import load_prompt_asset, load_taxonomy


class StaticProfilePromptBuilder:
    def __init__(self, prompt_version: str = "v1") -> None:
        self.prompt_version = prompt_version

    def build(self, state: GraphState) -> tuple[str, dict]:
        taxonomy = load_taxonomy()
        payload = {
            "enterprise_name": state.wide_row.enterprise_name,
            "business_scope": state.wide_row.business_scope,
            "authentication_time": state.wide_row.authentication_time or "无",
            "taxonomy": [
                {
                    "label": label.display_name,
                    "prompt_text": label.prompt_text,
                }
                for label in taxonomy.labels
                if label.enabled
            ],
        }
        asset = load_prompt_asset("static_profile", version=self.prompt_version)
        prompt = (
            f"[TASK: static_profile]\n"
            f"[SYSTEM]\n{asset.system_prompt.strip()}\n\n"
            f"[USER]\n"
            f"{asset.user_template.format(
                enterprise_name=state.wide_row.enterprise_name,
                business_scope=state.wide_row.business_scope or '无',
                authentication_time=payload['authentication_time'],
                taxonomy_json=json.dumps(payload['taxonomy'], ensure_ascii=False, indent=2),
            ).strip()}"
        )
        return prompt, payload
