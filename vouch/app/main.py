"""HTTP API (Starlette) and static screens.

All API routes live under /api. Errors are JSON: {"error": {"code", "message"}}.
"""
from __future__ import annotations

import json
import os
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import (agenda, cases, config, contacts, dashboard, db, delivery, gateway, ledger, migrations, policy, retention,
               reviews, schemas, scheduling, testmode, workspace)
from .errors import ApiError, invalid, not_found
from .security import check_password, current_user, hash_password, issue_token, require_role

STATIC = config.ROOT / "static"
REPORTS = config.REPO / "sentinel_hr" / "reports"

routes: list = []


def api(method: str, path: str):
    def deco(fn):
        routes.append(Route("/api" + path, fn, methods=[method]))
        return fn
    return deco


async def body_as(request: Request, model):
    raw = await request.body()
    if not raw.strip():
        data = {}
    else:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise invalid("Body must be JSON.")
    if not isinstance(data, dict):
        raise invalid("Body must be a JSON object.")
    return model.model_validate(data)


def paging(request: Request, allowed=("limit", "offset")) -> tuple[int, int]:
    extra = set(request.query_params) - set(allowed)
    if extra:
        raise invalid(f"Unknown query parameter(s): {', '.join(sorted(extra))}.")
    try:
        limit = int(request.query_params.get("limit", 50))
        offset = int(request.query_params.get("offset", 0))
    except ValueError:
        raise invalid("limit and offset must be numbers.")
    if limit < 1 or limit > config.MAX_LIST_LIMIT or offset < 0:
        raise invalid(f"limit must be 1..{config.MAX_LIST_LIMIT}, offset >= 0.")
    return limit, offset


def no_query(request: Request):
    if request.query_params:
        raise invalid("This endpoint takes no query parameters.")


def no_duplicate_query_keys(request: Request):
    keys = [key for key, _ in request.query_params.multi_items()]
    if len(keys) != len(set(keys)):
        raise invalid("Query parameters may only be supplied once.")


def ok(data, status=200):
    return JSONResponse(data, status_code=status)


# --- auth -------------------------------------------------------------------
_fails: OrderedDict[str, list[float]] = OrderedDict()
_MAX_LOGIN_KEYS = 10_000
_WINDOW_S = 300
_PER_ACCOUNT_AND_CLIENT = 10    # wrong passwords for one account from one client address
_PER_CLIENT = 30                # wrong passwords from one client address, any account (spraying)


def _throttle_key(email: str, client: str) -> str:
    """Failures count per (account, client address), so a stranger cannot lock the manager out of
    their own machine by typing wrong passwords for the manager's email. Behind a reverse proxy every
    request has the proxy's address; that limit is documented in vouch/README.md."""
    return f"{email}|{client}"


def _recent(key: str, now: float | None = None) -> list[float]:
    now = time.time() if now is None else now
    if key not in _fails:
        if len(_fails) >= _MAX_LOGIN_KEYS:
            _fails.popitem(last=False)
        _fails[key] = []
    _fails.move_to_end(key)
    _fails[key] = [t for t in _fails[key] if now - t < _WINDOW_S]
    return _fails[key]


def _blocked(key: str) -> bool:
    limit = _PER_CLIENT if key.startswith("*|") else _PER_ACCOUNT_AND_CLIENT
    return len(_recent(key)) >= limit
_DUMMY_PASSWORD_HASH = hash_password("vouch-unknown-account-check")


async def auth_user(request: Request) -> dict:
    return await run_in_threadpool(current_user, request)


