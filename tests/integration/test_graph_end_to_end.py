import json
from pathlib import Path

from industry_classification.main import run_once


class SequenceLLMClient:
    def __init__(self, responses: dict[str, str]):
        self.responses = responses
        self.calls = []

    def complete(self, prompt: str, payload: dict) -> str:
        self.calls.append((prompt, payload))
        if "[TASK: final_decision]" in prompt:
            return self.responses["final"]
        if "[TASK: dynamic_profile]" in prompt:
            return self.responses["dynamic"]
        if "[TASK: static_profile]" in prompt:
            return self.responses["static"]
        raise ValueError("unrecognized_prompt_task")


def _fixture_path(name: str) -> Path:
    return Path(__file__).with_name("fixtures") / name


def test_end_to_end_routes_safe_record_to_formal_and_low_conf_to_fallback():
    replay_cases = json.loads(_fixture_path("replay_cases.json").read_text(encoding="utf-8"))
    formal_store = {}
    fallback_store = {}

    safe_case = replay_cases[0]
    client = SequenceLLMClient(safe_case["responses"])
    result = run_once(
        row_dict=safe_case["row"],
        run_id="run-safe",
        client=client,
        formal_store=formal_store,
        fallback_store=fallback_store,
    )

    assert result.route == "formal"
    assert result.decision_record is not None
    assert result.decision_record.final_label == "物业管理"
    assert len(formal_store) == 1
    assert len(fallback_store) == 0

    low_case = replay_cases[1]
    client = SequenceLLMClient(low_case["responses"])
    result = run_once(
        row_dict=low_case["row"],
        run_id="run-low",
        client=client,
        formal_store=formal_store,
        fallback_store=fallback_store,
    )

    assert result.route == "fallback"
    assert result.decision_record is not None
    assert result.decision_record.final_label == "其他"
    assert len(formal_store) == 1
    assert len(fallback_store) == 1


def test_seed_replay_suite_matches_expected_routes_and_labels():
    replay_cases = json.loads(_fixture_path("replay_cases.json").read_text(encoding="utf-8"))
    expected = json.loads(_fixture_path("replay_expected.json").read_text(encoding="utf-8"))
    formal_store = {}
    fallback_store = {}

    for idx, case in enumerate(replay_cases, start=1):
        client = SequenceLLMClient(case["responses"])
        result = run_once(
            row_dict=case["row"],
            run_id=f"replay-{idx}",
            client=client,
            formal_store=formal_store,
            fallback_store=fallback_store,
        )
        assert result.route == expected[case["name"]]["route"]
        assert result.decision_record is not None
        assert result.decision_record.final_label == expected[case["name"]]["final_label"]
