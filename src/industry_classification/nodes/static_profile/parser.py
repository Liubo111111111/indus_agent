from __future__ import annotations

from industry_classification.llm.result_handler import normalize_llm_json
from industry_classification.schemas import StaticProfile


class StaticProfileParser:
    def parse(self, raw_text: str) -> StaticProfile:
        result = normalize_llm_json(raw_text, schema_name="StaticProfile", schema_model=StaticProfile)
        if not result.ok or result.data is None:
            raise ValueError(result.error_type or "unknown_static_profile_error")
        return StaticProfile.model_validate(result.data)

