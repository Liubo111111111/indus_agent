# Industry Classification V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a LangGraph-based V1 pipeline that classifies each enterprise into exactly one of 11 industry labels from SQL wide-table input, writes formal output for safe results, routes low-confidence/error cases to fallback output, and records a reproducible audit trail.

**Architecture:** The system is an offline batch pipeline. SQL produces a stable wide table with enterprise static data, 90-day job statistics, recent samples, and 90-day raw facts. Python loads rows into a versioned `GraphState`, runs a LangGraph with `static_profile -> dynamic_profile -> final_decision`, validates all LLM outputs through a shared handler, publishes only the safe branch to the formal output table, and writes the low-confidence/error branch to a review/fallback table.

**Tech Stack:** ODPS SQL, Python 3.11+, LangGraph, Pydantic or dataclasses+validation, Pytest, YAML/JSON taxonomy config, LLM provider SDK.

## Data Flow Diagram

```text
ODPS Wide Table
    |
    v
[Batch Loader]
    |
    v
[GraphState Builder] ---> schema/version validation
    |
    v
[Static Profile Node] ---> service / prompt-builder / parser
    |
    v
[Dynamic Profile Node] ---> service / prompt-builder / parser
    |
    v
[Final Decision Node] ---> service / prompt-builder / parser
    |
    +----------------------------+
    |                            |
    v                            v
[Formal Output Writer]     [Fallback Output Writer]

Sidecars on every run:
- audit metadata
- version-aware cache
- prompt budget enforcement
- shared llm_result_handler
```

## Proposed File Layout

```text
sql/
  build_enterprise_industry_wide_table.sql

src/industry_classification/
  __init__.py
  settings.py
  schemas.py
  taxonomy_config.yaml
  graph.py
  graph_state.py
  loader.py
  audit.py
  cache.py
  rate_limit.py
  llm/
    client.py
    result_handler.py
  nodes/
    static_profile/
      service.py
      prompt_builder.py
      parser.py
    dynamic_profile/
      service.py
      prompt_builder.py
      parser.py
    final_decision/
      service.py
      prompt_builder.py
      parser.py
  writers/
    formal_output.py
    fallback_output.py
  main.py

tests/
  unit/
    test_schemas.py
    test_taxonomy_config.py
    test_llm_result_handler.py
    test_graph_routing.py
    test_prompt_budget.py
    test_cache.py
  integration/
    test_static_profile_node.py
    test_dynamic_profile_node.py
    test_final_decision_node.py
    test_graph_end_to_end.py
    test_rerun_idempotency.py
    fixtures/
      replay_cases.json
      replay_expected.json
```

## Execution Order

1. Fix SQL shape first.
2. Lock schemas and taxonomy config.
3. Build LangGraph skeleton and routing.
4. Add shared runtime rails: audit, cache, prompt budget, rate limiting, result handling.
5. Implement nodes one by one with TDD.
6. Implement writers and batch entrypoint.
7. Build replay suite and full test coverage.
8. Run dry-run batch and document launch checklist.

## Task 1: Replace `feature_json` with a real wide-table contract

**Files:**
- Create: `sql/build_enterprise_industry_wide_table.sql`
- Reference: `提取数据集.sql`
- Test: `tests/unit/test_wide_row_examples.py`

**Step 1: Write the failing test**

Create `tests/unit/test_wide_row_examples.py` with a fixture-based schema assertion:

```python
from industry_classification.schemas import WideRow


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
        "jobs_all_90d": [
            {"job_name": "保安", "desc": "小区秩序维护", "add_time": "2026-04-01 10:00:00"},
        ],
    }
    assert WideRow.model_validate(row).enterprise_name == "某物业公司"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_wide_row_examples.py -v`
Expected: FAIL because `industry_classification.schemas` does not exist yet.

**Step 3: Write minimal implementation**

Create `sql/build_enterprise_industry_wide_table.sql` with these output columns:
- `user_id`
- `social_credit_code`
- `enterprise_name`
- `business_scope`
- `total_job_post_cnt_90d`
- `distinct_job_name_cnt_90d`
- `top_job_names_json`
- `jobs_recent_20_json`
- `jobs_all_90d_json`
- `pt`

Rules:
- Remove hardcoded upstream partitions like `pt = '20210807'`.
- Keep 90-day full facts for replay only.
- Precompute top-10 job stats and recent-20 samples in SQL.
- Do not keep only one opaque `feature_json`.

**Step 4: Run test to verify schema fixture still fails for the right reason**

Run: `pytest tests/unit/test_wide_row_examples.py -v`
Expected: FAIL on missing `WideRow` until Task 2.

**Step 5: Sanity-check SQL contract**

