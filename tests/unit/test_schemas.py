from industry_classification.graph_state import build_initial_state


def test_build_initial_state_sets_required_versions():
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
    assert state.run_id == "run-1"
    assert state.feature_schema_version == "v1"
    assert state.taxonomy_version == "v1"
    assert state.graph_version == "v1"
