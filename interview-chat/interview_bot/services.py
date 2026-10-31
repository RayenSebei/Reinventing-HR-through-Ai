"""Business operations used by the API (and usable directly from your own app)."""
from . import approvals, db, engine, evaluator, ingestion, ledger
from .config import settings


class ServiceError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


STAFF_WRITE = {"recruiter", "hiring_manager", "hr_admin"}


def require_role(user: dict, roles: set) -> None:
    if user["role"] not in roles:
        raise ServiceError(403, "Your role is not allowed to do this")


# ---------------------------------------------------------------- jobs

def validate_job_spec(spec: dict) -> None:
    if not isinstance(spec, dict) or not spec.get("title"):
        raise ServiceError(400, "Job spec needs a title")
    reqs = spec.get("requirements")
    if not isinstance(reqs, list) or not 1 <= len(reqs) <= 15:
        raise ServiceError(400, "Job spec needs 1 to 15 requirements")
    ids = set()
    for r in reqs:
        if not r.get("id") or not r.get("label") or r["id"] in ids:
            raise ServiceError(400, "Each requirement needs a unique id and a label")
        ids.add(r["id"])
    qs = spec.get("core_questions")
    if not isinstance(qs, list) or not 1 <= len(qs) <= 12:
        raise ServiceError(400, "Job spec needs 1 to 12 core questions")
    for q in qs:
        if not q.get("id") or not q.get("text") or not set(q.get("requirement_ids", [])) <= ids:
            raise ServiceError(400, f"Invalid question {q.get('id')}")


def create_job(spec: dict, user: dict) -> int:
    require_role(user, {"recruiter", "hr_admin"})
    validate_job_spec(spec)
    with db.tx() as conn:
        cur = conn.execute("INSERT INTO jobs (title, description, spec_json, created_by, created_at) VALUES (?,?,?,?,?)",
                           (spec["title"], spec.get("description", ""), db.dumps(spec), user["id"], db.now()))
        ledger.append(user["username"], "job.created", {"job_id": cur.lastrowid, "title": spec["title"]}, conn=conn)
        return cur.lastrowid


# ---------------------------------------------------------------- candidates

def add_candidate(job_id: int, full_name: str, email: str, filename: str, data: bytes, user: dict) -> int:
    require_role(user, {"recruiter", "hr_admin"})
    job = db.one("SELECT * FROM jobs WHERE id=?", (job_id,))
    if job is None:
        raise ServiceError(404, "Job not found")
    full_name, email = (full_name or "").strip()[:120], (email or "").strip()[:200]
    if not full_name or "@" not in email:
        raise ServiceError(400, "Name and a valid email are required")
    if len(data) > settings.max_upload_bytes:
        raise ServiceError(413, "File too large")
    try:
        ing = ingestion.ingest_cv(data, filename, [full_name])
    except ingestion.IngestionError as exc:
        raise ServiceError(400, str(exc)) from exc
    except Exception as exc:  # malformed PDF/DOCX
        raise ServiceError(400, "Could not read this file") from exc

    spec = db.loads(job["spec_json"])
    cv_ev = evaluator.cv_evidence(spec, ing["text_minimised"])
    with db.tx() as conn:
        n = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0] + 1
        alias = f"Candidate C-{n:04d}"
        cur = conn.execute(
            "INSERT INTO candidates (job_id, alias, full_name, contact_email, cv_filename, cv_sha256, cv_text_minimised, "
            "cv_findings_json, cv_evidence_json, status, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (job_id, alias, full_name, email, (filename or "cv")[:120], ing["sha256"], ing["text_minimised"],
             db.dumps(ing["findings"]), db.dumps(cv_ev), "screened", user["id"], db.now()))
        ledger.append(user["username"], "candidate.added",
                      {"candidate_id": cur.lastrowid, "job_id": job_id, "cv_sha256": ing["sha256"],
                       "hidden_content": ing["findings"]["hidden_count"],
                       "cv_quotes_dropped": cv_ev["unverified_quotes_dropped"], "model": cv_ev["model"],
                       "prompt_version": cv_ev["prompt_version"]}, conn=conn)
        cid = cur.lastrowid
    generate_report(cid)          # CV-only report so the shortlist works before any interview
    return cid


def _session_for(candidate_id: int):
    return db.one("SELECT * FROM interview_sessions WHERE candidate_id=? AND state!='revoked' ORDER BY id DESC LIMIT 1",
                  (candidate_id,))