@api("POST", "/auth/login")
async def login(request: Request):
    body = await body_as(request, schemas.Login)
    client = request.client.host if request.client else "unknown"
    email = body.email.lower()
    key = _throttle_key(email, client)
    spray = _throttle_key("*", client)
    now = time.time()
    if _blocked(key) or _blocked(spray):
        raise ApiError(429, "TOO_MANY_ATTEMPTS", "Too many failed logins. Wait 5 minutes.")
    u = await run_in_threadpool(db.one, "SELECT * FROM users WHERE lower(email)=?", (email,))
    password_ok = await run_in_threadpool(check_password, body.password, u["pw_hash"] if u else _DUMMY_PASSWORD_HASH)
    if not u or not password_ok:
        _fails[key].append(now)
        _fails[spray].append(now)
        raise ApiError(401, "BAD_CREDENTIALS", "Wrong email or password.")
    _fails.pop(key, None)
    return ok({"token": issue_token(u["id"]), "user": {"id": u["id"], "email": u["email"], "name": u["name"], "role": u["role"]}})


@api("GET", "/auth/me")
def me(request: Request):
    return ok(current_user(request))


@api("GET", "/users")
def users(request: Request):
    u = current_user(request)
    no_query(request)
    # Names and roles only, so a recruiter can pick the hiring manager for a case.
    return ok([dict(r) for r in db.q("SELECT id, name, role FROM users ORDER BY role, name")])


@api("GET", "/meta")
def meta(request: Request):
    current_policy = policy.read()
    provider_call = config.MODEL_MODE in ("openai", "ollama")
    return ok({"model_mode": config.MODEL_MODE, "test_mode": config.TEST_MODE,
               "demo_mode": config.DEMO_MODE,
               "n8n_delivery": bool(config.N8N_WEBHOOK_URL), "outbound_mode": config.OUTBOUND_MODE,
               "ai_capabilities": {
                   "mode": config.MODEL_MODE,
                   "provider_call_attempted_on_cv_upload": provider_call,
                   "claim_extraction": True,
                   "fallback_to_word_list": True,
                   "chat_assistant": False,
                   "inbox_summarization": False,
                   "autonomous_actions": False,
               },
               "approval_minutes": current_policy["approval_ttl_minutes"],
               "data_handling": {
                   "retention_days": config.RETENTION_DAYS,
                   "statement": "Original CVs stay on the Vouch server. Only visible, personal-data-removed text is sent "
                                "to an AI model. The Trust Ledger stores IDs and hashes, never CV text or contact details."}})


@api("GET", "/candidates")
def candidate_table(request: Request):
    user = current_user(request)
    no_duplicate_query_keys(request)
    allowed = {"case_id", "search", "finding_type", "shortlisted", "sort", "order", "limit", "offset"}
    extra = set(request.query_params) - allowed
    if extra:
        raise invalid(f"Unknown query parameter(s): {', '.join(sorted(extra))}.")
    limit, offset = paging(request, allowed=allowed)
    shortlisted = request.query_params.get("shortlisted")
    if shortlisted not in (None, "true", "false"):
        raise invalid("shortlisted must be true or false.")
    return ok(workspace.candidate_table(
        user, case_id=request.query_params.get("case_id"), search=request.query_params.get("search", ""),
        finding_type=request.query_params.get("finding_type"),
        shortlisted=None if shortlisted is None else shortlisted == "true",
        sort=request.query_params.get("sort", "created_at"), order=request.query_params.get("order", "desc"),
        limit=limit, offset=offset))


@api("GET", "/candidates/compare")
def compare_candidates(request: Request):
    user = current_user(request)
    no_duplicate_query_keys(request)
    extra = set(request.query_params) - {"candidate_ids"}
    if extra:
        raise invalid(f"Unknown query parameter(s): {', '.join(sorted(extra))}.")
    raw_ids = request.query_params.get("candidate_ids", "")
    return ok(workspace.compare_candidates(user, [value for value in raw_ids.split(",") if value]))


@api("GET", "/cases/{case_id}/analytics")
def case_analytics(request: Request):
    user = current_user(request)
    no_query(request)
    return ok(workspace.case_analytics(user, request.path_params["case_id"]))


