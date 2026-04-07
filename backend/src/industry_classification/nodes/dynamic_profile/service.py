from __future__ import annotations

import time

from industry_classification.graph_state import GraphState
from industry_classification.llm.client import LLMClient
from industry_classification.nodes.dynamic_profile.parser import DynamicProfileParser
from industry_classification.nodes.dynamic_profile.prompt_builder import DynamicProfilePromptBuilder
from industry_classification.writers.sqlite_store import SqliteResultStore


class DynamicProfileService:
    def __init__(
        self,
        client: LLMClient,
        model_version: str,
        prompt_version: str,
        prompt_builder: DynamicProfilePromptBuilder | None = None,
        parser: DynamicProfileParser | None = None,
        sqlite_store: SqliteResultStore | None = None,
    ) -> None:
        self.client = client
        self.model_version = model_version
        self.prompt_version = prompt_version
        self.prompt_builder = prompt_builder or DynamicProfilePromptBuilder(prompt_version=prompt_version)
        self.parser = parser or DynamicProfileParser()
        self.sqlite_store = sqlite_store

    def run(self, state: GraphState) -> GraphState:
        t0 = time.perf_counter()
        prompt, payload = self.prompt_builder.build(state)
        raw = self.client.complete(prompt, payload)
        parsed = self.parser.parse(raw)
        if self.sqlite_store is not None:
            self.sqlite_store.upsert_step(
                run_id=state.run_id,
                entity_key=state.entity_key,
                step_name="dynamic_profile",
                prompt_version=self.prompt_version,
                model_version=self.model_version,
                payload=payload,
                result=parsed.model_dump(),
            )
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        timing = dict(state.timing_ms or {})
        timing["dynamic_profile"] = elapsed
        return state.model_copy(
            update={
                "dynamic_profile": parsed,
                "prompt_version_dynamic": self.prompt_version,
                "model_version_dynamic": self.model_version,
                "timing_ms": timing,
            }
        )
