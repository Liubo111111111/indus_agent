from __future__ import annotations

from dataclasses import replace

from industry_classification.graph_state import GraphState
from industry_classification.llm.client import LLMClient
from industry_classification.nodes.static_profile.parser import StaticProfileParser
from industry_classification.nodes.static_profile.prompt_builder import StaticProfilePromptBuilder


class StaticProfileService:
    def __init__(
        self,
        client: LLMClient,
        model_version: str,
        prompt_version: str,
        prompt_builder: StaticProfilePromptBuilder | None = None,
        parser: StaticProfileParser | None = None,
    ) -> None:
        self.client = client
        self.model_version = model_version
        self.prompt_version = prompt_version
        self.prompt_builder = prompt_builder or StaticProfilePromptBuilder()
        self.parser = parser or StaticProfileParser()

    def run(self, state: GraphState) -> GraphState:
        prompt, payload = self.prompt_builder.build(state)
        raw = self.client.complete(prompt, payload)
        parsed = self.parser.parse(raw)
        return state.model_copy(
            update={
                "static_profile": parsed,
                "prompt_version_static": self.prompt_version,
                "model_version_static": self.model_version,
            }
        )