@api("GET", "/workspace/outbox")
def workspace_outbox(request: Request):
    user = current_user(request)
    no_duplicate_query_keys(request)
    allowed = {"case_id", "limit", "offset"}
    extra = set(request.query_params) - allowed
    if extra:
        raise invalid(f"Unknown query parameter(s): {', '.join(sorted(extra))}.")
    limit, offset = paging(request, allowed=allowed)
    return ok(workspace.outbox_view(user, request.query_params.get("case_id"), limit, offset))


@api("GET", "/audit/ledger")
def audit_ledger(request: Request):
    user = current_user(request)
    no_duplicate_query_keys(request)
    allowed = {"case_id", "limit", "offset"}
    extra = set(request.query_params) - allowed
    if extra:
        raise invalid(f"Unknown query parameter(s): {', '.join(sorted(extra))}.")
    limit, offset = paging(request, allowed=allowed)
    return ok(workspace.audit_ledger(user, request.query_params.get("case_id"), limit, offset))


@api("GET", "/audit/export")
def audit_export(request: Request):
    user = current_user(request)
    no_query(request)
    return ok(workspace.signed_audit_export(user))


@api("GET", "/admin/users")
def admin_users(request: Request):
    user = current_user(request)
    require_role(user, "hr_admin")
    no_query(request)
    return ok(workspace.list_users())


@api("POST", "/admin/users")
async def admin_create_user(request: Request):
    user = await auth_user(request)
    require_role(user, "hr_admin")
    body = await body_as(request, schemas.UserCreate)
    return ok(await run_in_threadpool(workspace.create_user, user, body), 201)


@api("PATCH", "/admin/users/{user_id}/role")
async def admin_change_role(request: Request):
    user = await auth_user(request)
    require_role(user, "hr_admin")
    body = await body_as(request, schemas.UserRoleUpdate)
    return ok(await run_in_threadpool(workspace.change_user_role, user, request.path_params["user_id"], body.role))


@api("GET", "/admin/policy")
def admin_get_policy(request: Request):
    user = current_user(request)
    require_role(user, "hr_admin")
    no_query(request)
    return ok(policy.read())


@api("PUT", "/admin/policy")
async def admin_update_policy(request: Request):
    user = await auth_user(request)
    require_role(user, "hr_admin")
    body = await body_as(request, schemas.PolicyUpdate)
    values = body.model_dump(exclude_unset=True)
    if not values:
        raise invalid("Set at least one policy field.")
    return ok(await run_in_threadpool(policy.update, values, user["id"]))


# --- agenda: calendar feed, internal meetings, interview format ------------------
@api("GET", "/agenda")
def get_agenda(request: Request):
    user = current_user(request)
    no_duplicate_query_keys(request)
    extra = set(request.query_params) - {"from", "to"}
    if extra:
        raise invalid(f"Unknown query parameter(s): {', '.join(sorted(extra))}.")
    return ok(agenda.agenda(user, request.query_params.get("from"), request.query_params.get("to")))


@api("POST", "/meetings")
async def create_meeting(request: Request):
    user = await auth_user(request)
    body = await body_as(request, schemas.MeetingCreate)
    return ok(await run_in_threadpool(agenda.create_meeting, user, body), 201)


@api("PATCH", "/meetings/{meeting_id}")
async def update_meeting(request: Request):
    user = await auth_user(request)
    body = await body_as(request, schemas.MeetingUpdate)
    return ok(await run_in_threadpool(agenda.update_meeting, user, request.path_params["meeting_id"],
                                      body.model_dump(exclude_unset=True)))


@api("DELETE", "/meetings/{meeting_id}")
async def cancel_meeting(request: Request):
    user = await auth_user(request)
    no_query(request)
    await body_as(request, schemas.Empty)
    return ok(await run_in_threadpool(agenda.cancel_meeting, user, request.path_params["meeting_id"]))


