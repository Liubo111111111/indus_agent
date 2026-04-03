from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import urlencode, urljoin

import httpx
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from industry_classification.settings import _env_get


class FeishuUser(BaseModel):
    model_config = ConfigDict(extra="ignore")

    open_id: str
    name: str = ""
    en_name: str = ""
    avatar_url: str = ""
    email: str = ""
    enterprise_email: str = ""
    user_id: str = ""
    tenant_key: str = ""


class FeishuAuthSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    redirect_uri: str = ""
    frontend_base_url: str = "http://localhost:3000"
    authorize_url: str = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
    access_token_url: str = "https://open.feishu.cn/open-apis/authen/v1/access_token"
    user_info_url: str = "https://open.feishu.cn/open-apis/authen/v1/user_info"
    scope: str = "contact:user.base:readonly"
    session_secret: str = ""
    session_cookie_name: str = "industry_classification_session"
    session_ttl_sec: int = Field(default=8 * 60 * 60, ge=300)
    cookie_secure: bool = False
    cookie_domain: str = ""
    allowed_emails: list[str] = Field(default_factory=list)
    allowed_open_ids: list[str] = Field(default_factory=list)


def load_feishu_auth_settings() -> FeishuAuthSettings:
    return FeishuAuthSettings(
        enabled=_env_get("FEISHU_AUTH_ENABLED", "").lower() in {"1", "true", "yes", "on"},
        app_id=_env_get("FEISHU_APP_ID", ""),
        app_secret=_env_get("FEISHU_APP_SECRET", ""),
        redirect_uri=_env_get("FEISHU_REDIRECT_URI", ""),
        frontend_base_url=_env_get("FRONTEND_BASE_URL", "http://localhost:3000"),
        scope=_env_get("FEISHU_AUTH_SCOPE", "contact:user.base:readonly"),
        session_secret=_env_get("FEISHU_SESSION_SECRET", ""),
        session_cookie_name=_env_get("FEISHU_SESSION_COOKIE_NAME", "industry_classification_session"),
        session_ttl_sec=int(_env_get("FEISHU_SESSION_TTL_SEC", str(8 * 60 * 60))),
        cookie_secure=_env_get("FEISHU_COOKIE_SECURE", "").lower() in {"1", "true", "yes", "on"},
        cookie_domain=_env_get("FEISHU_COOKIE_DOMAIN", ""),
        allowed_emails=[item.strip().lower() for item in _env_get("FEISHU_ALLOWED_EMAILS", "").split(",") if item.strip()],
        allowed_open_ids=[item.strip() for item in _env_get("FEISHU_ALLOWED_OPEN_IDS", "").split(",") if item.strip()],
    )