Review output columns in `sql/build_enterprise_industry_wide_table.sql` and verify they exactly match the future `WideRow` schema.

## Task 2: Define the core schemas and versioned state contract

**Files:**
- Create: `src/industry_classification/schemas.py`
- Create: `src/industry_classification/graph_state.py`
- Test: `tests/unit/test_schemas.py`

**Step 1: Write the failing test**

Create `tests/unit/test_schemas.py`:

```python
from industry_classification.graph_state import build_initial_state


def test_build_initial_state_sets_required_versions():
    state = build_initial_state(
        row_dict={...},
        run_id="run-1",
        feature_schema_version="v1",
        taxonomy_version="v1",
        graph_version="v1",
    )
    assert state.run_id == "run-1"
    assert state.feature_schema_version == "v1"
    assert state.taxonomy_version == "v1"
    assert state.graph_version == "v1"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_schemas.py -v`
Expected: FAIL because `graph_state.py` does not exist.

**Step 3: Write minimal implementation**

In `src/industry_classification/schemas.py`, define:
- `JobFact`
- `TopJobStat`
- `WideRow`
- `StaticProfile`
- `DynamicProfile`
- `DecisionRecord`

In `src/industry_classification/graph_state.py`, define `GraphState` with:
- `run_id`
- `entity_key`
- `feature_schema_version`
- `taxonomy_version`
- `graph_version`
- `prompt_version_static`
- `prompt_version_dynamic`
- `prompt_version_final`
- `model_version_static`
- `model_version_dynamic`
- `model_version_final`
- `wide_row`
- `static_profile | None`
- `dynamic_profile | None`
- `decision_record | None`
- `route`
- `error_type | None`

**Step 4: Run tests**

Run: `pytest tests/unit/test_schemas.py tests/unit/test_wide_row_examples.py -v`
Expected: PASS

**Step 5: Commit**

If working in git:
```bash
git add sql/build_enterprise_industry_wide_table.sql src/industry_classification/schemas.py src/industry_classification/graph_state.py tests/unit/test_schemas.py tests/unit/test_wide_row_examples.py
git commit -m "feat: add wide-row and graph state schemas"
```

## Task 3: Add single-source taxonomy configuration

**Files:**
- Create: `src/industry_classification/taxonomy_config.yaml`
- Test: `tests/unit/test_taxonomy_config.py`

**Step 1: Write the failing test**

```python
from industry_classification.settings import load_taxonomy


def test_taxonomy_contains_all_11_labels_once():
    taxonomy = load_taxonomy()
    assert len(taxonomy.labels) == 11
    assert taxonomy.labels.count("其他") == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_taxonomy_config.py -v`
Expected: FAIL because loader/config is missing.

**Step 3: Write minimal implementation**

Create `taxonomy_config.yaml` with:
- label id
- display name
- short description
- prompt text block
- enabled flag

Create `src/industry_classification/settings.py` with a loader that validates the config and returns one in-memory structure shared by all prompt-builders.

**Step 4: Run tests**

Run: `pytest tests/unit/test_taxonomy_config.py -v`
Expected: PASS

**Step 5: Commit**

If working in git:
```bash
git add src/industry_classification/taxonomy_config.yaml src/industry_classification/settings.py tests/unit/test_taxonomy_config.py
git commit -m "feat: add taxonomy single source of truth"
```

## Task 4: Build the shared LLM result handler

**Files:**
- Create: `src/industry_classification/llm/result_handler.py`
- Test: `tests/unit/test_llm_result_handler.py`

**Step 1: Write the failing test**

```python
from industry_classification.llm.result_handler import normalize_llm_json


def test_normalize_llm_json_returns_fallback_on_invalid_payload():
    result = normalize_llm_json("not-json", schema_name="StaticProfile")
    assert result.ok is False
    assert result.error_type == "parse_error"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_llm_result_handler.py -v`
Expected: FAIL because handler does not exist.

**Step 3: Write minimal implementation**

Implement one shared handler that does:
- JSON parse
- optional JSON repair attempt
- schema validation
- error classification
- retry eligibility flag
- fallback record creation for graph routing

**Step 4: Run tests**

Run: `pytest tests/unit/test_llm_result_handler.py -v`
Expected: PASS

**Step 5: Commit**

If working in git:
```bash
git add src/industry_classification/llm/result_handler.py tests/unit/test_llm_result_handler.py
git commit -m "feat: add shared llm result handler"
```

## Task 5: Implement prompt budget contract and version-aware cache

**Files:**
- Create: `src/industry_classification/cache.py`
- Create: `src/industry_classification/audit.py`
- Test: `tests/unit/test_prompt_budget.py`
- Test: `tests/unit/test_cache.py`

**Step 1: Write the failing tests**