@api("GET", "/interviews/{interview_id}/format")
def get_interview_format(request: Request):
    user = current_user(request)
    no_query(request)
    return ok(agenda.get_format(user, request.path_params["interview_id"]))


@api("POST", "/interviews/{interview_id}/format")
async def decide_interview_format(request: Request):
    user = await auth_user(request)
    body = await body_as(request, schemas.FormatDecision)
    return ok(await run_in_threadpool(agenda.decide_format, user, request.path_params["interview_id"], body.format))


@api("POST", "/interviews/{interview_id}/conducted-by")
async def interview_conducted_by(request: Request):
    user = await auth_user(request)
    body = await body_as(request, schemas.ConductedBy)
    return ok(await run_in_threadpool(agenda.set_conducted_by, user, request.path_params["interview_id"], body.by))


# --- interviews and follow-up tasks -----------------------------------------
@api("GET", "/interviews")
def list_interviews(request: Request):
    user = current_user(request)
    no_duplicate_query_keys(request)
    allowed = {"case_id", "candidate_id", "status", "from_date", "to_date", "limit", "offset"}
    extra = set(request.query_params) - allowed
    if extra:
        raise invalid(f"Unknown query parameter(s): {', '.join(sorted(extra))}.")
    limit, offset = paging(request, allowed=allowed)
    return ok(scheduling.list_interviews(
        user, case_id=request.query_params.get("case_id"), candidate_id=request.query_params.get("candidate_id"),
        status=request.query_params.get("status"), from_date=request.query_params.get("from_date"),
        to_date=request.query_params.get("to_date"), limit=limit, offset=offset))


@api("POST", "/interviews")
async def create_interview(request: Request):
    user = await auth_user(request)
    body = await body_as(request, schemas.InterviewCreate)
    return ok(await run_in_threadpool(scheduling.create_interview, user, body), 201)


@api("GET", "/interviews/{interview_id}")
def get_interview(request: Request):
    user = current_user(request)
    no_query(request)
    return ok(scheduling.get_interview(user, request.path_params["interview_id"]))


@api("PATCH", "/interviews/{interview_id}")
async def update_interview(request: Request):
    user = await auth_user(request)
    body = await body_as(request, schemas.InterviewUpdate)
    values = body.model_dump(exclude_unset=True)
    return ok(await run_in_threadpool(
        scheduling.update_interview, user, request.path_params["interview_id"], values))


@api("DELETE", "/interviews/{interview_id}")
async def cancel_interview(request: Request):
    user = await auth_user(request)
    no_query(request)
    await body_as(request, schemas.Empty)
    return ok(await run_in_threadpool(
        scheduling.update_interview, user, request.path_params["interview_id"], {"status": "cancelled"}))


@api("GET", "/follow-ups")
def list_follow_ups(request: Request):
    user = current_user(request)
    no_duplicate_query_keys(request)
    allowed = {"case_id", "candidate_id", "assigned_to", "status", "priority", "bucket", "limit", "offset"}
    extra = set(request.query_params) - allowed
    if extra:
        raise invalid(f"Unknown query parameter(s): {', '.join(sorted(extra))}.")
    limit, offset = paging(request, allowed=allowed)
    return ok(scheduling.list_tasks(
        user, case_id=request.query_params.get("case_id"), candidate_id=request.query_params.get("candidate_id"),
        assigned_to=request.query_params.get("assigned_to"), status=request.query_params.get("status"),
        priority=request.query_params.get("priority"), bucket=request.query_params.get("bucket"),
        limit=limit, offset=offset))


@api("POST", "/follow-ups")
async def create_follow_up(request: Request):
    user = await auth_user(request)
    body = await body_as(request, schemas.FollowUpCreate)
    return ok(await run_in_threadpool(scheduling.create_task, user, body), 201)


@api("GET", "/follow-ups/{task_id}")
def get_follow_up(request: Request):
    user = current_user(request)
    no_query(request)
    return ok(scheduling.get_task(user, request.path_params["task_id"]))


