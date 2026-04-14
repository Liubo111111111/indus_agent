from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from industry_classification.api.auth import FeishuAuthService, FeishuAuthSettings, FeishuUser
from industry_classification.api.data_source_router import DataSourceRouter
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


def _build_mock_data_source_router(
    formal: dict, fallback: dict
) -> DataSourceRouter:
    """Create a mock DataSourceRouter that returns in-memory services."""
    mock_router = MagicMock(spec=DataSourceRouter)
    mock_router.get_latest_pt.return_value = "20260412"
    mock_router.validate_pt.return_value = True
    mock_router.build_services.return_value = {
        "stats_service": StatsService(formal, fallback),
        "run_service": RunService(formal, fallback),
        "search_service": SearchService(formal, fallback),
        "fallback_service": FallbackService(formal, fallback),
    }
    mock_router.list_dates.return_value = [{"pt": "20260412", "record_count": 1}]
    return mock_router


def _build_client() -> tuple[TestClient, FeishuAuthService]:
    return _build_client_with_auth(
        FeishuAuthSettings(
            enabled=True,
            app_id="cli_test_app",
            app_secret="test_secret",
            redirect_uri="http://testserver/api/auth/callback",
            frontend_base_url="http://frontend.local",
            session_secret="test-session-secret",
        )
    )


def _build_client_with_auth(settings: FeishuAuthSettings) -> tuple[TestClient, FeishuAuthService]:
    formal = {}
    record = _formal_record("91330100MA28W12345", "run-001")
    formal[record["publish_key"]] = record
    fallback: dict[str, dict] = {}

    auth = FeishuAuthService(settings)
    mock_dsr = _build_mock_data_source_router(formal, fallback)

    app = FastAPI()
    router = create_router(
        data_source_router=mock_dsr,
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

    def test_protected_route_rejects_when_auth_not_configured(self):
        client, _ = _build_client_with_auth(
            FeishuAuthSettings(
                enabled=False,
                frontend_base_url="http://frontend.local",
            )
        )

        resp = client.get("/api/stats")

        assert resp.status_code == 503

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

    def test_authenticated_session_defaults_user_to_admin(self):
        client, auth = _build_client()
        cookie = auth.create_session_cookie_value(
            FeishuUser(
                open_id="ou_test_admin",
                name="管理员",
                email="admin@example.com",
            )
        )
        client.cookies.set(auth.cookie_name, cookie)

        session = client.get("/api/auth/session")

        assert session.status_code == 200
        data = session.json()
        assert data["authenticated"] is True
        assert data["user"]["open_id"] == "ou_test_admin"
        assert data["user"]["is_admin"] is True

    def test_settings_route_forbids_non_admin_user_when_admin_allowlist_configured(self):
        client, auth = _build_client_with_auth(
            FeishuAuthSettings(
                enabled=True,
                app_id="cli_test_app",
                app_secret="test_secret",
                redirect_uri="http://testserver/api/auth/callback",
                frontend_base_url="http://frontend.local",
                session_secret="test-session-secret",
                admin_open_ids=["ou_real_admin"],
            )
        )
        cookie = auth.create_session_cookie_value(
            FeishuUser(
                open_id="ou_normal_user",
                name="普通用户",
                email="biz@example.com",
            )
        )
        client.cookies.set(auth.cookie_name, cookie)

        resp = client.get("/api/settings")

        assert resp.status_code == 403

    def test_admin_overview_reports_open_admin_mode_and_host_mismatch_warning(self):
        client, auth = _build_client()
        cookie = auth.create_session_cookie_value(
            FeishuUser(
                open_id="ou_test_admin",
                name="管理员",
                email="admin@example.com",
            )
        )
        client.cookies.set(auth.cookie_name, cookie)

        resp = client.get("/api/admin/overview")

        assert resp.status_code == 200
        data = resp.json()
        assert data["admin_mode"] == "open_admin"
        assert data["access_scope"] == "all_authenticated"
        assert data["host_consistent"] is False
        assert data["admin_open_id_count"] == 0
        assert data["admin_email_count"] == 0
        assert len(data["warnings"]) >= 1

    def test_admin_overview_reports_allowlist_mode_without_exposing_values(self):
        client, auth = _build_client_with_auth(
            FeishuAuthSettings(
                enabled=True,
                app_id="cli_test_app",
                app_secret="test_secret",
                redirect_uri="http://127.0.0.1:8000/api/auth/callback",
                frontend_base_url="http://127.0.0.1:3000",
                session_secret="test-session-secret",
                allowed_open_ids=["ou_allowed_1", "ou_allowed_2"],
                allowed_emails=["ops@example.com"],
                admin_open_ids=["ou_real_admin"],
                admin_emails=["admin@example.com"],
            )
        )
        cookie = auth.create_session_cookie_value(
            FeishuUser(
                open_id="ou_real_admin",
                name="管理员",
                email="admin@example.com",
            )
        )
        client.cookies.set(auth.cookie_name, cookie)

        resp = client.get("/api/admin/overview")

        assert resp.status_code == 200
        data = resp.json()
        assert data["admin_mode"] == "allowlist"
        assert data["access_scope"] == "restricted"
        assert data["host_consistent"] is True
        assert data["allowed_open_id_count"] == 2
        assert data["allowed_email_count"] == 1
        assert data["admin_open_id_count"] == 1
        assert data["admin_email_count"] == 1
        assert "ou_real_admin" not in str(data)
        assert "admin@example.com" not in str(data)

    def test_admin_access_settings_endpoint_returns_current_values_for_admin(self):
        client, auth = _build_client_with_auth(
            FeishuAuthSettings(
                enabled=True,
                app_id="cli_test_app",
                app_secret="test_secret",
                redirect_uri="http://127.0.0.1:8000/api/auth/callback",
                frontend_base_url="http://127.0.0.1:3000",
                session_secret="test-session-secret",
                allowed_open_ids=["ou_allowed"],
                allowed_emails=["ops@example.com"],
                admin_open_ids=["ou_real_admin"],
                admin_emails=["admin@example.com"],
            )
        )
        cookie = auth.create_session_cookie_value(
            FeishuUser(
                open_id="ou_real_admin",
                name="管理员",
                email="admin@example.com",
            )
        )
        client.cookies.set(auth.cookie_name, cookie)

        resp = client.get("/api/admin/access-settings")

        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed_open_ids"] == ["ou_allowed"]
        assert data["allowed_emails"] == ["ops@example.com"]
        assert data["admin_open_ids"] == ["ou_real_admin"]
        assert data["admin_emails"] == ["admin@example.com"]

    def test_admin_auth_audit_endpoint_returns_recent_events_and_users(self):
        client, auth = _build_client()
        admin_user = FeishuUser(
            open_id="ou_test_admin",
            name="管理员",
            email="admin@example.com",
            user_id="u_admin",
        )
        cookie = auth.create_session_cookie_value(admin_user)
        client.cookies.set(auth.cookie_name, cookie)
        auth.record_auth_event("login", admin_user)
        auth.record_auth_event("logout", admin_user)

        resp = client.get("/api/admin/auth-audit")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events"]) == 2
        assert data["events"][0]["event_type"] == "logout"
        assert data["events"][1]["event_type"] == "login"
        assert len(data["users"]) == 1
        assert data["users"][0]["open_id"] == "ou_test_admin"
        assert data["users"][0]["event_count"] == 2
        assert data["users"][0]["last_event_type"] == "logout"
        assert data["users"][0]["is_admin"] is True