```python
def test_prompt_budget_rejects_raw_90d_payload_for_final_decision():
    ...


def test_cache_key_changes_when_taxonomy_version_changes():
    ...
```

**Step 2: Run tests to verify failure**

Run: `pytest tests/unit/test_prompt_budget.py tests/unit/test_cache.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Implement:
- prompt input builders that only consume bounded summary fields
- cache key builder using `entity_key + input_hash + graph_version + taxonomy_version + prompt_version + model_version`
- audit record builder that persists reproducibility metadata

**Step 4: Run tests**

Run: `pytest tests/unit/test_prompt_budget.py tests/unit/test_cache.py -v`
Expected: PASS

**Step 5: Commit**

If working in git:
```bash
git add src/industry_classification/cache.py src/industry_classification/audit.py tests/unit/test_prompt_budget.py tests/unit/test_cache.py
git commit -m "feat: add prompt budget and cache contracts"
```

## Task 6: Implement the LangGraph skeleton and routing

**Files:**
- Create: `src/industry_classification/graph.py`
- Test: `tests/unit/test_graph_routing.py`

**Step 1: Write the failing test**

```python
from industry_classification.graph import build_graph


def test_low_confidence_routes_to_fallback_branch():
    graph = build_graph()
    result = graph.invoke({...})
    assert result["route"] == "fallback"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_graph_routing.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Build a graph with nodes:
- `static_profile`
- `dynamic_profile`
- `final_decision`
- `formal_output`
- `fallback_output`

Routing rules:
- parser/model error -> fallback
- explicit `low_confidence` -> fallback
- safe decision -> formal output

**Step 4: Run tests**

Run: `pytest tests/unit/test_graph_routing.py -v`
Expected: PASS

**Step 5: Commit**

If working in git:
```bash
git add src/industry_classification/graph.py tests/unit/test_graph_routing.py
git commit -m "feat: add graph routing skeleton"
```

## Task 7: Implement the static profile node stack

**Files:**
- Create: `src/industry_classification/nodes/static_profile/service.py`
- Create: `src/industry_classification/nodes/static_profile/prompt_builder.py`
- Create: `src/industry_classification/nodes/static_profile/parser.py`
- Test: `tests/integration/test_static_profile_node.py`

**Step 1: Write the failing integration test**

```python
def test_static_profile_node_returns_top3_labels_and_summary():
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_static_profile_node.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Implement:
- prompt-builder using only enterprise name, business scope, taxonomy config
- parser emitting `StaticProfile`
- service calling client + shared result handler

**Step 4: Run tests**

Run: `pytest tests/integration/test_static_profile_node.py -v`
Expected: PASS

**Step 5: Commit**

If working in git:
```bash
git add src/industry_classification/nodes/static_profile tests/integration/test_static_profile_node.py
git commit -m "feat: add static profile node"
```

## Task 8: Implement the dynamic profile node stack

**Files:**
- Create: `src/industry_classification/nodes/dynamic_profile/service.py`
- Create: `src/industry_classification/nodes/dynamic_profile/prompt_builder.py`
- Create: `src/industry_classification/nodes/dynamic_profile/parser.py`
- Test: `tests/integration/test_dynamic_profile_node.py`

**Step 1: Write the failing integration test**

```python
def test_dynamic_profile_node_uses_bounded_summary_fields_only():
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_dynamic_profile_node.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Implement:
- prompt-builder using `top_job_names`, `jobs_recent_20`, selected summaries, not raw full 90-day payload
- parser emitting `DynamicProfile`
- service calling client + shared result handler

**Step 4: Run tests**

Run: `pytest tests/integration/test_dynamic_profile_node.py -v`
Expected: PASS

**Step 5: Commit**

If working in git:
```bash
git add src/industry_classification/nodes/dynamic_profile tests/integration/test_dynamic_profile_node.py
git commit -m "feat: add dynamic profile node"
```

## Task 9: Implement the final decision node stack

**Files:**
- Create: `src/industry_classification/nodes/final_decision/service.py`
- Create: `src/industry_classification/nodes/final_decision/prompt_builder.py`
- Create: `src/industry_classification/nodes/final_decision/parser.py`
- Test: `tests/integration/test_final_decision_node.py`

**Step 1: Write the failing integration test**

