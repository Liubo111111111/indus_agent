from industry_classification.graph_state import build_initial_state
from industry_classification.nodes.dynamic_profile.service import DynamicProfileService


class FakeLLMClient:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    def complete(self, prompt: str, payload: dict) -> str:
        self.calls.append((prompt, payload))
        return self.response


def test_dynamic_profile_node_uses_bounded_summary_fields_only():
    state = build_initial_state(
        row_dict={
            "user_id": 1,
            "social_credit_code": "abc",
            "enterprise_name": "某物业公司",
            "business_scope": "物业管理、保洁服务",
            "total_job_post_cnt_90d": 12,
            "distinct_job_name_cnt_90d": 4,
            "top_job_names": [{"job_name": "保安", "cnt": 5, "ratio": 0.42}],
            "jobs_recent_20": [{"job_name": "保安", "desc": "小区秩序维护", "add_time": "2026-04-01 10:00:00"}],
        },
        run_id="run-1",
        feature_schema_version="v1",
        taxonomy_version="v1",
        graph_version="v1",
    )
    client = FakeLLMClient(
        """
        {
          "core_jobs": ["保安", "保洁"],
          "scene": "小区和园区",
          "continuity": "近3个月持续招聘",
          "summary": "近3个月招聘持续且集中，主要围绕保安、保洁岗位，场景偏小区和园区。"
        }
        """
    )
    service = DynamicProfileService(client=client, model_version="mock-dynamic-v1", prompt_version="v1")

    next_state = service.run(state)

    assert next_state.dynamic_profile is not None
    assert next_state.dynamic_profile.core_jobs == ["保安", "保洁"]
    prompt, payload = client.calls[0]
    assert "[SYSTEM]" in prompt
    assert "[USER]" in prompt
    assert "保安" in prompt
    assert "jobs_all_90d" not in payload
    assert "top_job_names" in payload
    assert "jobs_recent_20" in payload
