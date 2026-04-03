"""Unit tests for the API routes module.

Uses FastAPI's TestClient to verify request/response formats and 422
validation errors for invalid parameters.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from industry_classification.api.routes import create_router
from industry_classification.api.services import (
    FallbackService,
    RunService,
    SearchService,
    SettingsService,
    StatsService,
    TaxonomyService,
)


# ---------------------------------------------------------------------------
# Fixtures – reuse the same in-memory store helpers from test_api_services
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
            "route": "formal",
        },
    }


def _fallback_record(
    entity_key: str, run_id: str, error_type: str = "low_confidence"
) -> dict:
    pk = f"{entity_key}::v1::v1::v1::fallback"
    return {
        "publish_key": pk,
        "decision_record": {"final_label": "建筑业", "confidence_level": "low"},
        "error_type": error_type,
        "audit": {
            "run_id": run_id,
            "entity_key": entity_key,
            "route": "fallback",
        },
    }


@pytest.fixture()
def formal_store() -> dict[str, dict]:
    r1 = _formal_record("91330100MA28W12345", "run-001")
    r2 = _formal_record("91330100MA28W99999", "run-002", label="信息技术")
    return {r1["publish_key"]: r1, r2["publish_key"]: r2}


@pytest.fixture()
def fallback_store() -> dict[str, dict]:
    r1 = _fallback_record("92320100MA4K966666", "run-003")
    return {r1["publish_key"]: r1}


@pytest.fixture()
def client(formal_store, fallback_store) -> TestClient:
    """Create a TestClient with all services wired to in-memory stores."""
    app = FastAPI()
    router = create_router(
        stats_service=StatsService(formal_store, fallback_store),
        run_service=RunService(formal_store, fallback_store),
        search_service=SearchService(formal_store, fallback_store),
        fallback_service=FallbackService(formal_store, fallback_store),
        taxonomy_service=TaxonomyService(),
        settings_service=SettingsService(),
    )
    app.include_router(router, prefix="/api")
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/stats
# ---------------------------------------------------------------------------


class TestGetStats:
    def test_returns_stats(self, client: TestClient):
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_processed"] == 3
        assert data["formal_count"] == 2
        assert data["fallback_count"] == 1


# ---------------------------------------------------------------------------
# GET /api/runs
# ---------------------------------------------------------------------------


class TestListRuns:
    def test_default_pagination(self, client: TestClient):
        resp = client.get("/api/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

    def test_custom_pagination(self, client: TestClient):
        resp = client.get("/api/runs", params={"offset": 0, "limit": 1})
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1

    def test_invalid_offset_returns_422(self, client: TestClient):
        resp = client.get("/api/runs", params={"offset": -1})
        assert resp.status_code == 422

    def test_invalid_limit_returns_422(self, client: TestClient):
        resp = client.get("/api/runs", params={"limit": 0})
        assert resp.status_code == 422

    def test_limit_exceeds_max_returns_422(self, client: TestClient):
        resp = client.get("/api/runs", params={"limit": 200})
        assert resp.status_code == 422

    def test_annotated_run_exposes_annotation_summary(self, client: TestClient):
        annotate = client.put(
            "/api/runs/run-001/annotation",
            json={"annotated_label": "建筑类", "reviewer_notes": "manual"},
        )
        assert annotate.status_code == 200

        resp = client.get("/api/runs")
        assert resp.status_code == 200
        item = next(item for item in resp.json()["items"] if item["run_id"] == "run-001")
        assert item["final_label"] == "建筑类"
        assert item["confidence_level"] == "high"
        assert len(item["annotations"]) >= 1
        assert item["annotations"][-1]["annotated_label"] == "建筑类"


# ---------------------------------------------------------------------------
# GET /api/runs/{run_id}
# ---------------------------------------------------------------------------


class TestGetRunDetail:
    def test_found(self, client: TestClient):
        resp = client.get("/api/runs/run-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == "run-001"
        assert data["route"] == "formal"

    def test_not_found(self, client: TestClient):
        resp = client.get("/api/runs/nonexistent")
        assert resp.status_code == 404

    def test_annotate_run(self, client: TestClient):
        resp = client.put(
            "/api/runs/run-001/annotation",
            json={"annotated_label": "建筑类", "reviewer_notes": "manual"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["annotated_label"] == "建筑类"
        assert data["status"] == "annotated"


# ---------------------------------------------------------------------------
# GET /api/search
# ---------------------------------------------------------------------------


class TestSearch:
    def test_search_returns_results(self, client: TestClient):
        resp = client.get("/api/search", params={"query": "MA28W12345"})
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["entity_key"] == "91330100MA28W12345"

    def test_search_missing_query_returns_422(self, client: TestClient):
        resp = client.get("/api/search")
        assert resp.status_code == 422

    def test_search_empty_query_returns_422(self, client: TestClient):
        resp = client.get("/api/search", params={"query": ""})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/batch
# ---------------------------------------------------------------------------


class TestTriggerBatch:
    def test_accepted(self, client: TestClient):
        resp = client.post(
            "/api/batch",
            json={
                "pt": "20260101",
                "input_path": "/data/input.csv",
                "worker_count": 4,
            },
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "accepted"
        assert "task_id" in data

    def test_invalid_body_returns_422(self, client: TestClient):
        resp = client.post("/api/batch", json={"pt": "20260101"})
        assert resp.status_code == 422

    def test_invalid_worker_count_returns_422(self, client: TestClient):
        resp = client.post(
            "/api/batch",
            json={
                "pt": "20260101",
                "input_path": "/data/input.csv",
                "worker_count": 0,
            },
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/fallbacks
# ---------------------------------------------------------------------------


class TestListFallbacks:
    def test_returns_fallbacks(self, client: TestClient):
        resp = client.get("/api/fallbacks")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_invalid_offset_returns_422(self, client: TestClient):
        resp = client.get("/api/fallbacks", params={"offset": -1})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PUT /api/fallbacks/{entity_key}/review
# ---------------------------------------------------------------------------


class TestReviewFallback:
    def test_review_success(self, client: TestClient):
        resp = client.put(
            "/api/fallbacks/92320100MA4K966666/review",
            json={"approved_label": "物业管理", "reviewer_notes": "ok"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["approved_label"] == "物业管理"
        assert data["status"] == "approved"

    def test_review_not_found(self, client: TestClient):
        resp = client.put(
            "/api/fallbacks/nonexistent/review",
            json={"approved_label": "物业管理"},
        )
        assert resp.status_code == 404

    def test_review_missing_label_returns_422(self, client: TestClient):
        resp = client.put(
            "/api/fallbacks/92320100MA4K966666/review",
            json={},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/taxonomy
# ---------------------------------------------------------------------------


class TestGetTaxonomy:
    def test_returns_taxonomy(self, client: TestClient):
        resp = client.get("/api/taxonomy")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert "labels" in data
        assert len(data["labels"]) > 0


# ---------------------------------------------------------------------------
# GET /api/settings & PUT /api/settings
# ---------------------------------------------------------------------------


class TestSettings:
    def test_get_settings(self, client: TestClient):
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "llm_model" in data
        assert "llm_timeout_sec" in data

    def test_update_settings_invalid_timeout_returns_422(
        self, client: TestClient
    ):
        resp = client.put(
            "/api/settings", json={"llm_timeout_sec": 0}
        )
        assert resp.status_code == 422
