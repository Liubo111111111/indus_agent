from __future__ import annotations

import argparse
import json
import threading
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from hashlib import sha256
from pathlib import Path
from typing import Any

from industry_classification.cache import build_cache_key
from industry_classification.graph_state import GraphState, build_initial_state
from industry_classification.loader import load_rows_from_file
from industry_classification.nodes.dynamic_profile.service import DynamicProfileService
from industry_classification.nodes.final_decision.service import FinalDecisionService
from industry_classification.nodes.static_profile.service import StaticProfileService
from industry_classification.rate_limit import MinuteRateLimiter, RuntimeConfig
from industry_classification.writers.fallback_output import FallbackOutputWriter
from industry_classification.writers.formal_output import FormalOutputWriter
from industry_classification.writers.jsonl_store import JsonlKeyedStore
from industry_classification.writers.sqlite_store import SqliteResultStore


def _hash_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return sha256(raw.encode("utf-8")).hexdigest()


def _cached_profile(
    cache_store: dict[str, dict] | None,
    key: str,
    compute_fn,
    cache_lock: threading.Lock | None = None,
):
    if cache_store is None:
        return compute_fn()

    if cache_lock is not None:
        with cache_lock:
            if key in cache_store:
                return cache_store[key]
        value = compute_fn()
        with cache_lock:
            return cache_store.setdefault(key, value)

    if key in cache_store:
        return cache_store[key]
    value = compute_fn()
    cache_store[key] = value
    return value


class SequenceLLMClient:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.calls = 0

    def complete(self, prompt: str, payload: dict) -> str:
        del payload
        self.calls += 1
        if "[TASK: final_decision]" in prompt:
            return self.responses["final"]
        if "[TASK: dynamic_profile]" in prompt:
            return self.responses["dynamic"]
        if "[TASK: static_profile]" in prompt:
            return self.responses["static"]
        raise ValueError("unrecognized_prompt_task")


class RateLimitedLLMClient:
    def __init__(self, client, limiter: MinuteRateLimiter) -> None:
        self.client = client
        self.limiter = limiter

    def complete(self, prompt: str, payload: dict) -> str:
        self.limiter.acquire()
        return self.client.complete(prompt, payload)


def _build_mock_client_factory(response_map: dict[str, dict[str, str]]):
    def build_client(row_dict: dict[str, Any]) -> SequenceLLMClient:
        return SequenceLLMClient(response_map[row_dict["social_credit_code"]])

    return build_client


def run_once(
    row_dict: dict,
    run_id: str,
    client,
    formal_store: dict[str, dict],
    fallback_store: dict[str, dict],
    sqlite_store: SqliteResultStore | None = None,
    sqlite_path: str | Path | None = None,
    cache_store: dict[str, dict] | None = None,
    cache_lock: threading.Lock | None = None,
    feature_schema_version: str = "v1",
    taxonomy_version: str = "v1",
    graph_version: str = "v1",
) -> GraphState:
    resolved_sqlite_store = sqlite_store
    owns_sqlite_store = False
    if resolved_sqlite_store is None and sqlite_path is not None:
        resolved_sqlite_store = SqliteResultStore(sqlite_path)
        owns_sqlite_store = True

    try:
        state = build_initial_state(
            row_dict=row_dict,
            run_id=run_id,
            feature_schema_version=feature_schema_version,
            taxonomy_version=taxonomy_version,
            graph_version=graph_version,
        )

        static_service = StaticProfileService(
            client=client,
            model_version="mock-static-v1",
            prompt_version=state.prompt_version_static,
            sqlite_store=resolved_sqlite_store,
        )
        dynamic_service = DynamicProfileService(
            client=client,
            model_version="mock-dynamic-v1",
            prompt_version=state.prompt_version_dynamic,
            sqlite_store=resolved_sqlite_store,
        )
        final_service = FinalDecisionService(
            client=client,
            model_version="mock-final-v1",
            prompt_version=state.prompt_version_final,
            sqlite_store=resolved_sqlite_store,
        )

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
            cache_lock=cache_lock,
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
            cache_lock=cache_lock,
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
            cache_lock=cache_lock,
        )

        if state.route == "formal":
            writer = FormalOutputWriter(formal_store, sqlite_store=resolved_sqlite_store)
        else:
            writer = FallbackOutputWriter(fallback_store, sqlite_store=resolved_sqlite_store)
        return writer.run(state)
    finally:
        if owns_sqlite_store and resolved_sqlite_store is not None:
            resolved_sqlite_store.close()


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


