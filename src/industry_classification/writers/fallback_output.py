from __future__ import annotations

from industry_classification.audit import build_audit_record
from industry_classification.graph_state import GraphState
from industry_classification.writers.sqlite_store import SqliteResultStore


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
    def __init__(self, store: dict[str, dict], sqlite_store: SqliteResultStore | None = None):
        self.store = store
        self.sqlite_store = sqlite_store

    def run(self, state: GraphState) -> GraphState:
        decision = state.decision_record.model_dump() if state.decision_record is not None else None
        publish_key = _publish_key(state)
        record = {
            "enterprise_name": state.wide_row.enterprise_name,
            "business_scope": state.wide_row.business_scope,
            "decision_record": decision,
            "error_type": state.error_type,
            "static_profile": state.static_profile.model_dump() if state.static_profile else None,
            "dynamic_profile": state.dynamic_profile.model_dump() if state.dynamic_profile else None,
            "timing_ms": state.timing_ms,
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
        self.store[publish_key] = record
        if self.sqlite_store is not None:
            self.sqlite_store.upsert_run(state)
            self.sqlite_store.upsert_published_record(
                publish_key=publish_key,
                run_id=state.run_id,
                entity_key=state.entity_key,
                route="fallback",
                record=record,
            )
        return state
