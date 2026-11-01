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

import secrets
from datetime import datetime, timedelta, timezone

from . import config, contacts, db, delivery, ledger
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
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    cand = db.one("SELECT * FROM candidates WHERE id=? AND case_id=?", (body.candidate_id, case_id))
    if not cand:
        raise not_found("Candidate")
    confirmed = db.one("SELECT payload_json FROM rankings WHERE case_id=? AND status='CONFIRMED' ORDER BY version DESC LIMIT 1", (case_id,))
    if not confirmed or body.candidate_id not in {r["candidate_id"] for r in db.loads(confirmed["payload_json"])}:
        raise conflict("SHORTLIST_NOT_CONFIRMED", "Confirm the shortlist that includes this candidate first.")
    recipient = contacts.confirmed_email(cand["id"])
    if not recipient:
        raise conflict("RECIPIENT_NOT_CONFIRMED", "Confirm this candidate's email address before proposing an action.")
    start = _valid_start(body.start)
    subject, text = draft_text(body.kind, cand["pseudonym"], case["title"], start, body.duration_minutes)
    payload = {"case_id": case_id, "candidate_id": cand["id"], "kind": body.kind,
               "recipient": recipient, "start": start if body.kind == "interview_invite" else None,
               "duration_minutes": body.duration_minutes, "subject": subject, "body": text}
    pid = db.new_id("PROP")
    h = payload_hash(payload)
    ts = db.now()
    with db.tx() as conn:
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
    if "recipient" in changes:
        changes["recipient"] = contacts.clean_address(changes["recipient"])
    payload.update(changes)
    if ("start" in changes or "duration_minutes" in changes) and "body" not in changes and payload["kind"] == "interview_invite":
        case = db.one("SELECT title FROM cases WHERE id=?", (p["case_id"],))
        payload["subject"], payload["body"] = draft_text(payload["kind"], "", case["title"], payload["start"], payload["duration_minutes"])
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
    expires = (db.utcnow() + timedelta(minutes=config.APPROVAL_MINUTES)).replace(microsecond=0)
    with db.tx() as conn:
        conn.execute("INSERT INTO approvals VALUES (?,?,?,?,?,?,?,?,?)",
                     (aid, pid, p["payload_sha256"], user["id"], decision, secrets.token_hex(8),
                      expires.isoformat().replace("+00:00", "Z"), None, db.now()))
        conn.execute("UPDATE proposals SET status=?, updated_at=? WHERE id=?",
                     ("APPROVED" if decision == "approved" else "REJECTED", db.now(), pid))
        ledger.append(conn, user["id"], "APPROVED" if decision == "approved" else "REJECTED", p["case_id"], pid,
                      {"payload_sha256": p["payload_sha256"], "approval_id": aid})
    return get_proposal(user, pid)


def _deny(conn_user: dict, p, code: str, message: str):
    ledger.record(conn_user["id"], "EXECUTION_DENIED", p["case_id"], p["id"], {"code": code})
    return conflict(code, message)


def execute(user: dict, pid: str) -> dict:
    p = _proposal_row(pid)
    require_case_read(user, p["case_id"])
    if user["role"] not in ("recruiter", "hiring_manager") or not is_member(user, p["case_id"]):
        raise forbidden("FORBIDDEN_ROLE", "Only members of this case can carry out its actions.")
    a = _latest_approval(pid)
    if not a or a["decision"] != "approved":
        raise _deny(user, p, "NO_VALID_APPROVAL", "No manager approval exists for this action.")
    if a["used_at"]:
        raise _deny(user, p, "APPROVAL_REPLAY", "This approval was already used. Each approval works once.")
    if _parse_ts(a["expires_at"]) <= db.utcnow():
        raise _deny(user, p, "APPROVAL_EXPIRED", "The approval has expired. Ask the manager to approve again.")
    current_hash = payload_hash(db.loads(p["payload_json"]))
    if current_hash != a["payload_sha256"] or current_hash != p["payload_sha256"]:
        raise _deny(user, p, "APPROVAL_PAYLOAD_MISMATCH",
                    "The action changed after the manager approved it. The approval no longer matches.")
    if db.loads(p["payload_json"]).get("recipient") != contacts.confirmed_email(p["candidate_id"]):
        raise _deny(user, p, "RECIPIENT_NOT_CONFIRMED",
                    "The recipient is not the address a recruiter confirmed for this candidate.")
    oid = db.new_id("OUT")
    with db.tx() as conn:
        # Re-read inside the transaction so nothing can change between the checks and the write.
        fresh = conn.execute("SELECT payload_json, payload_sha256 FROM proposals WHERE id=?", (pid,)).fetchone()
        if fresh["payload_json"] != p["payload_json"] or fresh["payload_sha256"] != a["payload_sha256"]:
            raise conflict("APPROVAL_PAYLOAD_MISMATCH",
                           "The action changed after the manager approved it. The approval no longer matches.")
        cur = conn.execute("UPDATE approvals SET used_at=? WHERE id=? AND used_at IS NULL", (db.now(), a["id"]))
        if cur.rowcount != 1:   # someone else used it a moment ago
            raise conflict("APPROVAL_REPLAY", "This approval was already used. Each approval works once.")
        conn.execute("INSERT INTO outbox VALUES (?,?,?,?,?,?,?)",
                     (oid, pid, p["case_id"], p["payload_json"], "QUEUED", "", db.now()))
        conn.execute("UPDATE proposals SET status='EXECUTED', updated_at=? WHERE id=?", (db.now(), pid))
        ledger.append(conn, user["id"], "EXECUTED", p["case_id"], pid,
                      {"payload_sha256": current_hash, "approval_id": a["id"], "outbox_id": oid})
    _deliver(oid, p["payload_json"], pid)
    return {"executed": True, "outbox_id": oid, "proposal": get_proposal(user, pid)}


def _deliver(oid: str, payload_json: str, pid: str) -> None:
    """Hand the approved action to delivery (kill switch, attempts, n8n). The outbox row is the record."""
    delivery.deliver(oid, payload_json, pid)


def outbox(user: dict, case_id: str) -> list[dict]:
    require_case_read(user, case_id)
    return [{"id": r["id"], "proposal_id": r["proposal_id"], "payload": db.loads(r["payload_json"]),
             "delivery_status": r["delivery_status"], "delivery_detail": r["delivery_detail"], "created_at": r["created_at"]}
            for r in db.q("SELECT * FROM outbox WHERE case_id=? ORDER BY created_at", (case_id,))]