```python
def test_final_decision_node_outputs_label_confidence_reason_and_route():
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_final_decision_node.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Implement:
- prompt-builder using `StaticProfile`, `DynamicProfile`, taxonomy config, bounded summaries
- parser emitting `DecisionRecord`
- service calling client + shared result handler
- route rules:
  - `low_confidence=True` -> fallback
  - parse/model failure -> fallback
  - safe decision -> formal

**Step 4: Run tests**

Run: `pytest tests/integration/test_final_decision_node.py -v`
Expected: PASS

**Step 5: Commit**

If working in git:
```bash
git add src/industry_classification/nodes/final_decision tests/integration/test_final_decision_node.py
git commit -m "feat: add final decision node"
```

## Task 10: Implement formal and fallback writers

**Files:**
- Create: `src/industry_classification/writers/formal_output.py`
- Create: `src/industry_classification/writers/fallback_output.py`
- Test: `tests/integration/test_graph_end_to_end.py`

**Step 1: Write the failing integration test**

```python
def test_end_to_end_routes_safe_record_to_formal_and_low_conf_to_fallback():
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_graph_end_to_end.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Formal output writer must persist:
- final label
- reason
- confidence
- audit metadata

Fallback output writer must persist:
- same audit metadata
- error type or low-confidence reason
- enough replay context to debug without rerunning raw upstream reads

**Step 4: Run tests**

Run: `pytest tests/integration/test_graph_end_to_end.py -v`
Expected: PASS

**Step 5: Commit**

If working in git:
```bash
git add src/industry_classification/writers tests/integration/test_graph_end_to_end.py
git commit -m "feat: add formal and fallback writers"
```

## Task 11: Add batch loader, runtime controls, and entrypoint

**Files:**
- Create: `src/industry_classification/loader.py`
- Create: `src/industry_classification/rate_limit.py`
- Create: `src/industry_classification/main.py`
- Test: `tests/integration/test_rerun_idempotency.py`

**Step 1: Write the failing integration test**

```python
def test_rerun_same_partition_reuses_cache_and_does_not_duplicate_publish():
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_rerun_idempotency.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Implement:
- batch loader from wide table
- bounded worker pool
- provider rate limiter
- backpressure
- node timeout budget
- retry budget
- idempotent publish logic

**Step 4: Run tests**

Run: `pytest tests/integration/test_rerun_idempotency.py -v`
Expected: PASS

**Step 5: Commit**

If working in git:
```bash
git add src/industry_classification/loader.py src/industry_classification/rate_limit.py src/industry_classification/main.py tests/integration/test_rerun_idempotency.py
git commit -m "feat: add batch runtime and idempotent rerun controls"
```

## Task 12: Build the seed replay suite and prelaunch gate

**Files:**
- Create: `tests/integration/fixtures/replay_cases.json`
- Create: `tests/integration/fixtures/replay_expected.json`
- Modify: `tests/integration/test_graph_end_to_end.py`

**Step 1: Write the failing replay test**

```python
def test_seed_replay_suite_matches_expected_routes_and_labels():
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_graph_end_to_end.py::test_seed_replay_suite_matches_expected_routes_and_labels -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Create a fixed replay suite with:
- representative high-frequency industries
- sparse-data enterprise
- contradictory static/dynamic signals
- malformed LLM payload fixture
- low-confidence case
- rerun/idempotency case

**Step 4: Run tests**

Run: `pytest tests/integration/test_graph_end_to_end.py -v`
Expected: PASS

**Step 5: Commit**

If working in git:
```bash
git add tests/integration/fixtures tests/integration/test_graph_end_to_end.py
git commit -m "test: add seed replay release gate"
```

## Task 13: Run the full prelaunch validation suite

**Files:**
- No new files required

**Step 1: Run unit tests**

Run: `pytest tests/unit -v`
Expected: PASS

**Step 2: Run integration tests**

Run: `pytest tests/integration -v`
Expected: PASS

**Step 3: Run the full suite**

Run: `pytest tests -v`
Expected: PASS

**Step 4: Run one dry-run batch**

Run: `python -m industry_classification.main --pt 20260402 --mode dry-run`
Expected:
- formal writer only receives safe branch
- fallback writer receives low-confidence/error branch
- audit metadata present on all outputs
- cache hits visible on rerun

**Step 5: Record launch checklist**

Write a short runbook note covering:
- versions in use
- batch command
- rerun command
- rollback procedure
- where to inspect fallback outputs

## Launch Checklist

- SQL wide table contract matches `WideRow`
- all graph nodes use bounded prompt inputs
- all prompt-builders read `taxonomy_config.yaml`
- all LLM outputs pass through `llm_result_handler`
- `low_confidence` and parser/model errors route to fallback
- formal output writer includes audit metadata
- cache and idempotent publish behavior tested
- seed replay suite green
- dry-run batch green

## Post-Launch Follow-ups

- Use [TODOS.md](C:\Users\ASUS\Desktop\indus_agent\TODOS.md) to track:
  - formal taxonomy contract
  - signal quality gate
  - manual override + rollback safety layer
- Start collecting labeled cases for post-launch eval expansion.

## Execution Handoff

Plan complete and saved to `docs/plans/2026-04-02-industry-classification-v1.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
