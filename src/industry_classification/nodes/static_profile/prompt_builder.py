from __future__ import annotations

from industry_classification.graph_state import GraphState
from industry_classification.settings import load_taxonomy


class StaticProfilePromptBuilder:
    def build(self, state: GraphState) -> tuple[str, dict]:
        taxonomy = load_taxonomy()
        payload = {
            "enterprise_name": state.wide_row.enterprise_name,
            "business_scope": state.wide_row.business_scope,
            "taxonomy": [
                {
                    "label": label.display_name,
                    "prompt_text": label.prompt_text,
                }
                for label in taxonomy.labels
                if label.enabled
            ],
        }
        prompt = (
            "基于企业名称和经营范围，输出最多3个静态候选行业及其原因，"
            "并给出一句静态主体倾向总结。"
        )
        return prompt, payload