@api("PATCH", "/follow-ups/{task_id}")
async def update_follow_up(request: Request):
    user = await auth_user(request)
    body = await body_as(request, schemas.FollowUpUpdate)
    values = body.model_dump(exclude_unset=True)
    return ok(await run_in_threadpool(
        scheduling.update_task, user, request.path_params["task_id"], values))


# --- cases ------------------------------------------------------------------
@api("GET", "/dashboard/overview")
def dashboard_overview(request: Request):
    user = current_user(request)
    params = list(request.query_params.multi_items())
    if any(key != "case_id" for key, _ in params) or len(params) > 1:
        raise invalid("Only one optional case_id query parameter is allowed.")
    case_id = request.query_params.get("case_id")
    if case_id is not None and not case_id.strip():
        raise invalid("case_id must not be empty.")
    return ok(dashboard.overview(user, case_id))


@api("GET", "/cases")
def list_cases(request: Request):
    u = current_user(request)
    return ok(cases.list_cases(u, *paging(request)))


@api("POST", "/cases")
async def create_case(request: Request):
    u = await auth_user(request)
    body = await body_as(request, schemas.CaseCreate)
    return ok(await run_in_threadpool(cases.create_case, u, body), 201)


@api("GET", "/cases/{case_id}")
def get_case(request: Request):
    u = current_user(request)
    no_query(request)
    return ok(cases.get_case(u, request.path_params["case_id"]))


@api("PUT", "/cases/{case_id}/criteria")
async def set_criteria(request: Request):
    u = await auth_user(request)
    body = await body_as(request, schemas.CriteriaSet)
    result = await run_in_threadpool(cases.set_criteria, u, request.path_params["case_id"], body)
    return ok(result)


@api("POST", "/cases/{case_id}/criteria/confirm")
async def confirm_criteria(request: Request):
    u = await auth_user(request)
    await body_as(request, schemas.Empty)
    return ok(await run_in_threadpool(cases.confirm_criteria, u, request.path_params["case_id"]))


@api("POST", "/cases/{case_id}/candidates")
async def upload(request: Request):
    u = await auth_user(request)
    case_id = request.path_params["case_id"]
    # Check access before reading a large body.
    from .security import require_case_write
    await run_in_threadpool(require_case_write, u, case_id)
    ctype = request.headers.get("content-type", "")
    if not ctype.startswith("multipart/form-data"):
        raise invalid("Upload the CV as multipart/form-data with a 'file' field.")
    form = await request.form(max_files=20, max_fields=5)
    files = form.getlist("file")
    if not files or any(isinstance(f, str) for f in files):
        raise invalid("Add at least one PDF in the 'file' field.")
    extra = set(form.keys()) - {"file"}
    if extra:
        raise invalid(f"Unknown form field(s): {', '.join(sorted(extra))}.")
    results = []
    for f in files:
        data = await f.read(config.MAX_UPLOAD_BYTES + 1)
        try:
            result = await run_in_threadpool(cases.upload_cv, u, case_id, f.filename, data)
            results.append(result if len(files) == 1 else {"filename": f.filename, "ok": True, "result": result})
        except ApiError as exc:
            if len(files) == 1:
                raise
            results.append({"filename": f.filename, "ok": False, "error": exc.body()["error"]})
    if len(files) == 1:
        return ok(results[0], 201)
    status = 207 if any(not result["ok"] for result in results) else 201
    return ok(results, status)


@api("GET", "/cases/{case_id}/candidates")
def list_candidates(request: Request):
    u = current_user(request)
    return ok(cases.list_candidates(u, request.path_params["case_id"], *paging(request)))


@api("GET", "/candidates/{cand_id}")
def get_candidate(request: Request):
    u = current_user(request)
    no_query(request)
    return ok(cases.get_candidate(u, request.path_params["cand_id"]))


