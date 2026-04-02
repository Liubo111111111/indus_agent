from __future__ import annotations

from industry_classification.audit import build_audit_record
from industry_classification.graph_state import GraphState


def _publish_key(state: GraphState) -> str:
    return "::".join(
        [
            state.entity_key,
            state.feature_schema_version,
            state.taxonomy_version,
            state.graph_version,
            "fallback",
        ]
    )


class FallbackOutputWriter:
    def __init__(self, store: dict[str, dict]):
        self.store = store

    def run(self, state: GraphState) -> GraphState:
        decision = state.decision_record.model_dump() if state.decision_record is not None else None
        self.store[_publish_key(state)] = {
            "decision_record": decision,
            "error_type": state.error_type,
            "audit": build_audit_record(
                run_id=state.run_id,
                entity_key=state.entity_key,
                feature_schema_version=state.feature_schema_version,
                taxonomy_version=state.taxonomy_version,
                graph_version=state.graph_version,
                prompt_version_static=state.prompt_version_static,
                prompt_version_dynamic=state.prompt_version_dynamic,
                prompt_version_final=state.prompt_version_final,
                model_version_static=state.model_version_static,
                model_version_dynamic=state.model_version_dynamic,
                model_version_final=state.model_version_final,
                route=state.route,
            ),
        }
        return state

