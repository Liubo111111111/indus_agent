from __future__ import annotations

from industry_classification.graph_state import GraphState
from industry_classification.llm.client import LLMClient
from industry_classification.nodes.dynamic_profile.parser import DynamicProfileParser
from industry_classification.nodes.dynamic_profile.prompt_builder import DynamicProfilePromptBuilder


class DynamicProfileService:
    def __init__(
        self,
        client: LLMClient,
        model_version: str,
        prompt_version: str,
        prompt_builder: DynamicProfilePromptBuilder | None = None,
        parser: DynamicProfileParser | None = None,
    ) -> None:
        self.client = client
        self.model_version = model_version
        self.prompt_version = prompt_version
        self.prompt_builder = prompt_builder or DynamicProfilePromptBuilder()
        self.parser = parser or DynamicProfileParser()

    def run(self, state: GraphState) -> GraphState:
        prompt, payload = self.prompt_builder.build(state)
        raw = self.client.complete(prompt, payload)
        parsed = self.parser.parse(raw)
        return state.model_copy(
            update={
                "dynamic_profile": parsed,
                "prompt_version_dynamic": self.prompt_version,
                "model_version_dynamic": self.model_version,
            }
        )

