from industry_classification.graph import build_graph


def test_low_confidence_routes_to_fallback_branch():
    graph = build_graph()
    result = graph.invoke(
        {
            "run_id": "run-1",
            "entity_key": "abc",
            "feature_schema_version": "v1",
            "taxonomy_version": "v1",
            "graph_version": "v1",
            "prompt_version_static": "v1",
            "prompt_version_dynamic": "v1",
            "prompt_version_final": "v1",
            "model_version_static": "m1",
            "model_version_dynamic": "m1",
            "model_version_final": "m1",
            "wide_row": {
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
            "decision_record": {
                "final_label": "其他",
                "confidence_level": "low",
                "low_confidence": True,
                "decision_reason": "证据不足",
                "supporting_evidence": [],
                "conflict_note": None,
            },
            "route": "in_progress",
            "error_type": None,
        }
    )
    assert result["route"] == "fallback"
