from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from industry_classification.cache import build_cache_key
from industry_classification.graph_state import GraphState, build_initial_state
from industry_classification.nodes.dynamic_profile.service import DynamicProfileService
from industry_classification.nodes.final_decision.service import FinalDecisionService
from industry_classification.nodes.static_profile.service import StaticProfileService
from industry_classification.writers.fallback_output import FallbackOutputWriter
from industry_classification.writers.formal_output import FormalOutputWriter


def _hash_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return sha256(raw.encode("utf-8")).hexdigest()


def _cached_profile(
    cache_store: dict[str, dict] | None,
    key: str,
    compute_fn,
):
    if cache_store is not None and key in cache_store:
        return cache_store[key]
    value = compute_fn()
    if cache_store is not None:
        cache_store[key] = value
    return value


class SequenceLLMClient:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.calls = 0

    def complete(self, prompt: str, payload: dict) -> str:
        del payload
        self.calls += 1
        if "静态候选行业" in prompt:
            return self.responses["static"]
        if "动态招聘画像" in prompt:
            return self.responses["dynamic"]
        return self.responses["final"]


def run_once(
    row_dict: dict,
    run_id: str,
    client,
    formal_store: dict[str, dict],
    fallback_store: dict[str, dict],
    cache_store: dict[str, dict] | None = None,
    feature_schema_version: str = "v1",
    taxonomy_version: str = "v1",
    graph_version: str = "v1",
) -> GraphState:
    state = build_initial_state(
        row_dict=row_dict,
        run_id=run_id,
        feature_schema_version=feature_schema_version,
        taxonomy_version=taxonomy_version,
        graph_version=graph_version,
    )

    static_service = StaticProfileService(client=client, model_version="mock-static-v1", prompt_version="v1")
    dynamic_service = DynamicProfileService(client=client, model_version="mock-dynamic-v1", prompt_version="v1")
    final_service = FinalDecisionService(client=client, model_version="mock-final-v1", prompt_version="v1")

    static_key = build_cache_key(
        entity_key=state.entity_key,
        input_hash=_hash_payload(
            {
                "enterprise_name": state.wide_row.enterprise_name,
                "business_scope": state.wide_row.business_scope,
            }
        ),
        graph_version=state.graph_version,
        taxonomy_version=state.taxonomy_version,
        prompt_version=state.prompt_version_static,
        model_version="mock-static-v1",
    )
    state = _cached_profile(
        cache_store,
        static_key,
        lambda: static_service.run(state),
    )

    dynamic_key = build_cache_key(
        entity_key=state.entity_key,
        input_hash=_hash_payload(
            {
                "top_job_names": [item.model_dump() for item in state.wide_row.top_job_names],
                "jobs_recent_20": [item.model_dump() for item in state.wide_row.jobs_recent_20],
            }
        ),
        graph_version=state.graph_version,
        taxonomy_version=state.taxonomy_version,
        prompt_version=state.prompt_version_dynamic,
        model_version="mock-dynamic-v1",
    )
    state = _cached_profile(
        cache_store,
        dynamic_key,
        lambda: dynamic_service.run(state),
    )

    final_key = build_cache_key(
        entity_key=state.entity_key,
        input_hash=_hash_payload(
            {
                "static_profile": state.static_profile.model_dump() if state.static_profile else None,
                "dynamic_profile": state.dynamic_profile.model_dump() if state.dynamic_profile else None,
            }
        ),
        graph_version=state.graph_version,
        taxonomy_version=state.taxonomy_version,
        prompt_version=state.prompt_version_final,
        model_version="mock-final-v1",
    )
    state = _cached_profile(
        cache_store,
        final_key,
        lambda: final_service.run(state),
    )

    if state.route == "formal":
        writer = FormalOutputWriter(formal_store)
    else:
        writer = FallbackOutputWriter(fallback_store)
    return writer.run(state)


def _default_dry_run_cases_path() -> Path:
    return Path(__file__).with_name("sample_dry_run_cases.json")


def run_dry_run_batch(pt: str, cases_path: str | None = None) -> dict[str, Any]:
    del pt
    fixture_path = Path(cases_path) if cases_path else _default_dry_run_cases_path()
    replay_cases = json.loads(fixture_path.read_text(encoding="utf-8"))

    formal_store: dict[str, dict] = {}
    fallback_store: dict[str, dict] = {}
    cache_store: dict[str, GraphState] = {}
    total_llm_calls = 0

    for idx, case in enumerate(replay_cases, start=1):
        client = SequenceLLMClient(case["responses"])
        run_once(
            row_dict=case["row"],
            run_id=f"dry-run-{idx}",
            client=client,
            formal_store=formal_store,
            fallback_store=fallback_store,
            cache_store=cache_store,
        )
        total_llm_calls += client.calls

    if replay_cases:
        rerun_client = SequenceLLMClient(replay_cases[0]["responses"])
        run_once(
            row_dict=replay_cases[0]["row"],
            run_id="dry-run-rerun",
            client=rerun_client,
            formal_store=formal_store,
            fallback_store=fallback_store,
            cache_store=cache_store,
        )
        total_llm_calls += rerun_client.calls

    return {
        "formal_count": len(formal_store),
        "fallback_count": len(fallback_store),
        "cache_entries": len(cache_store),
        "llm_calls": total_llm_calls,
        "formal_keys": sorted(formal_store.keys()),
        "fallback_keys": sorted(fallback_store.keys()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Industry classification pipeline")
    parser.add_argument("--pt", required=True, help="bizdate partition in yyyymmdd")
    parser.add_argument("--mode", required=True, choices=["dry-run"], help="execution mode")
    parser.add_argument("--cases-path", help="optional path to dry-run cases json")
    args = parser.parse_args(argv)

    if args.mode == "dry-run":
        summary = run_dry_run_batch(pt=args.pt, cases_path=args.cases_path)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    raise ValueError(f"unsupported mode: {args.mode}")


if __name__ == "__main__":
    raise SystemExit(main())
