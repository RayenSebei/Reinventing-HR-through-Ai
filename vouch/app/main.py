"""HTTP API (Starlette) and static screens.

All API routes live under /api. Errors are JSON: {"error": {"code", "message"}}.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import cases, config, dashboard, db, gateway, ledger, schemas, testmode
from .errors import ApiError, invalid, not_found
from .security import check_password, current_user, issue_token, require_role

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


def ok(data, status=200):
    return JSONResponse(data, status_code=status)


# --- auth -------------------------------------------------------------------
_fails: dict[str, list[float]] = defaultdict(list)


@api("POST", "/auth/login")
async def login(request: Request):
    body = await body_as(request, schemas.Login)
    key = body.email.lower()
    now = time.time()
    _fails[key] = [t for t in _fails[key] if now - t < 300]
    if len(_fails[key]) >= 10:
        raise ApiError(429, "TOO_MANY_ATTEMPTS", "Too many failed logins. Wait 5 minutes.")
    u = db.one("SELECT * FROM users WHERE lower(email)=?", (key,))
    if not u or not check_password(body.password, u["pw_hash"]):
        _fails[key].append(now)
        raise ApiError(401, "BAD_CREDENTIALS", "Wrong email or password.")
    _fails.pop(key, None)
    return ok({"token": issue_token(u["id"]), "user": {"id": u["id"], "email": u["email"], "name": u["name"], "role": u["role"]}})


@api("GET", "/auth/me")
async def me(request: Request):
    return ok(current_user(request))


@api("GET", "/users")
async def users(request: Request):
    u = current_user(request)
    no_query(request)
    # Names and roles only, so a recruiter can pick the hiring manager for a case.
    return ok([dict(r) for r in db.q("SELECT id, name, role FROM users ORDER BY role, name")])


@api("GET", "/meta")
async def meta(request: Request):
    return ok({"model_mode": config.MODEL_MODE, "test_mode": config.TEST_MODE,
               "n8n_delivery": bool(config.N8N_WEBHOOK_URL), "approval_minutes": config.APPROVAL_MINUTES,
               "data_handling": {
                   "retention_days": config.RETENTION_DAYS,
                   "statement": "Original CVs stay on the Vouch server. Only visible, personal-data-removed text is sent "
                                "to an AI model. The Trust Ledger stores IDs and hashes, never CV text or contact details."}})


# --- cases ------------------------------------------------------------------
@api("GET", "/dashboard/overview")
async def dashboard_overview(request: Request):
    user = current_user(request)
    params = list(request.query_params.multi_items())
    if any(key != "case_id" for key, _ in params) or len(params) > 1:
        raise invalid("Only one optional case_id query parameter is allowed.")
    case_id = request.query_params.get("case_id")
    if case_id is not None and not case_id.strip():
        raise invalid("case_id must not be empty.")
    return ok(dashboard.overview(user, case_id))


@api("GET", "/cases")
async def list_cases(request: Request):
    u = current_user(request)
    return ok(cases.list_cases(u, *paging(request)))


@api("POST", "/cases")
async def create_case(request: Request):
    u = current_user(request)
    return ok(cases.create_case(u, await body_as(request, schemas.CaseCreate)), 201)


@api("GET", "/cases/{case_id}")
async def get_case(request: Request):
    u = current_user(request)
    no_query(request)
    return ok(cases.get_case(u, request.path_params["case_id"]))


@api("PUT", "/cases/{case_id}/criteria")
async def set_criteria(request: Request):
    u = current_user(request)
    return ok(cases.set_criteria(u, request.path_params["case_id"], await body_as(request, schemas.CriteriaSet)))


@api("POST", "/cases/{case_id}/criteria/confirm")
async def confirm_criteria(request: Request):
    u = current_user(request)
    await body_as(request, schemas.Empty)
    return ok(cases.confirm_criteria(u, request.path_params["case_id"]))


@api("POST", "/cases/{case_id}/candidates")
async def upload(request: Request):
    u = current_user(request)
    case_id = request.path_params["case_id"]
    # Check access before reading a large body.
    from .security import require_case_write
    require_case_write(u, case_id)
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
        results.append(cases.upload_cv(u, case_id, f.filename, data))
    return ok(results[0] if len(results) == 1 else results, 201)


@api("GET", "/cases/{case_id}/candidates")
async def list_candidates(request: Request):
    u = current_user(request)
    return ok(cases.list_candidates(u, request.path_params["case_id"], *paging(request)))


@api("GET", "/candidates/{cand_id}")
async def get_candidate(request: Request):
    u = current_user(request)
    no_query(request)
    return ok(cases.get_candidate(u, request.path_params["cand_id"]))


@api("GET", "/candidates/{cand_id}/dossier")
async def get_dossier(request: Request):
    u = current_user(request)
    no_query(request)
    return ok(cases.dossier(u, request.path_params["cand_id"]))


@api("POST", "/candidates/{cand_id}/dossier")
async def regen_dossier(request: Request):
    u = current_user(request)
    await body_as(request, schemas.Empty)     # a client can't point the dossier at another document
    return ok(cases.regenerate_dossier(u, request.path_params["cand_id"]))


@api("GET", "/documents/{doc_id}/extraction")
async def extraction(request: Request):
    u = current_user(request)
    return ok(cases.extraction(u, request.path_params["doc_id"]))


@api("GET", "/documents/{doc_id}/findings")
async def doc_findings(request: Request):
    u = current_user(request)
    return ok(cases.document_findings(u, request.path_params["doc_id"]))


@api("GET", "/documents/{doc_id}/pages/{page:int}.png")
async def page_png(request: Request):
    u = current_user(request)
    png = cases.page_png(u, request.path_params["doc_id"], request.path_params["page"])
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@api("POST", "/cases/{case_id}/ranking")
async def draft_ranking(request: Request):
    u = current_user(request)
    await body_as(request, schemas.Empty)
    return ok(cases.draft_ranking(u, request.path_params["case_id"]), 201)


@api("GET", "/cases/{case_id}/ranking")
async def get_ranking(request: Request):
    u = current_user(request)
    return ok(cases.get_ranking(u, request.path_params["case_id"]))


@api("POST", "/cases/{case_id}/ranking/{version:int}/confirm")
async def confirm_ranking(request: Request):
    u = current_user(request)
    await body_as(request, schemas.Empty)
    return ok(cases.confirm_ranking(u, request.path_params["case_id"], request.path_params["version"]))


# --- proposals, approvals, gateway --------------------------------------------
@api("POST", "/cases/{case_id}/proposals")
async def create_proposal(request: Request):
    u = current_user(request)
    return ok(gateway.create_proposal(u, request.path_params["case_id"], await body_as(request, schemas.ProposalCreate)), 201)


@api("GET", "/cases/{case_id}/proposals")
async def list_proposals(request: Request):
    u = current_user(request)
    paging(request)
    return ok(gateway.list_proposals(u, request.path_params["case_id"]))


@api("GET", "/proposals/{pid}")
async def get_proposal(request: Request):
    u = current_user(request)
    return ok(gateway.get_proposal(u, request.path_params["pid"]))


@api("PATCH", "/proposals/{pid}")
async def edit_proposal(request: Request):
    u = current_user(request)
    return ok(gateway.edit_proposal(u, request.path_params["pid"], await body_as(request, schemas.ProposalEdit)))


@api("POST", "/proposals/{pid}/approve")
async def approve(request: Request):
    u = current_user(request)
    await body_as(request, schemas.Comment)
    return ok(gateway.decide(u, request.path_params["pid"], "approved"))


@api("POST", "/proposals/{pid}/reject")
async def reject(request: Request):
    u = current_user(request)
    await body_as(request, schemas.Comment)
    return ok(gateway.decide(u, request.path_params["pid"], "rejected"))


@api("POST", "/proposals/{pid}/execute")
async def execute(request: Request):
    u = current_user(request)
    await body_as(request, schemas.Empty)     # the gateway never accepts a payload from the client
    return ok(gateway.execute(u, request.path_params["pid"]))


@api("GET", "/cases/{case_id}/outbox")
async def outbox(request: Request):
    u = current_user(request)
    return ok(gateway.outbox(u, request.path_params["case_id"]))


# --- ledger & assurance ---------------------------------------------------------
@api("GET", "/ledger")
async def get_ledger(request: Request):
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
async def verify_ledger(request: Request):
    u = current_user(request)
    require_role(u, "auditor", "hr_admin")
    return ok(ledger.verify())


@api("GET", "/assurance/latest")
async def assurance_latest(request: Request):
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
    u = current_user(request)
    require_role(u, "recruiter", "hiring_manager", "hr_admin", "auditor")
    await body_as(request, schemas.Empty)
    p = _run["proc"]
    if p is not None and p.poll() is None:
        return ok({"started": False, "running": True}, 202)
    _run["proc"] = subprocess.Popen([sys.executable, str(config.REPO / "sentinel_hr" / "runner.py"), "--spawn"],
                                    cwd=str(config.REPO), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ledger.record(u["id"], "ASSURANCE_RUN_STARTED", None, None, {})
    return ok({"started": True, "running": True}, 202)


@api("GET", "/assurance/status")
async def assurance_status(request: Request):
    current_user(request)
    p = _run["proc"]
    return ok({"running": p is not None and p.poll() is None})


# --- test mode ----------------------------------------------------------------------
@api("POST", "/_test/reset")
async def test_reset(request: Request):
    testmode.guard(request)
    return ok(testmode.reset())


@api("POST", "/_test/clock")
async def test_clock(request: Request):
    testmode.guard(request)
    data = json.loads((await request.body()) or b"{}")
    return ok(testmode.set_clock(int(data.get("advance_minutes", 0))))


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


async def index(request):
    return FileResponse(STATIC / "app" / "index.html", headers={"Cache-Control": "no-cache"})


async def legacy_index(request):
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


def build_app() -> Starlette:
    db.connect()
    all_routes = routes + [
        Route("/api/{rest:path}", api_404, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
        Route("/", index),
        Route("/legacy", legacy_index),
        Mount("/static", StaticFiles(directory=str(STATIC)), name="static"),
    ]
    return Starlette(routes=all_routes, middleware=[Middleware(SecurityHeaders)],
                     exception_handlers={ApiError: api_error, ValidationError: validation_error, Exception: server_error})


app = build_app()