@api("DELETE", "/candidates/{cand_id}")
async def delete_candidate(request: Request):
    user = await auth_user(request)
    return ok(await run_in_threadpool(cases.delete_candidate, user, request.path_params["cand_id"]))


@api("GET", "/candidates/{cand_id}/dossier")
def get_dossier(request: Request):
    u = current_user(request)
    no_query(request)
    out = cases.dossier(u, request.path_params["cand_id"])
    reviews.record(u, request.path_params["cand_id"])     # HI-03: opening a dossier here is what counts as a review
    return ok(out)


@api("GET", "/candidates/{cand_id}/contact")
def get_contact(request: Request):
    u = current_user(request)
    no_query(request)
    return ok(contacts.get_contact(u, request.path_params["cand_id"]))


@api("POST", "/candidates/{cand_id}/contact/confirm")
async def confirm_contact(request: Request):
    u = await auth_user(request)
    body = await body_as(request, schemas.ContactConfirm)
    return ok(await run_in_threadpool(contacts.confirm, u, request.path_params["cand_id"], body.email))


@api("POST", "/candidates/{cand_id}/dossier")
async def regen_dossier(request: Request):
    u = await auth_user(request)
    await body_as(request, schemas.Empty)     # a client can't point the dossier at another document
    return ok(await run_in_threadpool(cases.regenerate_dossier, u, request.path_params["cand_id"]))


@api("GET", "/documents/{doc_id}/extraction")
def extraction(request: Request):
    u = current_user(request)
    return ok(cases.extraction(u, request.path_params["doc_id"]))


@api("GET", "/documents/{doc_id}/findings")
def doc_findings(request: Request):
    u = current_user(request)
    return ok(cases.document_findings(u, request.path_params["doc_id"]))


@api("GET", "/documents/{doc_id}/pages/{page:int}.png")
def page_png(request: Request):
    u = current_user(request)
    png = cases.page_png(u, request.path_params["doc_id"], request.path_params["page"])
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@api("POST", "/cases/{case_id}/ranking")
async def draft_ranking(request: Request):
    u = await auth_user(request)
    await body_as(request, schemas.Empty)
    return ok(await run_in_threadpool(cases.draft_ranking, u, request.path_params["case_id"]), 201)


@api("GET", "/cases/{case_id}/ranking")
def get_ranking(request: Request):
    u = current_user(request)
    return ok(cases.get_ranking(u, request.path_params["case_id"]))


@api("POST", "/cases/{case_id}/ranking/{version:int}/confirm")
async def confirm_ranking(request: Request):
    u = await auth_user(request)
    await body_as(request, schemas.Empty)
    await run_in_threadpool(reviews.enforce_ranking, u, request.path_params["case_id"], request.path_params["version"])
    return ok(await run_in_threadpool(cases.confirm_ranking, u, request.path_params["case_id"], request.path_params["version"]))


@api("POST", "/cases/{case_id}/ranking/{version:int}/shortlist")
async def shortlist(request: Request):
    u = await auth_user(request)
    body = await body_as(request, schemas.ShortlistSet)
    # HI-03: every candidate placed on the shortlist must have been opened by this recruiter.
    await run_in_threadpool(reviews.enforce_selected, u, request.path_params["case_id"], list(body.candidate_ids))
    result = await run_in_threadpool(
        cases.shortlist, u, request.path_params["case_id"], request.path_params["version"], body)
    return ok(result)


# --- proposals, approvals, gateway --------------------------------------------
@api("POST", "/cases/{case_id}/proposals")
async def create_proposal(request: Request):
    u = await auth_user(request)
    body = await body_as(request, schemas.ProposalCreate)
    return ok(await run_in_threadpool(gateway.create_proposal, u, request.path_params["case_id"], body), 201)


@api("GET", "/cases/{case_id}/proposals")
def list_proposals(request: Request):
    u = current_user(request)
    paging(request)
    return ok(gateway.list_proposals(u, request.path_params["case_id"]))


