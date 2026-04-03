import json
import sqlite3
from pathlib import Path

from industry_classification.main import run_once


class SequenceLLMClient:
    def __init__(self, responses: dict[str, str]):
        self.responses = responses

    def complete(self, prompt: str, payload: dict) -> str:
        del payload
        if "[TASK: final_decision]" in prompt:
            return self.responses["final"]
        if "[TASK: dynamic_profile]" in prompt:
            return self.responses["dynamic"]
        if "[TASK: static_profile]" in prompt:
            return self.responses["static"]
        raise ValueError("unrecognized_prompt_task")


def _fixture_path(name: str) -> Path:
    return Path(__file__).with_name("fixtures") / name


def test_run_once_persists_all_json_fields_to_sqlite_for_formal_route(tmp_path: Path):
    replay_cases = json.loads(_fixture_path("replay_cases.json").read_text(encoding="utf-8"))
    safe_case = replay_cases[0]
    sqlite_path = tmp_path / "pipeline_results.sqlite3"

    result = run_once(
        row_dict=safe_case["row"],
        run_id="sqlite-formal",
        client=SequenceLLMClient(safe_case["responses"]),
        formal_store={},
        fallback_store={},
        sqlite_path=sqlite_path,
    )

    assert result.route == "formal"

    conn = sqlite3.connect(sqlite_path)
    try:
        run_row = conn.execute(
            "select route, wide_row_json, timing_ms_json from pipeline_runs where run_id = ?",
            ("sqlite-formal",),
        ).fetchone()
        assert run_row is not None
        assert run_row[0] == "formal"
        assert json.loads(run_row[1])["enterprise_name"] == safe_case["row"]["enterprise_name"]
        assert "final_decision" in json.loads(run_row[2])

        steps = conn.execute(
            "select step_name, payload_json, result_json from inference_steps where run_id = ? order by step_name",
            ("sqlite-formal",),
        ).fetchall()
        assert [row[0] for row in steps] == [
            "dynamic_profile",
            "final_decision",
            "static_profile",
        ]

        final_step = next(row for row in steps if row[0] == "final_decision")
        final_payload = json.loads(final_step[1])
        final_result = json.loads(final_step[2])
        assert {
            "authentication_time",
            "dynamic_continuity",
            "dynamic_core_jobs",
            "dynamic_scene",
            "dynamic_summary",
            "enterprise_name",
            "latest_publish_time",
            "latest_publish_job_names",
            "static_summary",
            "static_top3_labels",
            "taxonomy",
        }.issubset(set(final_payload))
        assert set(final_result) == {
            "confidence_level",
            "conflict_note",
            "decision_reason",
            "final_label",
            "low_confidence",
            "supporting_evidence",
        }

        publish_row = conn.execute(
            "select route, record_json from published_records where run_id = ?",
            ("sqlite-formal",),
        ).fetchone()
        assert publish_row is not None
        assert publish_row[0] == "formal"
        published = json.loads(publish_row[1])
        assert {
            "audit",
            "confidence_level",
            "decision_reason",
            "dynamic_profile",
            "final_label",
            "static_profile",
            "supporting_evidence",
            "timing_ms",
        }.issubset(set(published))
    finally:
        conn.close()


def test_run_once_persists_all_json_fields_to_sqlite_for_fallback_route(tmp_path: Path):
    replay_cases = json.loads(_fixture_path("replay_cases.json").read_text(encoding="utf-8"))
    low_case = replay_cases[1]
    sqlite_path = tmp_path / "pipeline_results.sqlite3"

    result = run_once(
        row_dict=low_case["row"],
        run_id="sqlite-fallback",
        client=SequenceLLMClient(low_case["responses"]),
        formal_store={},
        fallback_store={},
        sqlite_path=sqlite_path,
    )

    assert result.route == "fallback"

    conn = sqlite3.connect(sqlite_path)
    try:
        publish_row = conn.execute(
            "select route, record_json from published_records where run_id = ?",
            ("sqlite-fallback",),
        ).fetchone()
        assert publish_row is not None
        assert publish_row[0] == "fallback"
        published = json.loads(publish_row[1])
        assert {
            "audit",
            "decision_record",
            "dynamic_profile",
            "error_type",
            "static_profile",
            "timing_ms",
        }.issubset(set(published))

        final_step = conn.execute(
            "select result_json from inference_steps where run_id = ? and step_name = ?",
            ("sqlite-fallback", "final_decision"),
        ).fetchone()
        assert final_step is not None
        assert json.loads(final_step[0])["low_confidence"] is True
    finally:
        conn.close()
