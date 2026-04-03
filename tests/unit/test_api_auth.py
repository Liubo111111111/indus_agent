from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from industry_classification.api.auth import FeishuAuthService, FeishuAuthSettings, FeishuUser
from industry_classification.api.routes import create_router
from industry_classification.api.services import (
    FallbackService,
    RunService,
    SearchService,
    SettingsService,
    StatsService,
    TaxonomyService,
)


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


def _build_client() -> tuple[TestClient, FeishuAuthService]:
    formal = {}
    record = _formal_record("91330100MA28W12345", "run-001")
    formal[record["publish_key"]] = record
    fallback: dict[str, dict] = {}

    auth = FeishuAuthService(
        FeishuAuthSettings(
            enabled=True,
            app_id="cli_test_app",
            app_secret="test_secret",
            redirect_uri="http://testserver/api/auth/callback",
            frontend_base_url="http://frontend.local",
            session_secret="test-session-secret",
        )
    )

    app = FastAPI()
    router = create_router(
        stats_service=StatsService(formal, fallback),
        run_service=RunService(formal, fallback),
        search_service=SearchService(formal, fallback),
        fallback_service=FallbackService(formal, fallback),
        taxonomy_service=TaxonomyService(),
        settings_service=SettingsService(),
        auth_service=auth,
    )
    app.include_router(router, prefix="/api")
    return TestClient(app), auth


class TestApiAuth:
    def test_session_endpoint_reports_unauthenticated(self):
        client, _ = _build_client()

        resp = client.get("/api/auth/session")

        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["authenticated"] is False
        assert "login_url" in data

    def test_protected_route_requires_login(self):
        client, _ = _build_client()

        resp = client.get("/api/stats")

        assert resp.status_code == 401

    def test_protected_route_accepts_valid_session_cookie(self):
        client, auth = _build_client()
        cookie = auth.create_session_cookie_value(
            FeishuUser(
                open_id="ou_test_user",
                name="业务同学",
                email="biz@example.com",
            )
        )
        client.cookies.set(auth.cookie_name, cookie)

        resp = client.get("/api/stats")

        assert resp.status_code == 200
        assert resp.json()["total_processed"] == 1

    def test_logout_clears_authenticated_session(self):
        client, auth = _build_client()
        cookie = auth.create_session_cookie_value(
            FeishuUser(
                open_id="ou_test_user",
                name="业务同学",
                email="biz@example.com",
            )
        )
        client.cookies.set(auth.cookie_name, cookie)

        logout = client.post("/api/auth/logout")

        assert logout.status_code == 200

        session = client.get("/api/auth/session")
        assert session.status_code == 200
        assert session.json()["authenticated"] is False