@api("GET", "/proposals/{pid}")
def get_proposal(request: Request):
    u = current_user(request)
    return ok(gateway.get_proposal(u, request.path_params["pid"]))


@api("PATCH", "/proposals/{pid}")
async def edit_proposal(request: Request):
    u = await auth_user(request)
    body = await body_as(request, schemas.ProposalEdit)
    return ok(await run_in_threadpool(gateway.edit_proposal, u, request.path_params["pid"], body))


@api("POST", "/proposals/{pid}/approve")
async def approve(request: Request):
    u = await auth_user(request)
    body = await body_as(request, schemas.Decision)
    return ok(await run_in_threadpool(gateway.decide, u, request.path_params["pid"], "approved", body.payload_sha256))


@api("POST", "/proposals/{pid}/reject")
async def reject(request: Request):
    u = await auth_user(request)
    body = await body_as(request, schemas.Decision)
    return ok(await run_in_threadpool(gateway.decide, u, request.path_params["pid"], "rejected", body.payload_sha256))


@api("POST", "/proposals/{pid}/execute")
async def execute(request: Request):
    u = await auth_user(request)
    await body_as(request, schemas.Empty)     # the gateway never accepts a payload from the client
    return ok(await run_in_threadpool(gateway.execute, u, request.path_params["pid"]))


@api("POST", "/outbox/{oid}/retry")
async def retry_delivery(request: Request):
    u = await auth_user(request)
    await body_as(request, schemas.Empty)     # a retry re-sends the stored approved payload, nothing else
    return ok(await run_in_threadpool(delivery.retry, u, request.path_params["oid"]))


@api("GET", "/healthz")
def healthz(request: Request):
    return ok({"ok": True})


@api("GET", "/readyz")
def readyz(request: Request):
    """Startup self-check: schema version, SQLite integrity, ledger chain, writable data dirs. No data returned."""
    conn = db.connect()
    with db._lock:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        version = migrations.current(conn)
    led = ledger.verify()
    writable = all(os.access(d, os.W_OK) for d in (config.DATA_DIR, config.ORIGINALS_DIR))
    body = {"ok": integrity == "ok" and led["ok"] and writable and version == migrations.LATEST,
            "schema_version": version, "integrity": integrity, "ledger_ok": led["ok"], "writable": writable,
            "outbound_mode": config.OUTBOUND_MODE}
    return ok(body, 200 if body["ok"] else 503)


@api("GET", "/cases/{case_id}/outbox")
def outbox(request: Request):
    u = current_user(request)
    return ok(gateway.outbox(u, request.path_params["case_id"]))


# --- ledger & assurance ---------------------------------------------------------
@api("GET", "/ledger")
def get_ledger(request: Request):
    u = current_user(request)
    extra = set(request.query_params) - {"case_id"}
    if extra:
        raise invalid(f"Unknown query parameter(s): {', '.join(sorted(extra))}.")
    case_id = request.query_params.get("case_id")
    if case_id:
        from .security import require_case_read
        require_case_read(u, case_id)
        rows = db.q("SELECT * FROM ledger WHERE case_id=? ORDER BY seq", (case_id,))
    else:
        require_role(u, "auditor", "hr_admin")
        rows = db.q("SELECT * FROM ledger ORDER BY seq DESC LIMIT 500")
    return ok([{"seq": r["seq"], "ts": r["ts"], "actor": r["actor"], "type": r["type"], "case_id": r["case_id"],
                "subject": r["subject"], "body": db.loads(r["body_json"], {}), "hash": r["hash"]} for r in rows])


@api("GET", "/ledger/verify")
def verify_ledger(request: Request):
    u = current_user(request)
    require_role(u, "auditor", "hr_admin")
    return ok(ledger.verify())


@api("GET", "/ledger/head")
def ledger_head(request: Request):
    u = current_user(request)
    no_query(request)
    require_role(u, "auditor", "hr_admin")
    return ok(ledger.head())


