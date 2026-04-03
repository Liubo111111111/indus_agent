from industry_classification.graph_state import build_initial_state
from industry_classification.nodes.final_decision.service import FinalDecisionService
from industry_classification.schemas import DynamicProfile, LabelReason, StaticProfile


class FakeLLMClient:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    def complete(self, prompt: str, payload: dict) -> str:
        self.calls.append((prompt, payload))
        return self.response


def test_final_decision_node_outputs_label_confidence_reason_and_route():
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
            "latest_publish_time": "2026-04-01",
            "latest_publish_job_names": ["保安"],
            "authentication_time": "2025-06-15",
        },
        run_id="run-1",
        feature_schema_version="v1",
        taxonomy_version="v1",
        graph_version="v1",
    )
    state.static_profile = StaticProfile(
        top3_labels=[
            LabelReason(label="物业管理", reason="主体信息命中"),
            LabelReason(label="安保服务", reason="岗位相关"),
            LabelReason(label="其他", reason="保守候选"),
        ],
        summary="主体偏向物业管理。",
    )
    state.dynamic_profile = DynamicProfile(
        core_jobs=["保安", "保洁"],
        scene="小区和园区",
        continuity="近3个月持续招聘",
        summary="近3个月招聘持续且集中，主要围绕保安、保洁岗位，场景偏小区和园区。",
    )
    client = FakeLLMClient(
        """
        {
          "final_label": "物业管理",
          "confidence_level": "high",
          "low_confidence": false,
          "decision_reason": "主体与招聘行为都指向物业管理。",
          "supporting_evidence": ["主体经营范围包含物业管理", "招聘岗位集中在保安和保洁"],
          "conflict_note": null
        }
        """
    )
    service = FinalDecisionService(client=client, model_version="mock-final-v1", prompt_version="v1")

    next_state = service.run(state)

    assert next_state.decision_record is not None
    assert next_state.decision_record.final_label == "物业管理"
    assert next_state.decision_record.confidence_level == "high"
    assert next_state.route == "formal"
    prompt, payload = client.calls[0]
    assert "[SYSTEM]" in prompt
    assert "[USER]" in prompt
    assert "主体偏向物业管理" in prompt
    assert "taxonomy" in payload
