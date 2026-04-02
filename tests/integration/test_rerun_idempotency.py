from industry_classification.main import run_once


class SequenceLLMClient:
    def __init__(self):
        self.calls = 0

    def complete(self, prompt: str, payload: dict) -> str:
        self.calls += 1
        if "静态候选行业" in prompt:
            return "{\"top3_labels\":[{\"label\":\"物业管理\",\"reason\":\"经营范围命中\"},{\"label\":\"安保服务\",\"reason\":\"岗位相关\"},{\"label\":\"其他\",\"reason\":\"保守候选\"}],\"summary\":\"主体偏向物业管理。\"}"
        if "动态招聘画像" in prompt:
            return "{\"core_jobs\":[\"保安\",\"保洁\"],\"scene\":\"小区和园区\",\"continuity\":\"近3个月持续招聘\",\"summary\":\"近3个月招聘持续且集中，主要围绕保安、保洁岗位，场景偏小区和园区。\"}"
        return "{\"final_label\":\"物业管理\",\"confidence_level\":\"high\",\"low_confidence\":false,\"decision_reason\":\"主体与招聘行为都指向物业管理。\",\"supporting_evidence\":[\"经营范围命中物业管理\",\"岗位集中在保安保洁\"],\"conflict_note\":null}"


def test_rerun_same_partition_reuses_cache_and_does_not_duplicate_publish():
    row = {
        "user_id": 1,
        "social_credit_code": "abc",
        "enterprise_name": "某物业公司",
        "business_scope": "物业管理、保洁服务",
        "total_job_post_cnt_90d": 12,
        "distinct_job_name_cnt_90d": 4,
        "top_job_names": [{"job_name": "保安", "cnt": 5, "ratio": 0.42}],
        "jobs_recent_20": [{"job_name": "保安", "desc": "小区秩序维护", "add_time": "2026-04-01 10:00:00"}],
        "jobs_all_90d": [{"job_name": "保安", "desc": "小区秩序维护", "add_time": "2026-04-01 10:00:00"}],
    }
    client = SequenceLLMClient()
    formal_store = {}
    fallback_store = {}
    cache_store = {}

    first = run_once(
        row_dict=row,
        run_id="rerun-1",
        client=client,
        formal_store=formal_store,
        fallback_store=fallback_store,
        cache_store=cache_store,
    )
    second = run_once(
        row_dict=row,
        run_id="rerun-2",
        client=client,
        formal_store=formal_store,
        fallback_store=fallback_store,
        cache_store=cache_store,
    )

    assert first.route == "formal"
    assert second.route == "formal"
    assert len(formal_store) == 1
    assert len(fallback_store) == 0
    assert client.calls == 3
