from __future__ import annotations

from industry_classification.llm.result_handler import normalize_llm_json
from industry_classification.schemas import DynamicProfile


class DynamicProfileParser:
    def parse(self, raw_text: str) -> DynamicProfile:
        result = normalize_llm_json(raw_text, schema_name="DynamicProfile", schema_model=DynamicProfile)
        if not result.ok or result.data is None:
            raise ValueError(result.error_type or "unknown_dynamic_profile_error")
        return DynamicProfile.model_validate(result.data)

