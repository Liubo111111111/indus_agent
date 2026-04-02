import json
from pathlib import Path

from industry_classification.main import run_file_batch
from industry_classification.rate_limit import RuntimeConfig


def _fixture_path(name: str) -> Path:
    return Path(__file__).with_name("fixtures") / name


def test_run_file_batch_writes_outputs_and_keeps_rerun_idempotent(tmp_path):
    replay_cases = json.loads(_fixture_path("replay_cases.json").read_text(encoding="utf-8"))
    input_path = tmp_path / "wide_rows.jsonl"
    responses_path = tmp_path / "responses.json"
    output_dir = tmp_path / "outputs"

    input_path.write_text(
        "\n".join(
            json.dumps({"pt": "20260402", **case["row"]}, ensure_ascii=False) for case in replay_cases
        ),
        encoding="utf-8",
    )
    responses_path.write_text(
        json.dumps(
            {case["row"]["social_credit_code"]: case["responses"] for case in replay_cases},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    runtime_config = RuntimeConfig(
        worker_count=2,
        provider_rate_limit_per_minute=600,
        timeout_seconds=5,
        retry_limit=1,
        max_in_flight=2,
    )

    first_summary = run_file_batch(
        pt="20260402",
        input_path=str(input_path),
        responses_path=str(responses_path),
        output_dir=str(output_dir),
        runtime_config=runtime_config,
    )
    second_summary = run_file_batch(
        pt="20260402",
        input_path=str(input_path),
        responses_path=str(responses_path),
        output_dir=str(output_dir),
        runtime_config=runtime_config,
    )

    assert first_summary["processed_count"] == 2
    assert first_summary["formal_count"] == 1
    assert first_summary["fallback_count"] == 1
    assert second_summary["formal_count"] == 1
    assert second_summary["fallback_count"] == 1
    assert second_summary["duplicate_publish_skips"] == 0

    formal_records = [
        json.loads(line)
        for line in (output_dir / "formal_output.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    fallback_records = [
        json.loads(line)
        for line in (output_dir / "fallback_output.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(formal_records) == 1
    assert len(fallback_records) == 1
    assert formal_records[0]["final_label"] == "物业管理"
    assert fallback_records[0]["decision_record"]["final_label"] == "其他"
