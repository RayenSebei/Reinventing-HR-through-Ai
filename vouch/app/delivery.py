"""Outbound delivery after the gateway has executed an approved action (HL-07, RB-07).

- The global switch config.OUTBOUND_MODE decides, at send time, what may leave:
  disabled -> nothing leaves, the row is HELD_OUTBOUND_DISABLED (a human can retry later);
  sink     -> recorded only, SANDBOX_ONLY (default);
  live     -> POST to the n8n webhook, signed with HMAC-SHA256 over payload_json.
- A retry is triggered by a human, re-sends the SAME stored payload (no new approval, no new
  content), and is refused once the row is DELIVERED. The outbox payload cannot be changed
  (database trigger), and its hash must still equal the approved hash.
- Idempotency key sent to n8n = outbox_id. Vouch never re-sends a DELIVERED row. Residual risk:
  if n8n sent the email but its answer was lost, a human retry could send it twice; see
  docs/plan/RESIDUAL_RISK.md.
"""
from __future__ import annotations

import hashlib
import hmac

import requests

from . import config, db, ledger
from .canonical import payload_hash
from .errors import conflict, not_found
from .security import is_member, require_case_read

RETRYABLE = ("DELIVERY_FAILED", "HELD_OUTBOUND_DISABLED")


def _attempts(oid: str) -> int:
    return db.one("SELECT COUNT(*) AS n FROM delivery_attempts WHERE outbox_id=?", (oid,))["n"]


def deliver(oid: str, payload_json: str, pid: str, actor: str = "gateway", case_id: str | None = None) -> str:
    mode = config.OUTBOUND_MODE
    detail = ""
    if mode == "disabled":
        status = "HELD_OUTBOUND_DISABLED"
    elif mode != "live" or not config.N8N_WEBHOOK_URL:
        status = "SANDBOX_ONLY"
    else:
        sig = hmac.new(config.N8N_HMAC_SECRET.encode(), payload_json.encode("utf-8"), hashlib.sha256).hexdigest()
        try:
            r = requests.post(config.N8N_WEBHOOK_URL,
                              json={"outbox_id": oid, "proposal_id": pid, "payload_json": payload_json},
                              headers={"X-Vouch-Signature": sig, "Idempotency-Key": oid}, timeout=10)
            status, detail = ("DELIVERED", "") if r.ok else ("DELIVERY_FAILED", f"n8n answered {r.status_code}")
        except requests.RequestException as e:
            status, detail = "DELIVERY_FAILED", type(e).__name__
    with db.tx() as conn:
        n = conn.execute("SELECT COUNT(*) FROM delivery_attempts WHERE outbox_id=?", (oid,)).fetchone()[0]
        conn.execute("INSERT INTO delivery_attempts (outbox_id, attempt, mode, status, detail, actor, ts) VALUES (?,?,?,?,?,?,?)",
                     (oid, n + 1, mode, status, detail, actor, db.now()))
        conn.execute("UPDATE outbox SET delivery_status=?, delivery_detail=? WHERE id=?", (status, detail, oid))
        ledger.append(conn, actor, "DELIVERY_" + status, case_id, oid, {"detail": detail, "attempt": n + 1, "mode": mode})
    return status


def retry(user: dict, oid: str) -> dict:
    row = db.one("SELECT * FROM outbox WHERE id=?", (oid,))
    if not row:
        raise not_found("Outbox item")
    require_case_read(user, row["case_id"])
    if user["role"] not in ("recruiter", "hiring_manager") or not is_member(user, row["case_id"]):
        from .errors import forbidden
        raise forbidden("FORBIDDEN_ROLE", "Only members of this case can retry its deliveries.")
    if row["delivery_status"] in ("DELIVERED", "SANDBOX_ONLY"):
        raise conflict("ALREADY_DELIVERED", "This item was already delivered or recorded. It is never sent twice.")
    if row["delivery_status"] not in RETRYABLE:
        raise conflict("NOT_RETRYABLE", "Only failed or held deliveries can be retried.")
    if _attempts(oid) >= config.MAX_DELIVERY_ATTEMPTS:
        raise conflict("RETRY_LIMIT", "Too many attempts. Check the delivery service, then create a new proposal.")
    appr = db.one("SELECT a.payload_sha256 FROM approvals a WHERE a.proposal_id=? AND a.used_at IS NOT NULL "
                  "ORDER BY a.used_at DESC LIMIT 1", (row["proposal_id"],))
    if not appr or payload_hash(db.loads(row["payload_json"])) != appr["payload_sha256"]:
        raise conflict("APPROVAL_PAYLOAD_MISMATCH", "The stored action no longer matches what the manager approved.")
    status = deliver(oid, row["payload_json"], row["proposal_id"], actor=user["id"], case_id=row["case_id"])
    return {"outbox_id": oid, "delivery_status": status, "attempts": _attempts(oid)}
