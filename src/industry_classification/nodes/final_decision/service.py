from __future__ import annotations

from industry_classification.graph_state import GraphState
from industry_classification.llm.client import LLMClient
from industry_classification.nodes.final_decision.parser import FinalDecisionParser
from industry_classification.nodes.final_decision.prompt_builder import FinalDecisionPromptBuilder


class FinalDecisionService:
    def __init__(
        self,
        client: LLMClient,
        model_version: str,
        prompt_version: str,
        prompt_builder: FinalDecisionPromptBuilder | None = None,
        parser: FinalDecisionParser | None = None,
    ) -> None:
        self.client = client
        self.model_version = model_version
        self.prompt_version = prompt_version
        self.prompt_builder = prompt_builder or FinalDecisionPromptBuilder()
        self.parser = parser or FinalDecisionParser()

    def run(self, state: GraphState) -> GraphState:
        prompt, payload = self.prompt_builder.build(state)
        raw = self.client.complete(prompt, payload)
        parsed = self.parser.parse(raw)
        route = "fallback" if parsed.low_confidence else "formal"
        return state.model_copy(
            update={
                "decision_record": parsed,
                "route": route,
                "prompt_version_final": self.prompt_version,
                "model_version_final": self.model_version,
            }
        )
