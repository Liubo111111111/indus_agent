from __future__ import annotations

import time

from industry_classification.graph_state import GraphState
from industry_classification.llm.client import LLMClient
from industry_classification.nodes.final_decision.parser import FinalDecisionParser
from industry_classification.nodes.final_decision.prompt_builder import FinalDecisionPromptBuilder
from industry_classification.writers.sqlite_store import SqliteResultStore


class FinalDecisionService:
    def __init__(
        self,
        client: LLMClient,
        model_version: str,
        prompt_version: str,
        prompt_builder: FinalDecisionPromptBuilder | None = None,
        parser: FinalDecisionParser | None = None,
        sqlite_store: SqliteResultStore | None = None,
    ) -> None:
        self.client = client
        self.model_version = model_version
        self.prompt_version = prompt_version
        self.prompt_builder = prompt_builder or FinalDecisionPromptBuilder(prompt_version=prompt_version)
        self.parser = parser or FinalDecisionParser()
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
                step_name="final_decision",
                prompt_version=self.prompt_version,
                model_version=self.model_version,
                payload=payload,
                result=parsed.model_dump(),
            )
        route = "fallback" if parsed.low_confidence else "formal"
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        timing = dict(state.timing_ms or {})
        timing["final_decision"] = elapsed
        return state.model_copy(
            update={
                "decision_record": parsed,
                "route": route,
                "prompt_version_final": self.prompt_version,
                "model_version_final": self.model_version,
                "timing_ms": timing,
            }
        )
