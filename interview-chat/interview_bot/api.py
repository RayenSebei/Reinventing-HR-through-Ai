"""HTTP API + pages (Starlette, the ASGI toolkit FastAPI is built on).

Run alone:      uvicorn interview_bot.api:app
Inside FastAPI: main_app.mount("/interview-bot", create_app())
"""
import functools
import mimetypes
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import approvals, db, engine, ledger, services
from .config import settings
from .security import (SecurityHeadersMiddleware, candidate_limiter, issue_staff_token, login_limiter,
                       read_staff_token, sha256, verify_password)

STATIC = Path(__file__).parent / "static"
# Windows registries sometimes map these wrongly; browsers refuse scripts with the wrong type (nosniff).
mimetypes.add_type("text/javascript", ".js")
MAX_JSON_BYTES = 64 * 1024


# ---------------------------------------------------------------- helpers

class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def err(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def handler(fn):
    """Uniform error handling: known errors -> clean JSON, unknown -> generic 500 (no stack traces leaked)."""
    @functools.wraps(fn)
    async def wrapper(request: Request):
        try:
            return await fn(request)
        except (ApiError, services.ServiceError, approvals.GatewayError) as e:
            return err(e.status, e.message)
        except engine.EngineError as e:
            return err(409, str(e))
        except ValidationError as e:
            return err(422, "Invalid input: " + "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:5]))
    return wrapper


async def body(request: Request, model: type[BaseModel]):
    raw = await request.body()
    if len(raw) > MAX_JSON_BYTES:
        raise ApiError(413, "Request too large")
    try:
        return model.model_validate_json(raw or b"{}")
    except ValidationError:
        raise
    except ValueError as exc:
        raise ApiError(400, "Malformed JSON") from exc


def staff(request: Request, roles: set | None = None) -> dict:
    auth = request.headers.get("authorization", "")
    payload = read_staff_token(auth[7:]) if auth.lower().startswith("bearer ") else None
    if payload is None:
        raise ApiError(401, "Login required")
    user = db.one("SELECT id, username, display_name, role FROM users WHERE id=?", (payload["sub"],))
    if user is None:
        raise ApiError(401, "Login required")
    if roles and user["role"] not in roles:
        raise ApiError(403, "Your role is not allowed to do this")
    return user


ANY_STAFF = {"recruiter", "hiring_manager", "hr_admin", "auditor"}
HR_STAFF = {"recruiter", "hiring_manager", "hr_admin"}


def int_param(request: Request, name: str) -> int:
    try:
        return int(request.path_params[name])
    except (KeyError, ValueError) as exc:
        raise ApiError(400, f"Invalid {name}") from exc


# ---------------------------------------------------------------- models

class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ApproveIn(BaseModel):
    payload_hash: str = Field(min_length=64, max_length=64)


class RejectIn(BaseModel):
    note: str = Field(default="", max_length=500)


class PayloadIn(BaseModel):
    payload: dict


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(advance|hold|reject)$")
    reason: str = Field(min_length=1, max_length=1000)


class StartIn(BaseModel):
    language: str = Field(pattern="^(en|fr|ar)$")
    consent: bool


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


# ---------------------------------------------------------------- staff endpoints

@handler
async def login(request: Request):
    ip = request.client.host if request.client else "?"
    if not login_limiter.allow(ip):
        raise ApiError(429, "Too many attempts, wait a minute")
    data = await body(request, LoginIn)
    user = db.one("SELECT * FROM users WHERE username=?", (data.username,))
    if user is None or not verify_password(data.password, user["pw_hash"]):
        ledger.append(data.username[:64], "auth.login_failed", {})
        raise ApiError(401, "Wrong username or password")
    ledger.append(user["username"], "auth.login", {})
    return JSONResponse({"token": issue_staff_token(user["id"], user["role"]),
                         "user": {"username": user["username"], "display_name": user["display_name"], "role": user["role"]}})


@handler
async def me(request: Request):
    return JSONResponse(staff(request))


@handler
async def jobs_list(request: Request):
    staff(request, ANY_STAFF)
    rows = db.many("SELECT j.id, j.title, j.description, (SELECT COUNT(*) FROM candidates c WHERE c.job_id=j.id "
                   "AND c.status!='erased') AS candidates FROM jobs j ORDER BY j.id")
    return JSONResponse(rows)


@handler
async def jobs_create(request: Request):
    user = staff(request, {"recruiter", "hr_admin"})
    raw = await request.body()
    if len(raw) > MAX_JSON_BYTES:
        raise ApiError(413, "Request too large")
    import json
    try:
        spec = json.loads(raw)
    except ValueError as exc:
        raise ApiError(400, "Malformed JSON") from exc
    return JSONResponse({"id": services.create_job(spec, user)}, status_code=201)


@handler
async def job_get(request: Request):
    staff(request, ANY_STAFF)
    job = db.one("SELECT * FROM jobs WHERE id=?", (int_param(request, "job_id"),))
    if job is None:
        raise ApiError(404, "Job not found")
    return JSONResponse({"id": job["id"], "title": job["title"], "description": job["description"],
                         "spec": db.loads(job["spec_json"])})


@handler
async def job_candidates(request: Request):
    staff(request, ANY_STAFF)
    job_id = int_param(request, "job_id")
    rows = db.many("SELECT c.id, c.alias, c.status, c.created_at, c.cv_findings_json, "
                   "(SELECT state FROM interview_sessions s WHERE s.candidate_id=c.id AND s.state!='revoked' "
                   " ORDER BY s.id DESC LIMIT 1) AS interview_state "
                   "FROM candidates c WHERE c.job_id=? AND c.status!='erased' ORDER BY c.id", (job_id,))
    for r in rows:
        findings = db.loads(r.pop("cv_findings_json")) or {}
        r["hidden_content"] = findings.get("hidden_count", 0)
    return JSONResponse(rows)


@handler
async def job_shortlist(request: Request):
    user = staff(request, ANY_STAFF)
    return JSONResponse(services.shortlist(int_param(request, "job_id"), user))


@handler
async def candidate_upload(request: Request):
    user = staff(request, {"recruiter", "hr_admin"})
    length = int(request.headers.get("content-length") or 0)
    if length > settings.max_upload_bytes + 64 * 1024:
        raise ApiError(413, "File too large")
    form = await request.form(max_files=1, max_fields=10, max_part_size=settings.max_upload_bytes)
    upload = form.get("cv")
    if upload is None or not hasattr(upload, "read"):
        raise ApiError(400, "Attach the CV in the 'cv' field")
    data = await upload.read(settings.max_upload_bytes + 1)
    cid = services.add_candidate(int_param(request, "job_id"), str(form.get("full_name", "")),
                                 str(form.get("email", "")), upload.filename or "cv", data, user)
    return JSONResponse({"id": cid}, status_code=201)


@handler
async def candidate_get(request: Request):
    user = staff(request, ANY_STAFF)
    reveal = request.query_params.get("reveal") == "1" and user["role"] in HR_STAFF
    return JSONResponse(services.candidate_view(int_param(request, "cid"), user, reveal=reveal))


@handler
async def candidate_transcript(request: Request):
    user = staff(request, ANY_STAFF)
    return JSONResponse(services.transcript(int_param(request, "cid"), user))


@handler
async def candidate_report(request: Request):
    user = staff(request, ANY_STAFF)
    cid = int_param(request, "cid")
    if not db.one("SELECT 1 FROM candidates WHERE id=? AND status!='erased'", (cid,)):
        raise ApiError(404, "Candidate not found")
    return JSONResponse(services.get_report(cid, user))


@handler
async def candidate_invite(request: Request):
    user = staff(request, {"recruiter", "hr_admin"})
    cid = int_param(request, "cid")
    c = db.one("SELECT * FROM candidates WHERE id=? AND status!='erased'", (cid,))
    if c is None:
        raise ApiError(404, "Candidate not found")
    if db.one("SELECT 1 FROM proposals WHERE candidate_id=? AND kind='interview_invite' AND status='pending'", (cid,)):
        raise ApiError(409, "An invitation is already waiting for approval")
    job = db.one("SELECT * FROM jobs WHERE id=?", (c["job_id"],))
    return JSONResponse(approvals.propose("interview_invite", cid, approvals.draft_invite(c, job), user), status_code=201)


@handler
async def candidate_decision(request: Request):
    user = staff(request, HR_STAFF)
    data = await body(request, DecisionIn)
    return JSONResponse(services.decide(int_param(request, "cid"), data.decision, data.reason, user))


@handler
async def candidate_erase(request: Request):
    user = staff(request, {"hr_admin"})
    services.erase_candidate(int_param(request, "cid"), user)
    return JSONResponse({"erased": True})


@handler
async def proposals_list(request: Request):
    staff(request, ANY_STAFF)
    status = request.query_params.get("status", "pending")
    rows = db.many("SELECT p.id, p.kind, p.candidate_id, c.alias, p.payload_json, p.payload_hash, p.status, p.proposed_at, "
                   "u.display_name AS proposed_by_name, p.proposed_by FROM proposals p JOIN candidates c ON c.id=p.candidate_id "
                   "JOIN users u ON u.id=p.proposed_by WHERE p.status=? ORDER BY p.id DESC LIMIT 100", (status,))
    for r in rows:
        r["payload"] = db.loads(r.pop("payload_json"))
    return JSONResponse(rows)


@handler
async def proposal_approve(request: Request):
    user = staff(request, HR_STAFF)
    data = await body(request, ApproveIn)
    return JSONResponse(approvals.approve(int_param(request, "pid"), user, data.payload_hash))


@handler
async def proposal_reject(request: Request):
    user = staff(request, HR_STAFF)
    data = await body(request, RejectIn)
    approvals.reject(int_param(request, "pid"), user, data.note)
    return JSONResponse({"rejected": True})


@handler
async def proposal_update(request: Request):
    user = staff(request, HR_STAFF)
    data = await body(request, PayloadIn)
    return JSONResponse(approvals.update(int_param(request, "pid"), data.payload, user))


@handler
async def outbox(request: Request):
    staff(request, HR_STAFF)
    return JSONResponse(db.many("SELECT o.id, o.to_addr, o.subject, o.body, o.created_at, p.kind FROM outbox o "
                                "LEFT JOIN proposals p ON p.id=o.proposal_id ORDER BY o.id DESC LIMIT 50"))


@handler
async def ledger_list(request: Request):
    staff(request, ANY_STAFF)
    cid = request.query_params.get("candidate_id")
    return JSONResponse(ledger.entries(200, int(cid) if cid and cid.isdigit() else None))


@handler
async def ledger_verify(request: Request):
    staff(request, ANY_STAFF)
    return JSONResponse(ledger.verify())


# ---------------------------------------------------------------- candidate endpoints

def candidate_session(request: Request) -> dict:
    token = request.headers.get("x-interview-token", "")
    if not (20 <= len(token) <= 100):
        raise ApiError(401, "Invalid or expired interview link")
    if not candidate_limiter.allow(sha256(token)):
        raise ApiError(429, "Too many requests, slow down a little")
    session = db.one("SELECT * FROM interview_sessions WHERE token_hash=?", (sha256(token),))
    if session is None or session["state"] in ("revoked", "expired"):
        raise ApiError(401, "Invalid or expired interview link")
    if session["expires_at"] < db.now() and session["state"] != "completed":
        conn = db.connect()
        try:
            conn.execute("UPDATE interview_sessions SET state='expired' WHERE id=?", (session["id"],))
        finally:
            conn.close()
        raise ApiError(401, "Invalid or expired interview link")
    return session


@handler
async def iv_info(request: Request):
    s = candidate_session(request)
    if engine.expire_if_time_up(s):
        services.generate_report(s["candidate_id"])
        s = db.one("SELECT * FROM interview_sessions WHERE id=?", (s["id"],))
    job = db.one("SELECT j.title, j.description FROM jobs j JOIN candidates c ON c.job_id=j.id WHERE c.id=?",
                 (s["candidate_id"],))
    return JSONResponse({
        "job_title": job["title"], "job_description": job["description"], "state": s["state"],
        "language": s["language"], "expires_at": s["expires_at"],
        "history": engine.history(s["id"]) if s["state"] != "invited" else [],
        "timer": engine.timer(s),
        "notice": {
            "en": "This first interview is run by an AI assistant. Your answers and your CV are read by a recruiter, "
                  "who makes every decision. The assistant does not analyse your personality or emotions and does not "
                  f"give a score. Your data is kept at most {settings.retention_days} days and you can ask for it to be "
                  "deleted. Do not share sensitive personal information (health, religion, family situation). "
                  f"You have {settings.interview_time_limit_min} minutes once you start; a timer shows the time left.",
            "fr": "Ce premier entretien est mené par un assistant IA. Vos réponses et votre CV sont lus par un recruteur, "
                  "qui prend toutes les décisions. L'assistant n'analyse ni votre voix, ni votre visage, ni vos émotions "
                  f"et ne donne pas de note. Vos données sont conservées au maximum {settings.retention_days} jours et "
                  "vous pouvez demander leur suppression. Ne partagez pas d'informations sensibles (santé, religion, "
                  "situation familiale). Vous disposez de {} minutes une fois l'entretien commencé ; un minuteur "
                  "affiche le temps restant.".format(settings.interview_time_limit_min),
            "ar": "تجري هذه المقابلة الأولى بواسطة مساعد ذكاء اصطناعي. يقرأ أحد المسؤولين عن التوظيف إجاباتك وسيرتك الذاتية "
                  "وهو من يتخذ كل القرارات. لا يحلل المساعد صوتك أو وجهك أو مشاعرك ولا يعطي أي علامة. "
                  f"نحتفظ ببياناتك {settings.retention_days} يوما كحد أقصى ويمكنك طلب حذفها. "
                  "لا تشارك معلومات حساسة (الصحة، الدين، الوضع العائلي). "
                  f"لديك {settings.interview_time_limit_min} دقيقة بعد بدء المقابلة، ويظهر مؤقت الوقت المتبقي.",
        },
    })


@handler
async def iv_start(request: Request):
    s = candidate_session(request)
    data = await body(request, StartIn)
    if not data.consent:
        raise ApiError(400, "Consent is required to start. You can also contact the recruiter for another format.")
    job = db.one("SELECT j.* FROM jobs j JOIN candidates c ON c.job_id=j.id WHERE c.id=?", (s["candidate_id"],))
    engine.start(s, job, data.language)
    ledger.append(f"candidate:{s['candidate_id']}", "interview.started",
                  {"candidate_id": s["candidate_id"], "session_id": s["id"], "language": data.language, "consent": True})
    return JSONResponse({"history": engine.history(s["id"])})


@handler
async def iv_message(request: Request):
    s = candidate_session(request)
    data = await body(request, MessageIn)
    result = engine.handle_answer(s["id"], data.text)
    if result["flagged"]:
        ledger.append(f"candidate:{s['candidate_id']}", "interview.manipulation_flagged",
                      {"candidate_id": s["candidate_id"], "session_id": s["id"]})
    if result["completed"]:
        ledger.append(f"candidate:{s['candidate_id']}", "interview.completed",
                      {"candidate_id": s["candidate_id"], "session_id": s["id"]})
        services.generate_report(s["candidate_id"])
    return JSONResponse({"bot": result["bot"], "completed": result["completed"]})


@handler
async def iv_finish(request: Request):
    s = candidate_session(request)
    if engine.expire_if_time_up(s):
        services.generate_report(s["candidate_id"])
        return JSONResponse({"completed": True, "history": engine.history(s["id"])})
    engine.finish_early(s["id"])
    ledger.append(f"candidate:{s['candidate_id']}", "interview.ended_early",
                  {"candidate_id": s["candidate_id"], "session_id": s["id"]})
    services.generate_report(s["candidate_id"])
    return JSONResponse({"completed": True, "history": engine.history(s["id"])})


# ---------------------------------------------------------------- pages

async def page_hr(request: Request):
    return FileResponse(STATIC / "hr.html")


async def page_interview(request: Request):
    return FileResponse(STATIC / "interview.html")


async def root(request: Request):
    return RedirectResponse(request.url_for("hr"))


async def health(request: Request):
    return JSONResponse({"ok": True, "llm_provider": settings.llm_provider})


routes = [
    Route("/", root),
    Route("/hr", page_hr, name="hr"),
    Route("/interview", page_interview),
    Route("/health", health),
    Route("/api/auth/login", login, methods=["POST"]),
    Route("/api/me", me),
    Route("/api/jobs", jobs_list),
    Route("/api/jobs", jobs_create, methods=["POST"]),
    Route("/api/jobs/{job_id}", job_get),
    Route("/api/jobs/{job_id}/candidates", job_candidates),
    Route("/api/jobs/{job_id}/candidates", candidate_upload, methods=["POST"]),
    Route("/api/jobs/{job_id}/shortlist", job_shortlist),
    Route("/api/candidates/{cid}", candidate_get),
    Route("/api/candidates/{cid}/transcript", candidate_transcript),
    Route("/api/candidates/{cid}/report", candidate_report),
    Route("/api/candidates/{cid}/invite", candidate_invite, methods=["POST"]),
    Route("/api/candidates/{cid}/decision", candidate_decision, methods=["POST"]),
    Route("/api/candidates/{cid}/erase", candidate_erase, methods=["POST"]),
    Route("/api/proposals", proposals_list),
    Route("/api/proposals/{pid}", proposal_update, methods=["PUT"]),
    Route("/api/proposals/{pid}/approve", proposal_approve, methods=["POST"]),
    Route("/api/proposals/{pid}/reject", proposal_reject, methods=["POST"]),
    Route("/api/outbox", outbox),
    Route("/api/ledger", ledger_list),
    Route("/api/ledger/verify", ledger_verify),
    Route("/api/interview/info", iv_info),
    Route("/api/interview/start", iv_start, methods=["POST"]),
    Route("/api/interview/message", iv_message, methods=["POST"]),
    Route("/api/interview/finish", iv_finish, methods=["POST"]),
    Mount("/static", StaticFiles(directory=STATIC), name="static"),
]


def create_app(seed: bool | None = None) -> Starlette:
    db.init_db()
    if settings.demo_seed if seed is None else seed:
        from .seed import seed_demo
        seed_demo()
    services.purge_expired()
    return Starlette(routes=routes, middleware=[Middleware(SecurityHeadersMiddleware)])


_app = None


def __getattr__(name):
    """Lazy `app` so importing this module (tests, FastAPI mounting) has no side effects."""
    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(name)