def _run_with_retry(
    row_dict: dict[str, Any],
    run_id: str,
    client_factory,
    formal_store,
    fallback_store,
    sqlite_store: SqliteResultStore | None,
    cache_store: dict[str, GraphState],
    cache_lock: threading.Lock,
    rate_limiter: MinuteRateLimiter,
    runtime_config: RuntimeConfig,
) -> GraphState:
    last_error: Exception | None = None
    for attempt in range(runtime_config.retry_limit + 1):
        try:
            client = RateLimitedLLMClient(client_factory(row_dict), rate_limiter)
            return run_once(
                row_dict=row_dict,
                run_id=run_id if attempt == 0 else f"{run_id}-retry-{attempt}",
                client=client,
                formal_store=formal_store,
                fallback_store=fallback_store,
                sqlite_store=sqlite_store,
                cache_store=cache_store,
                cache_lock=cache_lock,
            )
        except Exception as exc:  # pragma: no cover - protected by retry semantics
            last_error = exc
    assert last_error is not None
    raise last_error


def run_batch(
    rows: list[dict[str, Any]],
    pt: str,
    client_factory,
    formal_store,
    fallback_store,
    sqlite_store: SqliteResultStore | None = None,
    runtime_config: RuntimeConfig | None = None,
) -> dict[str, Any]:
    del pt
    config = runtime_config or RuntimeConfig()
    cache_store: dict[str, GraphState] = {}
    cache_lock = threading.Lock()
    limiter = MinuteRateLimiter(config.provider_rate_limit_per_minute)
    processed_count = 0
    duplicate_publish_skips = 0
    future_to_code: dict[Future[GraphState], str] = {}
    max_in_flight = max(1, min(config.max_in_flight, config.worker_count))

    def drain_one_or_more() -> None:
        nonlocal processed_count
        done, _ = wait(
            list(future_to_code),
            timeout=config.timeout_seconds,
            return_when=FIRST_COMPLETED,
        )
        if not done:
            raise TimeoutError(f"batch_timeout_after_{config.timeout_seconds}_seconds")
        for future in done:
            future.result()
            del future_to_code[future]
            processed_count += 1

    with ThreadPoolExecutor(max_workers=config.worker_count) as executor:
        for idx, row in enumerate(rows, start=1):
            while len(future_to_code) >= max_in_flight:
                drain_one_or_more()

            future = executor.submit(
                _run_with_retry,
                row,
                f"batch-{idx}",
                client_factory,
                formal_store,
                fallback_store,
                sqlite_store,
                cache_store,
                cache_lock,
                limiter,
                config,
            )
            future_to_code[future] = row["social_credit_code"]

        while future_to_code:
            drain_one_or_more()

    return {
        "processed_count": processed_count,
        "formal_count": len(formal_store),
        "fallback_count": len(fallback_store),
        "cache_entries": len(cache_store),
        "duplicate_publish_skips": duplicate_publish_skips,
        "formal_keys": sorted(formal_store.keys()),
        "fallback_keys": sorted(fallback_store.keys()),
    }


