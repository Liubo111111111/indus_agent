"""API route definitions for the Dashboard API.

Routes are defined WITHOUT the ``/api`` prefix — the prefix is applied
when the router is mounted in ``server.py``.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse

from industry_classification.api.auth import FeishuAuthService
from industry_classification.api.data_source_router import DataSourceRouter
from industry_classification.api.schemas import (
    AdminAuthAuditResponse,
    AdminOverviewResponse,
    AccessSettingsResponse,
    AccessSettingsUpdate,
    AnnotationRequest,
    AuthSessionResponse,
    BatchAccepted,
    BatchRequest,
    ClassifyBatchUploadAccepted,
    ClassifyByJobNameRequest,
    ClassifySingleRequest,
    ReviewRequest,
    SettingsUpdate,
)
from industry_classification.api.services import (
    SettingsService,
    TaxonomyService,
)


def _resolve_services(
    data_source_router: DataSourceRouter, pt: str | None
) -> dict[str, Any]:
    """Resolve *pt* to an effective partition and build service instances.

    Raises :class:`HTTPException` on validation / lookup failures.
    """
    effective_pt = pt or data_source_router.get_latest_pt()
    if effective_pt is None:
        raise HTTPException(status_code=404, detail="No data partitions available")
    if not data_source_router.validate_pt(effective_pt):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid pt format: {effective_pt}. Expected yyyymmdd or _legacy",
        )
    try:
        return data_source_router.build_services(effective_pt)
    except ValueError:
        raise HTTPException(
            status_code=404, detail=f"Data partition not found: {effective_pt}"
        )


def create_router(
    data_source_router: DataSourceRouter,
    taxonomy_service: TaxonomyService,
    settings_service: SettingsService,
    auth_service: FeishuAuthService | None = None,
    batch_trigger_fn: Callable[[BatchRequest, str], Any] | None = None,
    classify_single_fn: Callable[[str, str], Any] | None = None,
    classify_csv_fn: Callable[[str, str, int], Any] | None = None,
    classify_job_fn: Callable[[str, str, str], Any] | None = None,
) -> APIRouter:
    """Build and return an :class:`APIRouter` wired to the given services."""

    router = APIRouter()
    auth = auth_service

    def require_auth(request: Request):
        if auth is None:
            return None
        return auth.require_user(request)

    def require_admin(request: Request):
        if auth is None:
            return None
        return auth.require_admin(request)

    @router.get("/auth/session", response_model=AuthSessionResponse)
    def get_auth_session(request: Request):
        if auth is None:
            return {
                "enabled": False,
                "authenticated": False,
                "access_denied": False,
                "request_status": None,
                "user": None,
                "login_url": None,
        }
        return auth.get_session_payload(request)

    @router.get("/admin/overview", response_model=AdminOverviewResponse)
    def get_admin_overview(_user=Depends(require_admin)):
        if auth is None:
            raise HTTPException(status_code=503, detail="Feishu auth is not configured")
        return auth.get_admin_overview_payload()

    @router.get("/admin/auth-audit", response_model=AdminAuthAuditResponse)
    def get_admin_auth_audit(_user=Depends(require_admin)):
        if auth is None:
            raise HTTPException(status_code=503, detail="Feishu auth is not configured")
        return auth.get_auth_audit_payload()

    @router.get("/admin/access-settings", response_model=AccessSettingsResponse)
    def get_admin_access_settings(_user=Depends(require_admin)):
        # 同步已批准申请的 openId 到白名单
        if auth is not None:
            current = settings_service.get_access_settings()
            approved = auth._audit_store.list_access_requests("approved")
            approved_ids = [r["open_id"] for r in approved if r.get("open_id")]
            missing = [oid for oid in approved_ids if oid not in current.allowed_open_ids]
            if missing:
                new_ids = current.allowed_open_ids + missing
                from industry_classification.api.schemas import AccessSettingsUpdate as _ASU
                settings_service.update_access_settings(_ASU(
                    allowed_open_ids=new_ids,
                    allowed_emails=current.allowed_emails,
                    admin_open_ids=current.admin_open_ids,
                    admin_emails=current.admin_emails,
                ))
                auth.apply_access_settings(
                    allowed_open_ids=new_ids,
                    allowed_emails=current.allowed_emails,
                    admin_open_ids=current.admin_open_ids,
                    admin_emails=current.admin_emails,
                )
            return auth.get_access_settings_payload()
        return settings_service.get_access_settings()

    @router.put("/admin/access-settings", response_model=AccessSettingsResponse)
    def update_admin_access_settings(update: AccessSettingsUpdate, _user=Depends(require_admin)):
        result = settings_service.update_access_settings(update)
        if auth is not None:
            auth.apply_access_settings(
                allowed_open_ids=result.allowed_open_ids,
                allowed_emails=result.allowed_emails,
                admin_open_ids=result.admin_open_ids,
                admin_emails=result.admin_emails,
            )
        return result

    @router.get("/auth/login")
    def login(next: str = Query("/", alias="next")):
        if auth is None:
            raise HTTPException(status_code=503, detail="Feishu auth is not configured")
        return RedirectResponse(auth.build_login_url(next))

    @router.get("/auth/callback")
    def auth_callback(code: str, state: str):
        print(f"[AUTH] callback hit: code={code[:8]}..., auth={auth is not None}")
        if auth is None:
            raise HTTPException(status_code=503, detail="Feishu auth is not configured")
        try:
            user, next_path = auth.authenticate_with_code(code, state)
        except Exception as e:
            print(f"[AUTH] callback error: {e}")
            raise
        auth.record_auth_event("login", user)
        response = RedirectResponse(auth.build_frontend_redirect(next_path), status_code=302)
        response.set_cookie(
            key=auth.cookie_name,
            value=auth.create_session_cookie_value(user),
            httponly=True,
            secure=auth.cookie_secure,
            samesite="lax",
            max_age=auth.session_ttl_sec,
            domain=auth.cookie_domain or None,
            path="/",
        )
        return response

    @router.post("/auth/logout")
    def logout(request: Request):
        if auth is None:
            return JSONResponse({"status": "logged_out"})
        current_user = auth.get_current_user(request)
        if current_user is not None:
            auth.record_auth_event("logout", current_user)
        auth.revoke_session(request.cookies.get(auth.cookie_name))
        response = JSONResponse({"status": "logged_out"})
        response.set_cookie(
            key=auth.cookie_name,
            value=auth.clear_session_cookie_value(),
            httponly=True,
            secure=auth.cookie_secure,
            samesite="lax",
            max_age=0,
            expires=0,
            domain=auth.cookie_domain or None,
            path="/",
        )
        return response

    # -- access requests --------------------------------------------------

    @router.post("/auth/request-access")
    def request_access(request: Request, body: dict = None):
        """用户提交访问权限申请"""
        if auth is None:
            raise HTTPException(status_code=503, detail="Auth not configured")
        user = auth.get_current_user(request)
        if user is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        reason = (body or {}).get("reason", "") if body else ""
        result = auth._audit_store.create_access_request(user, reason)
        return result

    @router.get("/admin/access-requests")
    def list_access_requests(status: str = "", _user=Depends(require_admin)):
        """管理员查看权限申请列表"""
        if auth is None:
            raise HTTPException(status_code=503, detail="Auth not configured")
        return auth._audit_store.list_access_requests(status)

    @router.put("/admin/access-requests/{open_id}")
    def review_access_request(open_id: str, body: dict, _user=Depends(require_admin)):
        """管理员批准、拒绝或撤销权限申请"""
        if auth is None:
            raise HTTPException(status_code=503, detail="Auth not configured")
        action = body.get("action", "")
        if action not in ("approve", "reject", "revoke"):
            raise HTTPException(status_code=400, detail="action must be 'approve', 'reject' or 'revoke'")

        if action == "revoke":
            status = "revoked"
        elif action == "approve":
            status = "approved"
        else:
            status = "rejected"

        reviewer_note = body.get("reviewer_note", "")
        result = auth._audit_store.update_access_request(open_id, status, reviewer_note)
        if result is None:
            raise HTTPException(status_code=404, detail="Access request not found")

        # 批准后自动将 openId 加入允许登录白名单
        if action == "approve" and open_id:
            current = settings_service.get_access_settings()
            if open_id not in current.allowed_open_ids:
                new_ids = current.allowed_open_ids + [open_id]
                from industry_classification.api.schemas import AccessSettingsUpdate
                settings_service.update_access_settings(AccessSettingsUpdate(
                    allowed_open_ids=new_ids,
                    allowed_emails=current.allowed_emails,
                    admin_open_ids=current.admin_open_ids,
                    admin_emails=current.admin_emails,
                ))
                if auth is not None:
                    auth.apply_access_settings(
                        allowed_open_ids=new_ids,
                        allowed_emails=current.allowed_emails,
                        admin_open_ids=current.admin_open_ids,
                        admin_emails=current.admin_emails,
                    )

        # 撤销时从白名单移除 openId
        if action == "revoke" and open_id:
            current = settings_service.get_access_settings()
            if open_id in current.allowed_open_ids:
                new_ids = [oid for oid in current.allowed_open_ids if oid != open_id]
                from industry_classification.api.schemas import AccessSettingsUpdate
                settings_service.update_access_settings(AccessSettingsUpdate(
                    allowed_open_ids=new_ids,
                    allowed_emails=current.allowed_emails,
                    admin_open_ids=current.admin_open_ids,
                    admin_emails=current.admin_emails,
                ))
                if auth is not None:
                    auth.apply_access_settings(
                        allowed_open_ids=new_ids,
                        allowed_emails=current.allowed_emails,
                        admin_open_ids=current.admin_open_ids,
                        admin_emails=current.admin_emails,
                    )

        return result

    # -- dates ------------------------------------------------------------

    @router.get("/dates")
    def list_dates(_user=Depends(require_auth)):
        entries = data_source_router.list_dates()
        latest = data_source_router.get_latest_pt()
        return {"dates": entries, "latest_pt": latest}

    @router.get("/daily-summary")
    def get_daily_summary(
        pt_start: str = Query(...),
        pt_end: str = Query(...),
        _user=Depends(require_auth),
    ):
        if pt_start > pt_end:
            raise HTTPException(status_code=400, detail="pt_start must not be later than pt_end")
        return {"summaries": data_source_router.list_daily_summaries(pt_start, pt_end)}

    # -- stats ------------------------------------------------------------

    @router.get("/stats")
    def get_stats(
        pt: str = Query(None),
        pt_start: str = Query(None),
        pt_end: str = Query(None),
        _user=Depends(require_auth),
    ):
        # Range query takes priority
        if pt_start and pt_end:
            if not data_source_router.validate_pt(pt_start):
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid pt format: {pt_start}. Expected yyyymmdd or _legacy",
                )
            if not data_source_router.validate_pt(pt_end):
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid pt format: {pt_end}. Expected yyyymmdd or _legacy",
                )
            if pt_start > pt_end:
                raise HTTPException(
                    status_code=400,
                    detail="pt_start must not be later than pt_end",
                )
            return data_source_router.aggregate_stats(pt_start, pt_end)

        services = _resolve_services(data_source_router, pt)
        return services["stats_service"].get_stats()

    # -- runs -------------------------------------------------------------

    @router.get("/runs")
    def list_runs(
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        pt: str = Query(None),
        label: str = Query(None),
        annotation_status: str = Query(None),
        _user=Depends(require_auth),
    ):
        services = _resolve_services(data_source_router, pt)
        return services["run_service"].list_runs(
            offset, limit, label=label, annotation_status=annotation_status
        )

    @router.get("/runs/{run_id}")
    def get_run_detail(run_id: str, pt: str = Query(None), _user=Depends(require_auth)):
        services = _resolve_services(data_source_router, pt)
        detail = services["run_service"].get_run_detail(run_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return detail

    @router.put("/runs/{run_id}/annotation")
    def annotate_run(run_id: str, req: AnnotationRequest, pt: str = Query(None), _user=Depends(require_auth)):
        services = _resolve_services(data_source_router, pt)
        result = services["run_service"].annotate(run_id, req.annotated_label, req.reviewer_notes, req.reviewer_name)
        if result is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return result

    # -- search -----------------------------------------------------------

    @router.get("/search")
    def search(query: str = Query(..., min_length=1), pt: str = Query(None), _user=Depends(require_auth)):
        services = _resolve_services(data_source_router, pt)
        return services["search_service"].search(query)

    # -- annotations archive ----------------------------------------------

    @router.get("/annotations")
    def list_annotations(pt: str = Query(None), _user=Depends(require_auth)):
        services = _resolve_services(data_source_router, pt)
        return services["run_service"].list_annotated_runs()

    # -- batch ------------------------------------------------------------

    @router.post("/batch", status_code=202)
    def trigger_batch(req: BatchRequest, _user=Depends(require_auth)):
        task_id = str(uuid.uuid4())
        if batch_trigger_fn:
            batch_trigger_fn(req, task_id)
        return BatchAccepted(task_id=task_id, message="Batch task accepted")

    # -- fallbacks --------------------------------------------------------

    @router.get("/fallbacks")
    def list_fallbacks(
        offset: int = Query(0, ge=0),
        limit: int = Query(20, ge=1, le=100),
        pt: str = Query(None),
        _user=Depends(require_auth),
    ):
        services = _resolve_services(data_source_router, pt)
        return services["fallback_service"].list_fallbacks(offset, limit)

    @router.put("/fallbacks/{entity_key}/review")
    def review_fallback(entity_key: str, req: ReviewRequest, pt: str = Query(None), _user=Depends(require_auth)):
        services = _resolve_services(data_source_router, pt)
        result = services["fallback_service"].review(
            entity_key, req.approved_label, req.reviewer_notes
        )
        if result is None:
            raise HTTPException(
                status_code=404, detail="Fallback record not found"
            )
        return result

    # -- taxonomy ---------------------------------------------------------

    @router.get("/taxonomy")
    def get_taxonomy(_user=Depends(require_auth)):
        return taxonomy_service.get_taxonomy()

    # -- settings ---------------------------------------------------------

    @router.get("/settings")
    def get_settings(_user=Depends(require_admin)):
        return settings_service.get_settings()

    @router.get("/settings/batch-config")
    def get_batch_config(_user=Depends(require_auth)):
        """返回批量分类配置（非管理员也可读取）"""
        s = settings_service.get_settings()
        return {"batch_max_rows": s.batch_max_rows}

    @router.get("/prompts")
    def get_prompts(_user=Depends(require_admin)):
        """返回所有 prompt 模板内容。"""
        from industry_classification.settings import load_prompt_asset
        prompts = {}
        for node, version in [("static_profile", "v1"), ("dynamic_profile", "v1"), ("final_decision", "v1")]:
            try:
                asset = load_prompt_asset(node, version)
                prompts[node] = {"version": asset.version, "system_prompt": asset.system_prompt, "user_template": asset.user_template}
            except Exception:
                prompts[node] = None
        return prompts

    @router.put("/settings")
    def update_settings(update: SettingsUpdate, _user=Depends(require_admin)):
        return settings_service.update_settings(update)

    # -- classify (发起分类) ----------------------------------------------

    @router.post("/classify/single", status_code=202)
    def classify_single(req: ClassifySingleRequest, _user=Depends(require_auth)):
        task_id = str(uuid.uuid4())
        if classify_single_fn:
            classify_single_fn(req.query, task_id, req.pt)
        return {"task_id": task_id, "message": f"单条分类任务已提交: {req.query}", "status": "accepted"}

    @router.post("/classify/by-job-name", status_code=202)
    def classify_by_job_name(req: ClassifyByJobNameRequest, _user=Depends(require_auth)):
        task_id = str(uuid.uuid4())
        if classify_job_fn:
            classify_job_fn(req.job_name, task_id, req.pt)
        return {"task_id": task_id, "message": f"按工种批量分类已提交: {req.job_name}", "status": "accepted"}

    @router.get("/classify/status/{task_id}")
    def get_classify_status(task_id: str, _user=Depends(require_auth)):
        from industry_classification.api.server import _task_store
        task = _task_store.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    @router.post("/classify/upload", status_code=202)
    async def classify_upload(file: UploadFile = File(...), pt: str = Form(""), _user=Depends(require_auth)):
        import csv
        import io
        import tempfile
        from pathlib import Path

        content = await file.read()
        text = content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            raise HTTPException(status_code=400, detail="CSV 文件为空或格式不正确")

        # Save to temp file for processing
        task_id = str(uuid.uuid4())
        tmp_dir = Path(tempfile.gettempdir()) / "classify_uploads"
        tmp_dir.mkdir(exist_ok=True)
        tmp_path = tmp_dir / f"{task_id}.csv"
        tmp_path.write_bytes(content)

        if classify_csv_fn:
            classify_csv_fn(str(tmp_path), task_id, len(rows), pt)

        return ClassifyBatchUploadAccepted(
            task_id=task_id,
            message=f"批量分类任务已提交，共 {len(rows)} 条记录",
            total_rows=len(rows),
        )

    return router
