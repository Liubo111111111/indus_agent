from industry_classification.audit import enforce_prompt_budget


def test_prompt_budget_rejects_raw_90d_payload_for_final_decision():
    payload = {"summary": "ok", "jobs_all_90d": [{"job_name": "保安"}]}
    result = enforce_prompt_budget("final_decision", payload)
    assert result.allowed is False
    assert result.reason == "raw_90d_payload_forbidden"

