from industry_classification.llm.result_handler import normalize_llm_json


def test_normalize_llm_json_returns_fallback_on_invalid_payload():
    result = normalize_llm_json("not-json", schema_name="StaticProfile")
    assert result.ok is False
    assert result.error_type == "parse_error"