def run_file_batch(
    pt: str,
    input_path: str,
    responses_path: str,
    output_dir: str,
    runtime_config: RuntimeConfig | None = None,
) -> dict[str, Any]:
    rows = list(load_rows_from_file(input_path, pt=pt))
    responses = json.loads(Path(responses_path).read_text(encoding="utf-8"))
    formal_store = JsonlKeyedStore(Path(output_dir) / "formal_output.jsonl")
    fallback_store = JsonlKeyedStore(Path(output_dir) / "fallback_output.jsonl")
    sqlite_store = SqliteResultStore(Path(output_dir) / "pipeline_results.sqlite3")

    try:
        summary = run_batch(
            rows=rows,
            pt=pt,
            client_factory=_build_mock_client_factory(responses),
            formal_store=formal_store,
            fallback_store=fallback_store,
            sqlite_store=sqlite_store,
            runtime_config=runtime_config,
        )
    finally:
        sqlite_store.close()
    (Path(output_dir) / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Industry classification pipeline")
    parser.add_argument("--pt", required=True, help="bizdate partition in yyyymmdd")
    parser.add_argument("--mode", required=True, choices=["dry-run", "file-batch", "run", "run-single", "fetch", "fetch-run"], help="execution mode")
    parser.add_argument("--cases-path", help="optional path to dry-run cases json")
    parser.add_argument("--input-path", help="json/jsonl input path for file-batch / run mode")
    parser.add_argument("--responses-path", help="mock responses keyed by social_credit_code (file-batch only)")
    parser.add_argument("--output-dir", help="output directory", default="output")
    parser.add_argument("--format", choices=["json", "jsonl"], default="json", help="output format for fetch mode")
    parser.add_argument("--max-rows", type=int, default=100, help="max rows to fetch from ODPS")
    parser.add_argument("--worker-count", type=int, default=4)
    parser.add_argument("--provider-rate-limit-per-minute", type=int, default=120)
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--retry-limit", type=int, default=1)
    parser.add_argument("--max-in-flight", type=int, default=8)
    args = parser.parse_args(argv)
    runtime_config = RuntimeConfig(
        worker_count=args.worker_count,
        provider_rate_limit_per_minute=args.provider_rate_limit_per_minute,
        timeout_seconds=args.timeout_seconds,
        retry_limit=args.retry_limit,
        max_in_flight=args.max_in_flight,
    )

    if args.mode == "dry-run":
        summary = run_dry_run_batch(pt=args.pt, cases_path=args.cases_path)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if args.mode == "file-batch":
        if not args.input_path or not args.responses_path or not args.output_dir:
            raise ValueError("file-batch mode requires --input-path --responses-path --output-dir")
        summary = run_file_batch(
            pt=args.pt,
            input_path=args.input_path,
            responses_path=args.responses_path,
            output_dir=args.output_dir,
            runtime_config=runtime_config,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if args.mode in ("run", "run-single"):
        from industry_classification.llm.client import HttpLLMClient

        if not args.input_path:
            raise ValueError(f"{args.mode} mode requires --input-path")
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        rows = list(load_rows_from_file(args.input_path, pt=args.pt))
        if not rows:
            print("No rows matched the given --pt filter.")
            return 1

        if args.mode == "run-single":
            rows = rows[:1]

        llm_client = HttpLLMClient()
        formal_store = JsonlKeyedStore(output_dir / "formal_output.jsonl")
        fallback_store = JsonlKeyedStore(output_dir / "fallback_output.jsonl")
        sqlite_store = SqliteResultStore(output_dir / "pipeline_results.sqlite3")
        cache_store: dict[str, GraphState] = {}

        def _real_client_factory(row_dict: dict[str, Any]) -> HttpLLMClient:
            return llm_client

        try:
            summary = run_batch(
                rows=rows,
                pt=args.pt,
                client_factory=_real_client_factory,
                formal_store=formal_store,
                fallback_store=fallback_store,
                sqlite_store=sqlite_store,
                runtime_config=runtime_config,
            )
        finally:
            sqlite_store.close()
        (output_dir / "run_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        llm_client.close()
        return 0

    if args.mode == "fetch":
        from industry_classification.data_fetcher import fetch_and_convert

        json_path = fetch_and_convert(
            pt=args.pt,
            output_dir=args.output_dir,
            format=args.format,
            max_rows=args.max_rows,
        )
        print(f"数据已准备: {json_path}")
        return 0

    if args.mode == "fetch-run":
        from industry_classification.data_fetcher import fetch_and_convert
        from industry_classification.llm.client import HttpLLMClient

        output_dir = Path(args.output_dir)
        json_path = fetch_and_convert(
            pt=args.pt,
            output_dir=output_dir / "data",
            format="json",
            max_rows=args.max_rows,
        )
        print(f"数据拉取完成: {json_path}")

        rows = list(load_rows_from_file(str(json_path)))
        if not rows:
            print("拉取到的数据为空，无法运行分类。")
            return 1

        llm_client = HttpLLMClient()
        formal_store = JsonlKeyedStore(output_dir / "formal_output.jsonl")
        fallback_store = JsonlKeyedStore(output_dir / "fallback_output.jsonl")
        sqlite_store = SqliteResultStore(output_dir / "pipeline_results.sqlite3")

        def _real_client_factory(row_dict: dict[str, Any]) -> HttpLLMClient:
            return llm_client

        try:
            summary = run_batch(
                rows=rows,
                pt=args.pt,
                client_factory=_real_client_factory,
                formal_store=formal_store,
                fallback_store=fallback_store,
                sqlite_store=sqlite_store,
                runtime_config=runtime_config,
            )
        finally:
            sqlite_store.close()
        (output_dir / "run_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        llm_client.close()
        return 0

    raise ValueError(f"unsupported mode: {args.mode}")


if __name__ == "__main__":
    raise SystemExit(main())
