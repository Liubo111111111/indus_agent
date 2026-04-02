# Industry Classification V1 Runbook

## Environment
- Use local `uv` environment only.
- Install/sync: `uv sync --extra dev`

## Key Versions
- `feature_schema_version`: `v1`
- `taxonomy_version`: `v1`
- `graph_version`: `v1`
- `prompt_version_static`: `v1`
- `prompt_version_dynamic`: `v1`
- `prompt_version_final`: `v1`

## Prompt Assets
- `src/industry_classification/prompts/static_profile_v1.yaml`
- `src/industry_classification/prompts/dynamic_profile_v1.yaml`
- `src/industry_classification/prompts/final_decision_v1.yaml`
- Prompt builders load these files by `prompt_version` and render a `[TASK] + [SYSTEM] + [USER]` prompt envelope before calling the client.

## Commands
- Run all tests:
  - `uv run python -m pytest tests/unit tests/integration -v`
- Run dry-run batch:
  - `uv run python -m industry_classification.main --pt 20260402 --mode dry-run`
- Run file-backed local batch:
  - `uv run python -m industry_classification.main --pt 20260402 --mode file-batch --input-path .\\input.jsonl --responses-path .\\responses.json --output-dir .\\output`

## Expected Dry-Run Signals
- Formal output count is greater than `0`
- Fallback output count is greater than or equal to `0`
- Cache entries are present
- Re-run path does not increase formal publish count for the same entity/version tuple

## Expected File-Batch Signals
- `formal_output.jsonl` contains only safe-branch publishes
- `fallback_output.jsonl` contains low-confidence/error branches
- `run_summary.json` records processed count, route counts, cache entries, and publish keys
- Re-running with the same output directory keeps output record counts stable

## Where To Inspect
- Formal path: `<output-dir>/formal_output.jsonl`
- Fallback path: `<output-dir>/fallback_output.jsonl`
- Batch summary: `<output-dir>/run_summary.json`
- Replay fixtures:
  - `tests/integration/fixtures/replay_cases.json`
  - `tests/integration/fixtures/replay_expected.json`

## Rollback Procedure
1. Stop consuming new formal output records downstream.
2. Revert to previous stable pricing input source.
3. Inspect fallback output and audit metadata for the failing run.
4. Check taxonomy/prompt/model/version drift before rerun.

## Next Hardening Steps
- Replace JSONL/file-backed writers with real warehouse table writers.
- Replace mock response adapter with real provider client wiring.
- Add formal taxonomy contract from `TODOS.md`.
- Add signal-quality gate from `TODOS.md`.
- Add manual override and rollback safety layer from `TODOS.md`.
