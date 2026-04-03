from industry_classification.graph_state import build_initial_state
from industry_classification.nodes.static_profile.service import StaticProfileService


class FakeLLMClient:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    def complete(self, prompt: str, payload: dict) -> str:
        self.calls.append((prompt, payload))
        return self.response


def test_static_profile_node_returns_top3_labels_and_summary():
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
          "top3_labels": [
            {"label": "物业管理", "reason": "经营范围包含物业管理"},
            {"label": "安保服务", "reason": "岗位和秩序维护相关"},
            {"label": "其他", "reason": "保守候选"}
          ],
          "summary": "主体偏向物业管理。"
        }
        """
    )
    service = StaticProfileService(client=client, model_version="mock-static-v1", prompt_version="v1")

    next_state = service.run(state)

    assert next_state.static_profile is not None
    assert len(next_state.static_profile.top3_labels) == 3
    assert next_state.static_profile.top3_labels[0].label == "物业管理"
    assert next_state.static_profile.summary == "主体偏向物业管理。"
    prompt, payload = client.calls[0]
    assert "[SYSTEM]" in prompt
    assert "[USER]" in prompt
    assert "某物业公司" in prompt
    assert "taxonomy" in payload
