"""Approval gateway: nothing is sent to a candidate without a recorded human approval.

- An action is first stored as a PROPOSAL with a hash of its exact payload.
- Approval is a database row created by an authenticated staff user through
  the API. Text inside a CV, an email or a chat message can never approve anything.
- The approver must send the payload hash they reviewed. If the payload changed
  after they looked at it, approval is refused.
- Interview invitations need four eyes: the approver must be a different person
  from the proposer, with an approving role.
- Approved proposals execute once (status 'executed'); they cannot be edited or replayed.
"""
from . import db, engine, evaluator, ledger, scheduling
from .config import settings
from .security import new_link_token, sha256

POLICY = {
    "interview_invite": {"propose": {"recruiter", "hr_admin"}, "approve": {"hiring_manager", "hr_admin"}, "four_eyes": True},
    "schedule_slots": {"propose": {"recruiter", "hiring_manager", "hr_admin"},
                       "approve": {"recruiter", "hiring_manager", "hr_admin"}, "four_eyes": False},
}


class GatewayError(Exception):
    def __init__(self, status: int, message: str, log: tuple | None = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.log = log          # (action, data) recorded in the ledger after the rollback


def payload_hash(kind: str, candidate_id: int, payload: dict) -> str:
    return sha256(f"{kind}|{candidate_id}|{db.dumps(payload)}")


def _validate_payload(kind: str, payload: dict) -> None:
    if not isinstance(payload, dict):
        raise GatewayError(400, "Payload must be an object")
    required = {"interview_invite": {"to", "subject", "body"}, "schedule_slots": {"to", "subject", "body", "slots"}}[kind]
    missing = required - payload.keys()
    if missing:
        raise GatewayError(400, f"Missing fields: {', '.join(sorted(missing))}")
    if len(str(payload.get("body", ""))) > 5000 or len(str(payload.get("subject", ""))) > 200:
        raise GatewayError(400, "Message too long")
    if kind == "interview_invite" and "{interview_link}" not in payload["body"]:
        raise GatewayError(400, "Body must contain {interview_link}")


def draft_invite(candidate: dict, job: dict) -> dict:
    title = job["title"]
    body = (
        f"Hello,\n\nThank you for applying for the role \"{title}\". As a first step, we invite you to a short "
        f"written interview (about 15 minutes) with our AI interview assistant. You can answer in English, French "
        f"or Arabic. A recruiter reads every answer; the assistant makes no decision.\n\n"
        f"Your personal link (valid {settings.invite_ttl_hours} hours, do not share it):\n{{interview_link}}\n\n"
        f"Bonjour,\n\nMerci pour votre candidature au poste « {title} ». Nous vous invitons à un court entretien écrit "
        f"(environ 15 minutes) avec notre assistant d'entretien IA. Un recruteur lit chaque réponse ; l'assistant ne "
        f"prend aucune décision. Lien personnel ci-dessus.\n\nThe recruitment team"
    )
    return {"to": candidate["contact_email"], "subject": f"Interview invitation: {title}", "body": body,
            "expires_hours": settings.invite_ttl_hours}


def draft_slots(candidate: dict, job: dict) -> dict:
    slots = scheduling.propose_slots()
    lines = "\n".join(f"- {s['start'][:16].replace('T', ' ')} to {s['end'][11:16]} (Tunis time)" for s in slots)
    body = (f"Hello,\n\nThank you for completing the first interview for \"{job['title']}\". We would like to meet you. "
            f"Please reply with the slot that suits you:\n{lines}\n\nThe recruitment team")
    return {"to": candidate["contact_email"], "subject": f"Next step: interview for {job['title']}", "body": body,
            "slots": slots}


def propose(kind: str, candidate_id: int, payload: dict, user: dict, conn=None) -> dict:
    if kind not in POLICY:
        raise GatewayError(400, "Unknown action")
    if user["role"] not in POLICY[kind]["propose"]:
        raise GatewayError(403, "Your role cannot propose this action")
    _validate_payload(kind, payload)
    h = payload_hash(kind, candidate_id, payload)

    def write(c):
        cur = c.execute("INSERT INTO proposals (kind, candidate_id, payload_json, payload_hash, proposed_by, proposed_at) "
                        "VALUES (?,?,?,?,?,?)", (kind, candidate_id, db.dumps(payload), h, user["id"], db.now()))
        ledger.append(user["username"], "proposal.created",
                      {"proposal_id": cur.lastrowid, "kind": kind, "candidate_id": candidate_id, "payload_hash": h}, conn=c)
        return cur.lastrowid

    if conn is not None:
        pid = write(conn)
    else:
        with db.tx() as c:
            pid = write(c)
    return {"id": pid, "payload_hash": h, "status": "pending"}


def update(proposal_id: int, payload: dict, user: dict) -> dict:
    with db.tx() as conn:
        p = conn.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        if p is None:
            raise GatewayError(404, "Proposal not found")
        if p["status"] != "pending":
            raise GatewayError(409, f"Proposal is {p['status']}; it can no longer be edited")
        if p["proposed_by"] != user["id"]:
            raise GatewayError(403, "Only the proposer can edit a pending proposal")
        _validate_payload(p["kind"], payload)
        h = payload_hash(p["kind"], p["candidate_id"], payload)
        conn.execute("UPDATE proposals SET payload_json=?, payload_hash=? WHERE id=?", (db.dumps(payload), h, proposal_id))
        ledger.append(user["username"], "proposal.edited",
                      {"proposal_id": proposal_id, "candidate_id": p["candidate_id"], "old_hash": p["payload_hash"],
                       "new_hash": h}, conn=conn)
    return {"id": proposal_id, "payload_hash": h, "status": "pending"}


def reject(proposal_id: int, user: dict, note: str) -> None:
    with db.tx() as conn:
        p = conn.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        if p is None:
            raise GatewayError(404, "Proposal not found")
        if p["status"] != "pending":
            raise GatewayError(409, f"Proposal is {p['status']}")
        if user["role"] not in POLICY[p["kind"]]["approve"] and user["id"] != p["proposed_by"]:
            raise GatewayError(403, "Your role cannot reject this action")
        conn.execute("UPDATE proposals SET status='rejected', decided_by=?, decided_at=?, decision_note=? WHERE id=?",
                     (user["id"], db.now(), (note or "")[:500], proposal_id))
        ledger.append(user["username"], "proposal.rejected",
                      {"proposal_id": proposal_id, "candidate_id": p["candidate_id"]}, conn=conn)


def approve(proposal_id: int, user: dict, reviewed_hash: str) -> dict:
    """Approve and execute. Returns what was executed (outbox id, etc.)."""
    try:
        return _approve(proposal_id, user, reviewed_hash)
    except GatewayError as err:
        if err.log:
            ledger.append(user["username"], err.log[0], err.log[1])
        raise


def _approve(proposal_id: int, user: dict, reviewed_hash: str) -> dict:
    with db.tx() as conn:
        p = conn.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        if p is None:
            raise GatewayError(404, "Proposal not found")
        p = dict(p)
        rule = POLICY[p["kind"]]
        if p["status"] != "pending":
            raise GatewayError(409, f"Proposal is already {p['status']}",
                               log=("proposal.replay_blocked", {"proposal_id": proposal_id,
                                    "candidate_id": p["candidate_id"], "status": p["status"]}))
        if user["role"] not in rule["approve"]:
            raise GatewayError(403, "Your role cannot approve this action")
        if rule["four_eyes"] and user["id"] == p["proposed_by"]:
            raise GatewayError(403, "Four-eyes rule: you cannot approve your own proposal",
                               log=("proposal.self_approval_blocked",
                                    {"proposal_id": proposal_id, "candidate_id": p["candidate_id"]}))
        payload = db.loads(p["payload_json"])
        actual = payload_hash(p["kind"], p["candidate_id"], payload)
        if actual != p["payload_hash"]:
            raise GatewayError(409, "Stored payload does not match its hash (tampering detected)",
                               log=("proposal.integrity_failure",
                                    {"proposal_id": proposal_id, "candidate_id": p["candidate_id"]}))
        if reviewed_hash != p["payload_hash"]:
            raise GatewayError(409, "The payload changed since you reviewed it. Reload and review again.",
                               log=("proposal.stale_approval_blocked",
                                    {"proposal_id": proposal_id, "candidate_id": p["candidate_id"]}))

        conn.execute("UPDATE proposals SET status='approved', decided_by=?, decided_at=? WHERE id=?",
                     (user["id"], db.now(), proposal_id))
        ledger.append(user["username"], "proposal.approved",
                      {"proposal_id": proposal_id, "candidate_id": p["candidate_id"], "payload_hash": actual}, conn=conn)
        result = _execute(conn, p, payload, user)
        conn.execute("UPDATE proposals SET status='executed' WHERE id=?", (proposal_id,))
    return result


def _execute(conn, p: dict, payload: dict, user: dict) -> dict:
    cand = dict(conn.execute("SELECT * FROM candidates WHERE id=?", (p["candidate_id"],)).fetchone())
    if p["kind"] == "interview_invite":
        job = dict(conn.execute("SELECT * FROM jobs WHERE id=?", (cand["job_id"],)).fetchone())
        spec = db.loads(job["spec_json"])
        cv_ev = db.loads(cand["cv_evidence_json"]) or {"quotes": {}}
        plan = engine.build_plan(spec, evaluator.gaps(spec, cv_ev))
        # One active interview per candidate: revoke earlier unused links.
        conn.execute("UPDATE interview_sessions SET state='revoked' WHERE candidate_id=? AND state='invited'", (cand["id"],))
        token, token_hash = new_link_token()
        ttl_h = min(int(payload.get("expires_hours", settings.invite_ttl_hours)), settings.invite_ttl_hours)
        cur = conn.execute(
            "INSERT INTO interview_sessions (candidate_id, proposal_id, token_hash, expires_at, plan_json) VALUES (?,?,?,?,?)",
            (cand["id"], p["id"], token_hash, db.now() + ttl_h * 3600, db.dumps(plan)))
        link = f"{settings.public_base_url.rstrip('/')}/interview#t={token}"   # fragment: never sent to servers or logs
        body = payload["body"].replace("{interview_link}", link)
        out = conn.execute("INSERT INTO outbox (proposal_id, to_addr, subject, body, created_at) VALUES (?,?,?,?,?)",
                           (p["id"], payload["to"], payload["subject"], body, db.now()))
        conn.execute("UPDATE candidates SET status='invited' WHERE id=?", (cand["id"],))
        ledger.append("system", "invite.sent", {"proposal_id": p["id"], "candidate_id": cand["id"],
                      "session_id": cur.lastrowid, "outbox_id": out.lastrowid, "expires_hours": ttl_h}, conn=conn)
        return {"executed": "interview_invite", "outbox_id": out.lastrowid, "session_id": cur.lastrowid}

    if p["kind"] == "schedule_slots":
        out = conn.execute("INSERT INTO outbox (proposal_id, to_addr, subject, body, created_at) VALUES (?,?,?,?,?)",
                           (p["id"], payload["to"], payload["subject"], payload["body"], db.now()))
        conn.execute("UPDATE candidates SET status='scheduling' WHERE id=?", (cand["id"],))
        ledger.append("system", "slots.sent", {"proposal_id": p["id"], "candidate_id": cand["id"],
                      "outbox_id": out.lastrowid, "slots": len(payload.get("slots", []))}, conn=conn)
        return {"executed": "schedule_slots", "outbox_id": out.lastrowid}
    raise GatewayError(400, "Unknown action")
