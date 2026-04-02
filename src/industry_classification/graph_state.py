from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from industry_classification.schemas import DecisionRecord, DynamicProfile, StaticProfile, WideRow


class GraphState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    entity_key: str
    feature_schema_version: str
    taxonomy_version: str
    graph_version: str
    prompt_version_static: str
    prompt_version_dynamic: str
    prompt_version_final: str
    model_version_static: str
    model_version_dynamic: str
    model_version_final: str
    wide_row: WideRow
    static_profile: StaticProfile | None = None
    dynamic_profile: DynamicProfile | None = None
    decision_record: DecisionRecord | None = None
    route: str = "in_progress"
    error_type: str | None = None


def build_initial_state(
    row_dict: dict,
    run_id: str,
    feature_schema_version: str,
    taxonomy_version: str,
    graph_version: str,
    prompt_version_static: str = "v1",
    prompt_version_dynamic: str = "v1",
    prompt_version_final: str = "v1",
    model_version_static: str = "unset",
    model_version_dynamic: str = "unset",
    model_version_final: str = "unset",
) -> GraphState:
    row = WideRow.model_validate(row_dict)
    return GraphState(
        run_id=run_id,
        entity_key=row.social_credit_code,
        feature_schema_version=feature_schema_version,
        taxonomy_version=taxonomy_version,
        graph_version=graph_version,
        prompt_version_static=prompt_version_static,
        prompt_version_dynamic=prompt_version_dynamic,
        prompt_version_final=prompt_version_final,
        model_version_static=model_version_static,
        model_version_dynamic=model_version_dynamic,
        model_version_final=model_version_final,
        wide_row=row,
    )

