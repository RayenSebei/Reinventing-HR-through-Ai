"""F3: detect candidates who have not answered a message Vouch sent.

Only the latest sent message per candidate counts. A message is "answered" when a recruiter records
it, or when the inbox (F1) receives a message from the candidate's confirmed address after it was sent.
Overdue items can get a follow-up DRAFT, which goes through the normal proposal and approval path;
nothing is ever sent from here. The list holds IDs and pseudonyms, never contact details.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import config, db, gateway, ledger, schemas, scheduling
from .errors import conflict, invalid, not_found
from .security import READ_ALL_ROLES, require_case_read, require_case_write

SENT = ("DELIVERED", "SANDBOX_ONLY")


def _when(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def _visible_cases(user: dict) -> list[str] | None:
    if user["role"] in READ_ALL_ROLES:
        return None
    return [r["case_id"] for r in db.q("SELECT case_id FROM case_members WHERE user_id=?", (user["id"],))]


def awaiting(user: dict, case_id: str | None = None) -> dict:
    if case_id:
        require_case_read(user, case_id)
    visible = _visible_cases(user)
    rows = db.q(
        "SELECT o.id AS outbox_id, o.case_id, o.created_at AS sent_at, o.delivery_status, p.kind, p.candidate_id, "
        "c.pseudonym, k.title AS case_title FROM outbox o JOIN proposals p ON p.id=o.proposal_id "
        "JOIN candidates c ON c.id=p.candidate_id JOIN cases k ON k.id=o.case_id "
        f"WHERE o.delivery_status IN ({','.join('?' for _ in SENT)}) "
        "AND o.id NOT IN (SELECT outbox_id FROM outbox_replies) "
        "AND NOT EXISTS (SELECT 1 FROM outbox o2 JOIN proposals p2 ON p2.id=o2.proposal_id "
        "  WHERE p2.candidate_id=p.candidate_id AND o2.delivery_status IN ('DELIVERED','SANDBOX_ONLY') "
        "  AND (o2.created_at > o.created_at OR (o2.created_at = o.created_at AND o2.rowid > o.rowid))) "
        "ORDER BY o.created_at", SENT)
    now = db.utcnow()
    items = []
    for r in rows:
        if case_id and r["case_id"] != case_id:
            continue
        if visible is not None and r["case_id"] not in visible:
            continue
        sent = _when(r["sent_at"])
        days = max(0, (now - sent).days)
        due = sent + timedelta(days=config.REPLY_WAIT_DAYS)
        draft = db.one("SELECT id FROM proposals WHERE id=(SELECT proposal_id FROM follow_up_tasks WHERE dedupe_key=?)",
                       (f"awaiting:{r['outbox_id']}",))
        items.append({"outbox_id": r["outbox_id"], "case_id": r["case_id"], "case_title": r["case_title"],
                      "candidate_id": r["candidate_id"], "pseudonym": r["pseudonym"], "kind": r["kind"],
                      "sent_at": r["sent_at"], "delivery_status": r["delivery_status"], "days_waiting": days,
                      "due_at": due.strftime("%Y-%m-%dT%H:%M:%SZ"), "overdue": now >= due,
                      "follow_up_proposal_id": draft["id"] if draft else None})
    items.sort(key=lambda i: (not i["overdue"], i["sent_at"]))
    return {"wait_days": config.REPLY_WAIT_DAYS, "items": items, "total": len(items),
            "overdue": sum(1 for i in items if i["overdue"]),
            "statement": "Vouch does not read a real mailbox. A reply counts when a recruiter records it or when "
                         "the AI Inbox receives a message from the candidate's confirmed address."}


def _sent_row(oid: str):
    r = db.one("SELECT o.*, p.candidate_id, p.kind FROM outbox o JOIN proposals p ON p.id=o.proposal_id WHERE o.id=?", (oid,))
    if not r:
        raise not_found("Outbox item")
    return r


def record_reply(user: dict, oid: str, *, source: str = "manual", message_id: str | None = None, conn=None) -> dict:
    r = _sent_row(oid) if conn is None else conn.execute(
        "SELECT o.*, p.candidate_id FROM outbox o JOIN proposals p ON p.id=o.proposal_id WHERE o.id=?", (oid,)).fetchone()
    if conn is None:
        require_case_write(user, r["case_id"], roles=("recruiter",))

    def _write(c):
        if c.execute("SELECT 1 FROM outbox_replies WHERE outbox_id=?", (oid,)).fetchone():
            raise conflict("ALREADY_RECORDED", "A reply is already recorded for this message.")
        c.execute("INSERT INTO outbox_replies VALUES (?,?,?,?,?)", (oid, db.now(), user["id"], source, message_id))
        ledger.append(c, user["id"], "REPLY_RECORDED", r["case_id"], oid,
                      {"candidate_id": r["candidate_id"], "source": source, "message_id": message_id})

    if conn is None:
        with db.tx() as c:
            _write(c)
    else:
        _write(conn)
    return {"outbox_id": oid, "replied": True, "source": source}


def draft_follow_up(user: dict, oid: str) -> tuple[dict, bool]:
    r = _sent_row(oid)
    require_case_write(user, r["case_id"], roles=("recruiter",))
    if r["delivery_status"] not in SENT:
        raise conflict("NOT_SENT", "Only a message that was sent can be followed up.")
    if db.one("SELECT 1 FROM outbox_replies WHERE outbox_id=?", (oid,)):
        raise conflict("ALREADY_REPLIED", "The candidate already replied to this message.")
    key = f"awaiting:{oid}"
    task = db.one("SELECT proposal_id FROM follow_up_tasks WHERE dedupe_key=?", (key,))
    if task and task["proposal_id"]:
        return gateway.get_proposal(user, task["proposal_id"]), False
    proposal = gateway.create_proposal(user, r["case_id"], schemas.ProposalCreate(candidate_id=r["candidate_id"], kind="follow_up"))
    scheduling.ensure_workflow_task(
        user, case_id=r["case_id"], dedupe_key=key, title="Follow up: no reply yet", task_type="follow_up",
        candidate_id=r["candidate_id"], proposal_id=proposal["id"], assigned_to=user["id"],
        due_at=db.now(), priority="high")
    return proposal, True


def match_inbound(conn, user: dict, candidate_id: str, received_at: str, message_id: str) -> str | None:
    """Called by the inbox: a message from the candidate after the latest send counts as a reply."""
    r = conn.execute(
        "SELECT o.id, o.created_at FROM outbox o JOIN proposals p ON p.id=o.proposal_id WHERE p.candidate_id=? "
        "AND o.delivery_status IN ('DELIVERED','SANDBOX_ONLY') ORDER BY o.created_at DESC, o.rowid DESC LIMIT 1",
        (candidate_id,)).fetchone()
    if not r or _when(received_at) < _when(r["created_at"]):
        return None
    if conn.execute("SELECT 1 FROM outbox_replies WHERE outbox_id=?", (r["id"],)).fetchone():
        return None
    record_reply(user, r["id"], source="inbox", message_id=message_id, conn=conn)
    return r["id"]


def check_query(params) -> str | None:
    extra = set(params) - {"case_id"}
    if extra:
        raise invalid(f"Unknown query parameter(s): {', '.join(sorted(extra))}.")
    return params.get("case_id") or None