def candidate_view(candidate_id: int, user: dict, reveal: bool = False) -> dict:
    c = db.one("SELECT * FROM candidates WHERE id=?", (candidate_id,))
    if c is None:
        raise ServiceError(404, "Candidate not found")
    job = db.one("SELECT id, title, spec_json FROM jobs WHERE id=?", (c["job_id"],))
    spec = db.loads(job["spec_json"])
    cv_ev = db.loads(c["cv_evidence_json"]) or {"quotes": {}}
    session = _session_for(candidate_id)
    report = db.one("SELECT report_json, created_at FROM reports WHERE candidate_id=? ORDER BY id DESC LIMIT 1",
                    (candidate_id,))
    decisions = db.many("SELECT d.decision, d.reason, d.created_at, u.display_name AS by FROM decisions d "
                        "JOIN users u ON u.id=d.decided_by WHERE candidate_id=? ORDER BY d.id", (candidate_id,))
    proposals = db.many("SELECT id, kind, status, payload_json, payload_hash, proposed_at FROM proposals "
                        "WHERE candidate_id=? ORDER BY id", (candidate_id,))
    view = {
        "id": c["id"], "alias": c["alias"], "job": {"id": job["id"], "title": job["title"]}, "status": c["status"],
        "name": c["full_name"] if reveal else None, "email": c["contact_email"] if reveal else None,
        "cv_filename": c["cv_filename"], "cv_text": c["cv_text_minimised"],
        "cv_findings": db.loads(c["cv_findings_json"]),
        "cv_evidence": [{"id": r["id"], "requirement": r["label"], "must_have": bool(r.get("must_have")),
                         "quotes": cv_ev["quotes"].get(r["id"], [])} for r in spec["requirements"]],
        "interview": {"state": session["state"], "language": session["language"],
                      "expires_at": session["expires_at"]} if session else None,
        "report_available": report is not None,
        "decisions": decisions,
        "proposals": [{**{k: v for k, v in p.items() if k != "payload_json"}, "payload": db.loads(p["payload_json"])}
                      for p in proposals],
    }
    if reveal:
        ledger.append(user["username"], "candidate.identity_revealed", {"candidate_id": candidate_id})
    return view


def transcript(candidate_id: int, user: dict) -> list:
    session = _session_for(candidate_id)
    if session is None:
        return []
    rows = db.many("SELECT sender, question_id, text, flags_json, created_at FROM messages WHERE session_id=? ORDER BY id",
                   (session["id"],))
    ledger.append(user["username"], "transcript.viewed", {"candidate_id": candidate_id})
    return [{"sender": r["sender"], "question_id": r["question_id"], "text": r["text"],
             "flags": db.loads(r["flags_json"]), "ts": r["created_at"]} for r in rows]


def generate_report(candidate_id: int) -> dict:
    c = db.one("SELECT * FROM candidates WHERE id=?", (candidate_id,))
    job = db.one("SELECT * FROM jobs WHERE id=?", (c["job_id"],))
    spec = db.loads(job["spec_json"])
    cv_ev = db.loads(c["cv_evidence_json"]) or {"quotes": {}}
    session = _session_for(candidate_id)
    iv_ev, flagged, short = None, [], 0
    if session and session["state"] == "completed":
        lines, flagged, short = engine.candidate_lines(session["id"])
        iv_ev = evaluator.interview_evidence(spec, lines)
    report = evaluator.build_report(spec, c, cv_ev, iv_ev, flagged, short, db.loads(c["cv_findings_json"]) or {})
    with db.tx() as conn:
        conn.execute("INSERT INTO reports (candidate_id, session_id, report_json, created_at) VALUES (?,?,?,?)",
                     (candidate_id, session["id"] if session else None, db.dumps(report), db.now()))
        if iv_ev is not None:
            conn.execute("UPDATE candidates SET status='interviewed' WHERE id=? AND status IN ('invited','screened')",
                         (candidate_id,))
        ledger.append("system", "report.generated",
                      {"candidate_id": candidate_id, "summary": report["summary"],
                       "provenance": report["provenance"]}, conn=conn)
    return report


def get_report(candidate_id: int, user: dict) -> dict:
    row = db.one("SELECT report_json FROM reports WHERE candidate_id=? ORDER BY id DESC LIMIT 1", (candidate_id,))
    report = db.loads(row["report_json"]) if row else generate_report(candidate_id)
    with db.tx() as conn:
        conn.execute("INSERT OR REPLACE INTO report_views (user_id, candidate_id, viewed_at) VALUES (?,?,?)",
                     (user["id"], candidate_id, db.now()))
        ledger.append(user["username"], "report.viewed", {"candidate_id": candidate_id}, conn=conn)
    return report


