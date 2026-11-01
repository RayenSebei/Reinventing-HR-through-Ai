"""Proposals, approvals and the Action Gateway.

- The AI can only DRAFT a proposal. A proposal stores its payload and the SHA-256 of
  its canonical form.
- A hiring manager approves THAT hash. The approval expires and works once.
- The gateway is the only code that writes to the outbox (and calls n8n). It denies by
  default and re-checks everything at execution time: role, case scope, approval
  exists, not expired, not used, and the hash of the CURRENT payload equals the
  approved hash. Edit the payload after approval and execution is refused.
"""
from __future__ import annotations

import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone


from . import db, delivery, ledger, policy
from .canonical import canonical, payload_hash
from .errors import ApiError, conflict, forbidden, invalid, not_found
from .security import is_member, require_case_read, require_case_write


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _valid_start(s: str | None) -> str:
    if s is None:
        start = (db.utcnow() + timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0)
        return start.isoformat().replace("+00:00", "Z")
    try:
        dt = _parse_ts(s)
    except ValueError:
        raise invalid("start must be an ISO 8601 date-time, e.g. 2030-05-01T10:00:00Z")
    if dt.tzinfo is None:
        raise invalid("start must include a time zone (use Z for UTC).")
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    if dt < db.utcnow():
        raise invalid("start must not be in the past.")
    return dt.isoformat().replace("+00:00", "Z")


_EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+")


def _validate_payload(payload: dict) -> None:
    recipient = payload.get("recipient", "")
    subject = payload.get("subject", "")
    if "\r" in recipient or "\n" in recipient or not _EMAIL.fullmatch(recipient):
        raise invalid("recipient must be a valid email address without line breaks.")
    if "\r" in subject or "\n" in subject:
        raise invalid("subject must not contain line breaks.")
    if payload.get("kind") == "interview_invite":
        _valid_start(payload.get("start"))


def draft_text(kind: str, pseudonym: str, case_title: str, start: str, minutes: int) -> tuple[str, str]:
    """Template draft. Built only from the case and this candidate's own record."""
    if kind == "follow_up":
        return (f"Following up on your application: {case_title}",
                f"Hello,\n\nWe are still reviewing applications for {case_title} and wanted to check that you are "
                f"still interested. Please reply to this email.\n\nRegards,\nThe recruitment team")
    when = _parse_ts(start).strftime("%A %d %B %Y at %H:%M UTC")
    return (f"Interview invitation: {case_title}",
            f"Hello,\n\nThank you for applying for {case_title}. We would like to invite you to a "
            f"{minutes}-minute interview on {when}. Please reply to confirm or to suggest another time.\n\n"
            f"Regards,\nThe recruitment team")