class FeishuAuthService:
    def __init__(
        self,
        settings: FeishuAuthSettings | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings or load_feishu_auth_settings()
        self._http_client = http_client
        self._revoked_session_ids: set[str] = set()

    @property
    def enabled(self) -> bool:
        required = (
            self._settings.app_id,
            self._settings.app_secret,
            self._settings.redirect_uri,
            self._settings.session_secret,
        )
        return self._settings.enabled and all(required)

    @property
    def cookie_name(self) -> str:
        return self._settings.session_cookie_name

    @property
    def cookie_secure(self) -> bool:
        return self._settings.cookie_secure

    @property
    def cookie_domain(self) -> str:
        return self._settings.cookie_domain

    @property
    def session_ttl_sec(self) -> int:
        return self._settings.session_ttl_sec

    def _sign(self, raw: bytes) -> str:
        signature = hmac.new(
            self._settings.session_secret.encode("utf-8"),
            raw,
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")

    def _encode_token(self, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        encoded = base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")
        signature = self._sign(raw)
        return f"{encoded}.{signature}"

    def _decode_token(self, token: str) -> dict[str, Any] | None:
        try:
            encoded, signature = token.split(".", 1)
            raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        except Exception:
            return None
        expected = self._sign(raw)
        if not hmac.compare_digest(signature, expected):
            return None
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            return None
        if payload.get("sid") in self._revoked_session_ids:
            return None
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload

    def _normalize_next_path(self, next_path: str | None) -> str:
        if not next_path or not next_path.startswith("/"):
            return "/"
        return next_path

    def build_login_url(self, next_path: str = "/") -> str:
        if not self.enabled:
            raise HTTPException(status_code=503, detail="Feishu auth is not configured")
        state = self._encode_token(
            {
                "next": self._normalize_next_path(next_path),
                "iat": int(time.time()),
                "exp": int(time.time()) + 10 * 60,
            }
        )
        query = urlencode(
            {
                "client_id": self._settings.app_id,
                "redirect_uri": self._settings.redirect_uri,
                "response_type": "code",
                "scope": self._settings.scope,
                "state": state,
            }
        )
        return f"{self._settings.authorize_url}?{query}"

    def create_session_cookie_value(self, user: FeishuUser) -> str:
        now = int(time.time())
        return self._encode_token(
            {
                "iat": now,
                "exp": now + self._settings.session_ttl_sec,
                "sid": self._build_session_id(user, now),
                "user": user.model_dump(),
            }
        )

    def clear_session_cookie_value(self) -> str:
        return ""

    def revoke_session(self, token: str | None) -> None:
        if not token:
            return
        payload = self._decode_token_without_revocation(token)
        if payload is None:
            return
        sid = payload.get("sid")
        if isinstance(sid, str) and sid:
            self._revoked_session_ids.add(sid)

    def get_current_user(self, request: Request) -> FeishuUser | None:
        if not self.enabled:
            return None
        cookie = request.cookies.get(self.cookie_name)
        if not cookie:
            return None
        payload = self._decode_token(cookie)
        if payload is None:
            return None
        user_payload = payload.get("user")
        if not isinstance(user_payload, dict):
            return None
        return FeishuUser.model_validate(user_payload)

    def _decode_token_without_revocation(self, token: str) -> dict[str, Any] | None:
        try:
            encoded, signature = token.split(".", 1)
            raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        except Exception:
            return None
        expected = self._sign(raw)
        if not hmac.compare_digest(signature, expected):
            return None
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            return None
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload

    def _build_session_id(self, user: FeishuUser, issued_at: int) -> str:
        raw = f"{user.open_id}:{issued_at}:{self._settings.session_secret}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def require_user(self, request: Request) -> FeishuUser | None:
        if not self.enabled:
            return None
        user = self.get_current_user(request)
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        return user

    def get_session_payload(self, request: Request) -> dict[str, Any]:
        user = self.get_current_user(request)
        return {
            "enabled": self.enabled,
            "authenticated": user is not None,
            "user": user.model_dump() if user is not None else None,
            "login_url": self.build_login_url("/") if self.enabled else None,
        }

    def build_frontend_redirect(self, next_path: str) -> str:
        normalized = self._normalize_next_path(next_path)
        return urljoin(self._settings.frontend_base_url.rstrip("/") + "/", normalized.lstrip("/"))

    def _is_allowed(self, user: FeishuUser) -> bool:
        if self._settings.allowed_open_ids and user.open_id not in self._settings.allowed_open_ids:
            return False
        allowed_emails = self._settings.allowed_emails
        if not allowed_emails:
            return True
        email_candidates = {
            user.email.strip().lower(),
            user.enterprise_email.strip().lower(),
        }
        return any(email and email in allowed_emails for email in email_candidates)

    def authenticate_with_code(self, code: str, state: str) -> tuple[FeishuUser, str]:
        if not self.enabled:
            raise HTTPException(status_code=503, detail="Feishu auth is not configured")
        state_payload = self._decode_token(state)
        if state_payload is None:
            raise HTTPException(status_code=400, detail="Invalid login state")
        next_path = self._normalize_next_path(state_payload.get("next"))
        user_access_token = self._exchange_code_for_access_token(code)
        user = self._fetch_user(user_access_token)
        if not self._is_allowed(user):
            raise HTTPException(status_code=403, detail="User is not allowed to access this console")
        return user, next_path

    def _exchange_code_for_access_token(self, code: str) -> str:
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "app_id": self._settings.app_id,
            "app_secret": self._settings.app_secret,
        }
        client, should_close = self._client()
        try:
            resp = client.post(self._settings.access_token_url, json=payload)
        finally:
            if should_close:
                client.close()
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 0:
            raise HTTPException(status_code=502, detail=body.get("msg", "Failed to exchange Feishu login code"))
        data = body.get("data") or {}
        token = data.get("access_token")
        if not token:
            raise HTTPException(status_code=502, detail="Feishu did not return a user access token")
        return token

    def _fetch_user(self, user_access_token: str) -> FeishuUser:
        client, should_close = self._client()
        try:
            resp = client.get(
                self._settings.user_info_url,
                headers={"Authorization": f"Bearer {user_access_token}"},
            )
        finally:
            if should_close:
                client.close()
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 0:
            raise HTTPException(status_code=502, detail=body.get("msg", "Failed to fetch Feishu user info"))
        data = body.get("data") or {}
        return FeishuUser.model_validate(data)

    def _client(self) -> tuple[httpx.Client, bool]:
        if self._http_client is not None:
            return self._http_client, False
        return httpx.Client(timeout=10.0), True
