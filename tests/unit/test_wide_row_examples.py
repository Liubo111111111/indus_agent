from industry_classification.schemas import WideRow
from pydantic import ValidationError


def test_wide_row_accepts_expected_contract():
    row = {
        "user_id": 1,
        "social_credit_code": "abc",
        "enterprise_name": "某物业公司",
        "business_scope": "物业管理、保洁服务",
        "total_job_post_cnt_90d": 12,
        "distinct_job_name_cnt_90d": 4,
        "top_job_names": [
            {"job_name": "保安", "cnt": 5, "ratio": 0.42},
        ],
        "jobs_recent_20": [
            {"job_name": "保安", "desc": "小区秩序维护", "add_time": "2026-04-01 10:00:00"},
        ],
        "latest_publish_time": "2026-04-01",
        "latest_publish_job_names": ["保安"],
        "authentication_time": "2025-06-15",
    }
    assert WideRow.model_validate(row).enterprise_name == "某物业公司"


def test_wide_row_rejects_legacy_jobs_all_90d_field():
    row = {
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
        "jobs_all_90d": [{"job_name": "保安", "desc": "小区秩序维护", "add_time": "2026-04-01 10:00:00"}],
    }

    try:
        WideRow.model_validate(row)
    except ValidationError as exc:
        assert "jobs_all_90d" in str(exc)
    else:
        raise AssertionError("WideRow unexpectedly accepted legacy jobs_all_90d field")