def create_proposal(user: dict, case_id: str, body) -> dict:
    case = require_case_write(user, case_id, roles=("recruiter",))
    start = _valid_start(body.start) if body.kind == "interview_invite" else None
    pid = db.new_id("PROP")
    ts = db.now()
    with db.tx() as conn:
        cand = conn.execute("SELECT * FROM candidates WHERE id=? AND case_id=?",
                            (body.candidate_id, case_id)).fetchone()
        if not cand:
            raise not_found("Candidate")
        selected = conn.execute(
            "SELECT 1 FROM shortlisted_candidates s JOIN rankings r "
            "ON r.case_id=s.case_id AND r.version=s.ranking_version "
            "WHERE s.case_id=? AND s.candidate_id=? AND r.status='CONFIRMED'",
            (case_id, body.candidate_id)).fetchone()
        if not selected:
            raise conflict("SHORTLIST_NOT_CONFIRMED",
                           "Confirm a shortlist that explicitly includes this candidate first.")
        row = conn.execute("SELECT email FROM contact_confirmations WHERE candidate_id=?", (cand["id"],)).fetchone()
        if not row:   # D11: the CV address is only a suggestion; a recruiter must confirm it first
            raise conflict("RECIPIENT_NOT_CONFIRMED", "Confirm this candidate's email address before proposing an action.")
        subject, text = draft_text(body.kind, cand["pseudonym"], case["title"], start, body.duration_minutes)
        payload = {"case_id": case_id, "candidate_id": cand["id"], "kind": body.kind,
                   "recipient": row["email"], "start": start,
                   "duration_minutes": body.duration_minutes, "subject": subject, "body": text}
        _validate_payload(payload)
        h = payload_hash(payload)
        conn.execute("INSERT INTO proposals VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (pid, case_id, cand["id"], body.kind, canonical(payload), h, user["id"], "PENDING_APPROVAL", ts, ts))
        ledger.append(conn, user["id"], "PROPOSAL_CREATED", case_id, pid, {"payload_sha256": h, "kind": body.kind})
    return get_proposal(user, pid)


def _proposal_row(pid: str):
    p = db.one("SELECT * FROM proposals WHERE id=?", (pid,))
    if not p:
        raise not_found("Proposal")
    return p


def _latest_approval(pid: str):
    return db.one("SELECT * FROM approvals WHERE proposal_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1", (pid,))


def get_proposal(user: dict, pid: str) -> dict:
    p = _proposal_row(pid)
    require_case_read(user, p["case_id"])
    a = _latest_approval(pid)
    approval = None
    if a:
        approval = {"id": a["id"], "decision": a["decision"], "approver_id": a["approver_id"],
                    "approved_hash": a["payload_sha256"], "expires_at": a["expires_at"], "used_at": a["used_at"],
                    "matches_current_payload": a["payload_sha256"] == p["payload_sha256"]}
    return {"id": p["id"], "case_id": p["case_id"], "candidate_id": p["candidate_id"], "kind": p["kind"],
            "payload": db.loads(p["payload_json"]), "payload_sha256": p["payload_sha256"],
            "created_by": p["created_by"], "status": p["status"], "created_at": p["created_at"],
            "updated_at": p["updated_at"], "approval": approval}


def list_proposals(user: dict, case_id: str) -> list[dict]:
    require_case_read(user, case_id)
    return [get_proposal(user, r["id"]) for r in db.q("SELECT id FROM proposals WHERE case_id=? ORDER BY created_at", (case_id,))]


def edit_proposal(user: dict, pid: str, body) -> dict:
    p = _proposal_row(pid)
    require_case_write(user, p["case_id"], roles=("recruiter",))
    if p["status"] == "EXECUTED":
        raise conflict("ALREADY_EXECUTED", "This action was already carried out.")
    payload = db.loads(p["payload_json"])
    changes = body.model_dump(exclude_none=True)
    if "start" in changes:
        changes["start"] = _valid_start(changes["start"])
    payload.update(changes)
    if ("start" in changes or "duration_minutes" in changes) and "body" not in changes and payload["kind"] == "interview_invite":
        case = db.one("SELECT title FROM cases WHERE id=?", (p["case_id"],))
        payload["subject"], payload["body"] = draft_text(payload["kind"], "", case["title"], payload["start"], payload["duration_minutes"])
    _validate_payload(payload)
    h = payload_hash(payload)
    with db.tx() as conn:
        # The approval is NOT moved to the new hash. It stays bound to what the manager saw.
        conn.execute("UPDATE proposals SET payload_json=?, payload_sha256=?, updated_at=? WHERE id=?",
                     (canonical(payload), h, db.now(), pid))
        ledger.append(conn, user["id"], "PROPOSAL_EDITED", p["case_id"], pid,
                      {"old_sha256": p["payload_sha256"], "new_sha256": h, "fields": sorted(changes)})
    return get_proposal(user, pid)


def decide(user: dict, pid: str, decision: str) -> dict:
    p = _proposal_row(pid)
    require_case_read(user, p["case_id"])
    if user["role"] != "hiring_manager" or not is_member(user, p["case_id"]):
        raise forbidden("FORBIDDEN_ROLE", "Only the hiring manager on this case can approve or reject.")
    if p["created_by"] == user["id"]:
        raise forbidden("SELF_APPROVAL", "You can't approve your own proposal.")
    if p["status"] == "EXECUTED":
        raise conflict("ALREADY_EXECUTED", "This action was already carried out.")
    aid = db.new_id("APPR")
    nonce = secrets.token_hex(8)
    expires = (db.utcnow() + timedelta(minutes=policy.read()["approval_ttl_minutes"])).replace(microsecond=0)
    with db.tx() as conn:
        conn.execute("INSERT INTO approvals VALUES (?,?,?,?,?,?,?,?,?)",
                     (aid, pid, p["payload_sha256"], user["id"], decision, nonce,
                      expires.isoformat().replace("+00:00", "Z"), None, db.now()))
        conn.execute("UPDATE proposals SET status=?, updated_at=? WHERE id=?",
                     ("APPROVED" if decision == "approved" else "REJECTED", db.now(), pid))
        ledger.append(conn, user["id"], "APPROVED" if decision == "approved" else "REJECTED", p["case_id"], pid,
                      {"payload_sha256": p["payload_sha256"], "approval_id": aid, "nonce": nonce})
    return get_proposal(user, pid)


def _deny(conn, conn_user: dict, p, code: str, message: str):
    ledger.append(conn, conn_user["id"], "EXECUTION_DENIED", p["case_id"], p["id"], {"code": code})
    return conflict(code, message)


def execute(user: dict, pid: str) -> dict:
    denial = None
    oid = None
    p = None
    current_hash = None
    with db.tx() as conn:
        p = conn.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
        if not p:
            raise not_found("Proposal")
        require_case_read(user, p["case_id"])
        if user["role"] not in ("recruiter", "hiring_manager") or not is_member(user, p["case_id"]):
            raise forbidden("FORBIDDEN_ROLE", "Only members of this case can carry out its actions.")
        a = conn.execute("SELECT * FROM approvals WHERE proposal_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                         (pid,)).fetchone()
        if not a or a["decision"] != "approved":
            denial = _deny(conn, user, p, "NO_VALID_APPROVAL", "No manager approval exists for this action.")
        elif a["used_at"]:
            denial = _deny(conn, user, p, "APPROVAL_REPLAY", "This approval was already used. Each approval works once.")
        elif _parse_ts(a["expires_at"]) <= db.utcnow():
            denial = _deny(conn, user, p, "APPROVAL_EXPIRED", "The approval has expired. Ask the manager to approve again.")
        else:
            approval_event = conn.execute(
                "SELECT body_json FROM ledger WHERE type='APPROVED' AND case_id=? AND subject=? "
                "ORDER BY seq DESC LIMIT 1", (p["case_id"], pid)).fetchone()
            approval_body = db.loads(approval_event["body_json"], {}) if approval_event else {}
            nonce_matches = (approval_body.get("approval_id") == a["id"] and
                             hmac.compare_digest(a["nonce"], approval_body.get("nonce", "")))
            if not nonce_matches:
                denial = _deny(conn, user, p, "APPROVAL_NONCE_INVALID",
                               "The approval nonce could not be verified against the ledger.")
            else:
                current_hash = payload_hash(db.loads(p["payload_json"]))
                if current_hash != a["payload_sha256"] or current_hash != p["payload_sha256"]:
                    denial = _deny(conn, user, p, "APPROVAL_PAYLOAD_MISMATCH",
                                   "The action changed after the manager approved it. The approval no longer matches.")
                else:
                    try:
                        _validate_payload(db.loads(p["payload_json"]))
                    except ApiError as exc:
                        denial = _deny(conn, user, p, "INVALID_PAYLOAD", exc.message)
                    if not denial:
                        confirmed = conn.execute("SELECT email FROM contact_confirmations WHERE candidate_id=?",
                                                 (p["candidate_id"],)).fetchone()
                        if not confirmed or db.loads(p["payload_json"]).get("recipient") != confirmed["email"]:
                            denial = _deny(conn, user, p, "RECIPIENT_NOT_CONFIRMED",
                                           "The recipient is not the address a recruiter confirmed for this candidate.")
                    if not denial:
                        oid = db.new_id("OUT")
                        cur = conn.execute("UPDATE approvals SET used_at=? WHERE id=? AND used_at IS NULL", (db.now(), a["id"]))
                        if cur.rowcount != 1:
                            denial = _deny(conn, user, p, "APPROVAL_REPLAY",
                                           "This approval was already used. Each approval works once.")
                        else:
                            conn.execute("INSERT INTO outbox VALUES (?,?,?,?,?,?,?)",
                                         (oid, pid, p["case_id"], p["payload_json"], "QUEUED", "", db.now()))
                            conn.execute("UPDATE proposals SET status='EXECUTED', updated_at=? WHERE id=?", (db.now(), pid))
                            ledger.append(conn, user["id"], "EXECUTED", p["case_id"], pid,
                                          {"payload_sha256": current_hash, "approval_id": a["id"], "outbox_id": oid})
    if denial:
        raise denial
    _deliver(oid, p["payload_json"], pid, p["case_id"])
    return {"executed": True, "outbox_id": oid, "proposal": get_proposal(user, pid)}


def _deliver(oid: str, payload_json: str, pid: str, case_id: str) -> None:
    """Hand the approved action to delivery: global kill switch, recorded attempts, n8n when live."""
    delivery.deliver(oid, payload_json, pid, case_id=case_id)


def outbox(user: dict, case_id: str) -> list[dict]:
    require_case_read(user, case_id)
    return [{"id": r["id"], "proposal_id": r["proposal_id"], "payload": db.loads(r["payload_json"]),
             "delivery_status": r["delivery_status"], "delivery_detail": r["delivery_detail"], "created_at": r["created_at"]}
            for r in db.q("SELECT * FROM outbox WHERE case_id=? ORDER BY created_at", (case_id,))]