@api("GET", "/assurance/latest")
def assurance_latest(request: Request):
    current_user(request)
    p = REPORTS / "latest.json"
    if not p.exists():
        return ok({"available": False})
    return ok({"available": True, **json.loads(p.read_text(encoding="utf-8"))})


_run = {"proc": None}


@api("POST", "/assurance/run")
async def assurance_run(request: Request):
    """Start SENTINEL against an ISOLATED test instance (temporary database). Demo data is untouched."""
    import subprocess
    import sys
    u = await auth_user(request)
    require_role(u, "hr_admin", "auditor")
    await body_as(request, schemas.Empty)
    p = _run["proc"]
    if p is not None and p.poll() is None:
        return ok({"started": False, "running": True}, 202)
    _run["proc"] = subprocess.Popen([sys.executable, str(config.REPO / "sentinel_hr" / "runner.py"), "--spawn"],
                                    cwd=str(config.REPO), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await run_in_threadpool(ledger.record, u["id"], "ASSURANCE_RUN_STARTED", None, None, {})
    return ok({"started": True, "running": True}, 202)


@api("GET", "/assurance/status")
def assurance_status(request: Request):
    current_user(request)
    p = _run["proc"]
    return ok({"running": p is not None and p.poll() is None})


# --- test mode ----------------------------------------------------------------------
@api("POST", "/_test/reset")
def test_reset(request: Request):
    testmode.guard(request)
    return ok(testmode.reset())


@api("POST", "/_test/clock")
async def test_clock(request: Request):
    testmode.guard(request)
    data = json.loads((await request.body()) or b"{}")
    return ok(await run_in_threadpool(testmode.set_clock, int(data.get("advance_minutes", 0))))


# --- app ------------------------------------------------------------------------
class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' blob: data:; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if request.url.path.startswith("/api"):
            resp.headers["Cache-Control"] = resp.headers.get("Cache-Control", "no-store")
        return resp


async def api_error(request, exc: ApiError):
    return JSONResponse(exc.body(), status_code=exc.status)


async def validation_error(request, exc: ValidationError):
    details = [{"field": ".".join(str(x) for x in e["loc"]), "problem": e["msg"]} for e in exc.errors()]
    return JSONResponse({"error": {"code": "SCHEMA_INVALID", "message": "The request has invalid or unknown fields.",
                                   "details": details}}, status_code=422)


async def server_error(request, exc: Exception):
    return JSONResponse({"error": {"code": "INTERNAL", "message": "Something went wrong on the server."}}, status_code=500)


async def api_404(request):
    raise not_found("Endpoint")


def index(request):
    return FileResponse(STATIC / "app" / "index.html", headers={"Cache-Control": "no-cache"})


def client_route(request):
    path = request.url.path
    if path == "/api" or path.startswith("/api/") or path == "/static" or path.startswith("/static/"):
        return JSONResponse({"error": {"code": "NOT_FOUND", "message": "Resource not found."}}, status_code=404)
    if Path(request.path_params["path"]).suffix:
        return JSONResponse({"error": {"code": "NOT_FOUND", "message": "Resource not found."}}, status_code=404)
    return index(request)


def build_app() -> Starlette:
    db.connect()
    ledger.initialize()

    @asynccontextmanager
    async def lifespan(_app):
        await run_in_threadpool(retention.purge_expired)
        yield

    all_routes = routes + [
        Route("/api/{rest:path}", api_404, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
        Route("/", index),
        Mount("/static", StaticFiles(directory=str(STATIC)), name="static"),
        Route("/{path:path}", client_route),
    ]
    return Starlette(routes=all_routes, middleware=[Middleware(SecurityHeaders)], lifespan=lifespan,
                     exception_handlers={ApiError: api_error, ValidationError: validation_error, Exception: server_error})


app = build_app()
