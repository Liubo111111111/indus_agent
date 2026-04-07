"""Unit tests for the API service layer."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from industry_classification.api.services import (
    FallbackService,
    RunService,
    SearchService,
    SettingsService,
    StatsService,
    TaxonomyService,
)
from industry_classification.main import run_once


# ---------------------------------------------------------------------------
# Fixtures – in-memory dict stores that mimic JsonlKeyedStore
# ---------------------------------------------------------------------------

def _formal_record(entity_key: str, run_id: str, label: str = "物业管理") -> dict:
    pk = f"{entity_key}::v1::v1::v1"
    return {
        "publish_key": pk,
        "final_label": label,
        "confidence_level": "high",
        "decision_reason": "test reason",
        "supporting_evidence": ["ev1"],
        "audit": {
            "run_id": run_id,
            "entity_key": entity_key,
            "feature_schema_version": "v1",
            "taxonomy_version": "v1",
            "graph_version": "v1",
            "route": "formal",
        },
    }


def _fallback_record(entity_key: str, run_id: str, error_type: str = "low_confidence") -> dict:
    pk = f"{entity_key}::v1::v1::v1::fallback"
    return {
        "publish_key": pk,
        "decision_record": {"final_label": "建筑业", "confidence_level": "low"},
        "error_type": error_type,
        "audit": {
            "run_id": run_id,
            "entity_key": entity_key,
            "feature_schema_version": "v1",
            "taxonomy_version": "v1",
            "graph_version": "v1",
            "route": "fallback",
        },
    }


@pytest.fixture()
def formal_store() -> dict[str, dict]:
    r1 = _formal_record("91330100MA28W12345", "batch-1")
    r2 = _formal_record("91330100MA28W99999", "batch-1", label="信息技术")
    return {r1["publish_key"]: r1, r2["publish_key"]: r2}


@pytest.fixture()
def fallback_store() -> dict[str, dict]:
    r1 = _fallback_record("92320100MA4K966666", "batch-2")
    return {r1["publish_key"]: r1}


# ---------------------------------------------------------------------------
# StatsService
# ---------------------------------------------------------------------------


class TestStatsService:
    def test_counts(self, formal_store, fallback_store):
        svc = StatsService(formal_store, fallback_store)
        stats = svc.get_stats()
        assert stats.annotated_count == 0
        assert stats.unannotated_count == 3
        assert stats.total_processed == 3
        assert isinstance(stats.label_distribution, dict)

    def test_empty_stores(self):
        svc = StatsService({}, {})
        stats = svc.get_stats()
        assert stats.total_processed == 0


# ---------------------------------------------------------------------------
# RunService
# ---------------------------------------------------------------------------


class TestRunService:
    def test_list_runs_total(self, formal_store, fallback_store):
        svc = RunService(formal_store, fallback_store)
        result = svc.list_runs(offset=0, limit=10)
        assert result.total == 3
        assert len(result.items) == 3

    def test_list_runs_pagination(self, formal_store, fallback_store):
        svc = RunService(formal_store, fallback_store)
        page = svc.list_runs(offset=0, limit=2)
        assert len(page.items) == 2
        assert page.total == 3

    def test_list_runs_offset(self, formal_store, fallback_store):
        svc = RunService(formal_store, fallback_store)
        page = svc.list_runs(offset=2, limit=10)
        assert len(page.items) == 1

    def test_get_run_detail_found(self, formal_store, fallback_store):
        svc = RunService(formal_store, fallback_store)
        detail = svc.get_run_detail("batch-1")
        assert detail is not None
        assert detail.run_id == "batch-1"
        assert detail.route == "formal"
        assert detail.decision_record is not None

    def test_get_run_detail_fallback(self, formal_store, fallback_store):
        svc = RunService(formal_store, fallback_store)
        detail = svc.get_run_detail("batch-2")
        assert detail is not None
        assert detail.route == "fallback"

    def test_get_run_detail_not_found(self, formal_store, fallback_store):
        svc = RunService(formal_store, fallback_store)
        assert svc.get_run_detail("nonexistent") is None

    def test_list_runs_includes_annotation_summary(self, formal_store, fallback_store):
        svc = RunService(formal_store, fallback_store)

        resp = svc.annotate("batch-1", "建筑类", "manual corrected")

        assert resp is not None
        runs = svc.list_runs(offset=0, limit=10)
        annotated = next(item for item in runs.items if item.run_id == "batch-1")
        assert len(annotated.annotations) >= 1
        assert annotated.annotations[-1]["annotated_label"] == "建筑类"
        assert annotated.confidence_level == "high"


# ---------------------------------------------------------------------------
# SearchService
# ---------------------------------------------------------------------------


class TestSearchService:
    def test_search_by_entity_key(self, formal_store, fallback_store):
        svc = SearchService(formal_store, fallback_store)
        results = svc.search("MA28W12345")
        assert len(results) == 1
        assert results[0].entity_key == "91330100MA28W12345"
        assert results[0].route == "formal"

    def test_search_case_insensitive(self, formal_store, fallback_store):
        svc = SearchService(formal_store, fallback_store)
        results = svc.search("ma28w12345")
        assert len(results) == 1

    def test_search_empty_query(self, formal_store, fallback_store):
        svc = SearchService(formal_store, fallback_store)
        assert svc.search("") == []

    def test_search_no_match(self, formal_store, fallback_store):
        svc = SearchService(formal_store, fallback_store)
        assert svc.search("ZZZZZ") == []

    def test_search_fallback_record(self, formal_store, fallback_store):
        svc = SearchService(formal_store, fallback_store)
        results = svc.search("MA4K966666")
        assert len(results) == 1
        assert results[0].route == "fallback"


# ---------------------------------------------------------------------------
# FallbackService
# ---------------------------------------------------------------------------


class TestFallbackService:
    def test_list_fallbacks(self, formal_store, fallback_store):
        svc = FallbackService(formal_store, fallback_store)
        result = svc.list_fallbacks(offset=0, limit=10)
        assert result.total == 1
        assert len(result.items) == 1
        assert result.items[0].error_type == "low_confidence"

    def test_review_success(self, formal_store, fallback_store):
        svc = FallbackService(formal_store, fallback_store)
        initial_formal = len(formal_store)
        initial_fallback = len(fallback_store)

        resp = svc.review("92320100MA4K966666", "物业管理", "looks correct")
        assert resp is not None
        assert resp.approved_label == "物业管理"
        assert resp.status == "approved"
        # Record migrated: fallback -1, formal +1
        assert len(fallback_store) == initial_fallback - 1
        assert len(formal_store) == initial_formal + 1

    def test_review_not_found(self, formal_store, fallback_store):
        svc = FallbackService(formal_store, fallback_store)
        assert svc.review("nonexistent", "物业管理") is None


# ---------------------------------------------------------------------------
# TaxonomyService
# ---------------------------------------------------------------------------


class TestTaxonomyService:
    def test_get_taxonomy(self):
        svc = TaxonomyService()
        result = svc.get_taxonomy()
        assert result.version
        assert len(result.labels) > 0
        assert result.labels[0].id


# ---------------------------------------------------------------------------
# SettingsService
# ---------------------------------------------------------------------------


class TestSettingsService:
    def test_get_settings(self):
        svc = SettingsService()
        settings = svc.get_settings()
        assert settings.llm_model  # should have a default
        assert settings.llm_timeout_sec > 0

    def test_update_settings(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text("LLM_MODEL=qwen3-max\nLLM_TIMEOUT_SEC=30\n")

        svc = SettingsService(env_path=env_file)
        from industry_classification.api.schemas import SettingsUpdate

        update = SettingsUpdate(llm_timeout_sec=60)
        result = svc.update_settings(update)
        assert result.llm_timeout_sec == 60

        # Verify .env file was updated
        content = env_file.read_text()
        assert "LLM_TIMEOUT_SEC=60" in content

        # Cleanup env
        os.environ.pop("LLM_TIMEOUT_SEC", None)

    def test_patch_env_appends_new_key(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text("LLM_MODEL=qwen3-max\n")

        svc = SettingsService(env_path=env_file)
        svc._patch_env_file({"WORKER_COUNT": "8"})

        content = env_file.read_text()
        assert "WORKER_COUNT=8" in content
        assert "LLM_MODEL=qwen3-max" in content

    def test_get_access_settings(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "FEISHU_ALLOWED_OPEN_IDS=ou_a,ou_b\n"
            "FEISHU_ALLOWED_EMAILS=ops@example.com,biz@example.com\n"
            "FEISHU_ADMIN_OPEN_IDS=ou_admin\n"
            "FEISHU_ADMIN_EMAILS=admin@example.com\n",
            encoding="utf-8",
        )

        svc = SettingsService(env_path=env_file)

        access = svc.get_access_settings()

        assert access.allowed_open_ids == ["ou_a", "ou_b"]
        assert access.allowed_emails == ["ops@example.com", "biz@example.com"]
        assert access.admin_open_ids == ["ou_admin"]
        assert access.admin_emails == ["admin@example.com"]

    def test_update_access_settings_normalizes_and_persists(self, tmp_path: Path):
        env_file = tmp_path / ".env"
        env_file.write_text("", encoding="utf-8")

        svc = SettingsService(env_path=env_file)
        from industry_classification.api.schemas import AccessSettingsUpdate

        updated = svc.update_access_settings(
            AccessSettingsUpdate(
                allowed_open_ids=[" ou_a ", "", "ou_b"],
                allowed_emails=[" Admin@Example.com ", " ", "ops@example.com"],
                admin_open_ids=[" ou_admin "],
                admin_emails=[" Owner@Example.com "],
            )
        )

        assert updated.allowed_open_ids == ["ou_a", "ou_b"]
        assert updated.allowed_emails == ["admin@example.com", "ops@example.com"]
        assert updated.admin_open_ids == ["ou_admin"]
        assert updated.admin_emails == ["owner@example.com"]

        content = env_file.read_text(encoding="utf-8")
        assert "FEISHU_ALLOWED_OPEN_IDS=ou_a,ou_b" in content
        assert "FEISHU_ALLOWED_EMAILS=admin@example.com,ops@example.com" in content
        assert "FEISHU_ADMIN_OPEN_IDS=ou_admin" in content
        assert "FEISHU_ADMIN_EMAILS=owner@example.com" in content


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
    return Path(__file__).resolve().parents[1] / "integration" / "fixtures" / name


@pytest.fixture()
def sqlite_output(tmp_path: Path) -> Path:
    replay_cases = json.loads(_fixture_path("replay_cases.json").read_text(encoding="utf-8"))
    sqlite_path = tmp_path / "pipeline_results.sqlite3"

    for idx, case in enumerate(replay_cases[:2], start=1):
        run_once(
            row_dict=case["row"],
            run_id=f"sqlite-run-{idx}",
            client=SequenceLLMClient(case["responses"]),
            formal_store={},
            fallback_store={},
            sqlite_path=sqlite_path,
        )

    return sqlite_path


class TestSqliteBackedServices:
    def test_stats_service_prefers_sqlite(self, sqlite_output: Path):
        svc = StatsService({}, {}, sqlite_path=sqlite_output)
        stats = svc.get_stats()
        assert stats.total_processed == 2
        assert stats.annotated_count == 0
        assert stats.unannotated_count == 2

    def test_run_service_reads_from_sqlite(self, sqlite_output: Path):
        svc = RunService({}, {}, sqlite_path=sqlite_output)
        result = svc.list_runs(offset=0, limit=10)
        assert result.total == 2
        assert {item.route for item in result.items} == {"formal", "fallback"}

    def test_run_service_uses_final_decision_completion_time_for_timestamp(self, sqlite_output: Path):
        with sqlite3.connect(sqlite_output) as conn:
            conn.execute(
                "update pipeline_runs set created_at = ?, updated_at = ? where run_id = ?",
                ("2026-04-07 10:00:00", "2026-04-07 10:00:00", "sqlite-run-1"),
            )
            conn.execute(
                "update inference_steps set updated_at = ? where run_id = ? and step_name = ?",
                ("2026-04-07 10:09:00", "sqlite-run-1", "final_decision"),
            )
            conn.commit()

        svc = RunService({}, {}, sqlite_path=sqlite_output)

        result = svc.list_runs(offset=0, limit=10)
        target = next(item for item in result.items if item.run_id == "sqlite-run-1")

        assert target.timestamp == "2026-04-07 10:09:00"

    def test_get_run_detail_reads_wide_row_from_sqlite(self, sqlite_output: Path):
        svc = RunService({}, {}, sqlite_path=sqlite_output)
        detail = svc.get_run_detail("sqlite-run-1")
        assert detail is not None
        assert detail.enterprise_name
        assert detail.wide_row["enterprise_name"] == detail.enterprise_name
        assert detail.static_profile is not None
        assert detail.dynamic_profile is not None

    def test_search_service_reads_from_sqlite(self, sqlite_output: Path):
        svc = SearchService({}, {}, sqlite_path=sqlite_output)
        results = svc.search("物业")
        assert len(results) >= 1
        assert any(item.route == "formal" for item in results)

    def test_fallback_service_reads_from_sqlite(self, sqlite_output: Path):
        svc = FallbackService({}, {}, sqlite_path=sqlite_output)
        result = svc.list_fallbacks(offset=0, limit=10)
        assert result.total == 1
        assert result.items[0].audit["route"] == "fallback"

    def test_fallback_review_updates_sqlite(self, sqlite_output: Path):
        formal_store: dict[str, dict] = {}
        fallback_store: dict[str, dict] = {}
        svc = FallbackService(formal_store, fallback_store, sqlite_path=sqlite_output)

        resp = svc.review("xyz", "物业管理", "manual")

        assert resp is not None

        run_svc = RunService(formal_store, fallback_store, sqlite_path=sqlite_output)
        detail = run_svc.get_run_detail("sqlite-run-2")
        assert detail is not None
        assert detail.route == "formal"
        assert detail.decision_record is not None
        assert detail.decision_record["final_label"] == "物业管理"

    def test_run_service_annotation_persists_and_overrides_display(self, sqlite_output: Path):
        svc = RunService({}, {}, sqlite_path=sqlite_output)

        resp = svc.annotate("sqlite-run-1", "建筑类", "manual corrected")

        assert resp is not None
        assert resp.annotated_label == "建筑类"

        detail = svc.get_run_detail("sqlite-run-1")
        assert detail is not None
        assert len(detail.annotations) >= 1
        assert detail.annotations[-1]["annotated_label"] == "建筑类"
        assert detail.decision_record is not None
        assert detail.decision_record["final_label"] == "物业管理"

        runs = svc.list_runs(offset=0, limit=10)
        annotated = next(item for item in runs.items if item.run_id == "sqlite-run-1")
        assert annotated.final_label == "建筑类"
        assert annotated.confidence_level == "high"
        assert len(annotated.annotations) >= 1
        assert annotated.annotations[-1]["annotated_label"] == "建筑类"

    def test_run_service_annotation_resolves_fallback(self, sqlite_output: Path):
        svc = RunService({}, {}, sqlite_path=sqlite_output)

        resp = svc.annotate("sqlite-run-2", "物业管理", "approved by reviewer")

        assert resp is not None
        detail = svc.get_run_detail("sqlite-run-2")
        assert detail is not None
        assert detail.route == "formal"
        assert len(detail.annotations) >= 1
        assert detail.decision_record is not None
        assert detail.decision_record["confidence_level"] == "low"

        fallback_svc = FallbackService({}, {}, sqlite_path=sqlite_output)
        fallbacks = fallback_svc.list_fallbacks(offset=0, limit=10)
        assert fallbacks.total == 0

        runs = svc.list_runs(offset=0, limit=10)
        annotated = next(item for item in runs.items if item.run_id == "sqlite-run-2")
        assert annotated.confidence_level == "low"
