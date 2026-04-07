from __future__ import annotations

from industry_classification.llm.result_handler import normalize_llm_json
from industry_classification.schemas import DecisionRecord


class FinalDecisionParser:
    def parse(self, raw_text: str) -> DecisionRecord:
        result = normalize_llm_json(raw_text, schema_name="DecisionRecord", schema_model=DecisionRecord)
        if not result.ok or result.data is None:
            raise ValueError(result.error_type or "unknown_final_decision_error")
        return DecisionRecord.model_validate(result.data)