def decide(candidate_id: int, decision: str, reason: str, user: dict) -> dict:
    """Record a HUMAN decision. Requires having opened the report, and a reason."""
    require_role(user, STAFF_WRITE)
    if decision not in ("advance", "hold", "reject"):
        raise ServiceError(400, "Decision must be advance, hold or reject")
    reason = (reason or "").strip()
    if len(reason) < 15:
        raise ServiceError(400, "Write a job-related reason (at least 15 characters)")
    c = db.one("SELECT * FROM candidates WHERE id=?", (candidate_id,))
    if c is None:
        raise ServiceError(404, "Candidate not found")
    if not db.one("SELECT 1 FROM report_views WHERE user_id=? AND candidate_id=?", (user["id"], candidate_id)):
        raise ServiceError(409, "Open and read the evidence report before deciding")
    job = db.one("SELECT * FROM jobs WHERE id=?", (c["job_id"],))
    result = {"decision": decision}
    with db.tx() as conn:
        conn.execute("INSERT INTO decisions (candidate_id, decision, reason, decided_by, created_at) VALUES (?,?,?,?,?)",
                     (candidate_id, decision, reason[:1000], user["id"], db.now()))
        conn.execute("UPDATE candidates SET status=? WHERE id=?",
                     ({"advance": "advanced", "hold": "on_hold", "reject": "rejected"}[decision], candidate_id))
        ledger.append(user["username"], "decision.recorded",
                      {"candidate_id": candidate_id, "decision": decision, "by_human": True}, conn=conn)
        if decision == "advance":
            # Prepared, not sent: slots go out only after someone approves them.
            result["slots_proposal"] = approvals.propose("schedule_slots", candidate_id,
                                                         approvals.draft_slots(c, job), user, conn=conn)
    return result


def shortlist(job_id: int, user: dict) -> dict:
    cands = db.many("SELECT * FROM candidates WHERE job_id=? AND status!='erased' ORDER BY id", (job_id,))
    reviewed, pending = [], []
    for c in cands:
        row = db.one("SELECT report_json FROM reports WHERE candidate_id=? ORDER BY id DESC LIMIT 1", (c["id"],))
        if row is None:
            pending.append({"id": c["id"], "alias": c["alias"], "status": c["status"]})
            continue
        rep = db.loads(row["report_json"])
        reviewed.append({"id": c["id"], "alias": c["alias"], "status": c["status"], "summary": rep["summary"],
                         "counts": rep["counts"], "flags": [f["type"] for f in rep["review_flags"]],
                         "interview_completed": rep["interview_completed"], "_key": evaluator.sort_key(rep)})
    reviewed.sort(key=lambda r: r.pop("_key"))
    for i, r in enumerate(reviewed, 1):
        r["suggested_position"] = i
    return {"notice": "Suggested review order based only on job-related evidence. It is not a decision: open each "
                      "report, read the CV and transcript, and record your own decision with a reason.",
            "candidates": reviewed, "without_report": pending}


def erase_candidate(candidate_id: int, user: dict) -> None:
    """Right to erasure: removes personal data, keeps anonymous ledger entries."""
    require_role(user, {"hr_admin"})
    with db.tx() as conn:
        conn.execute("UPDATE candidates SET full_name='[erased]', contact_email='[erased]', cv_text_minimised=NULL, "
                     "cv_evidence_json=NULL, cv_findings_json=NULL, status='erased' WHERE id=?", (candidate_id,))
        sessions = [r[0] for r in conn.execute("SELECT id FROM interview_sessions WHERE candidate_id=?", (candidate_id,))]
        for sid in sessions:
            conn.execute("DELETE FROM messages WHERE session_id=?", (sid,))
        conn.execute("UPDATE interview_sessions SET state='revoked' WHERE candidate_id=?", (candidate_id,))
        conn.execute("DELETE FROM reports WHERE candidate_id=?", (candidate_id,))
        conn.execute("UPDATE outbox SET body='[erased]', to_addr='[erased]' WHERE proposal_id IN "
                     "(SELECT id FROM proposals WHERE candidate_id=?)", (candidate_id,))
        conn.execute("UPDATE proposals SET payload_json='{}' WHERE candidate_id=? AND status!='pending'", (candidate_id,))
        conn.execute("DELETE FROM proposals WHERE candidate_id=? AND status='pending'", (candidate_id,))
        ledger.append(user["username"], "candidate.erased", {"candidate_id": candidate_id}, conn=conn)


def purge_expired() -> int:
    """Retention: erase candidates older than IB_RETENTION_DAYS and expire stale links."""
    cutoff = db.now() - settings.retention_days * 86400
    old = db.many("SELECT id FROM candidates WHERE created_at < ? AND status != 'erased'", (cutoff,))
    system = {"id": 0, "username": "retention-job", "role": "hr_admin"}
    for c in old:
        erase_candidate(c["id"], system)
    conn = db.connect()
    try:
        conn.execute("UPDATE interview_sessions SET state='expired' WHERE state IN ('invited','in_progress') AND expires_at < ?",
                     (db.now(),))
    finally:
        conn.close()
    return len(old)
