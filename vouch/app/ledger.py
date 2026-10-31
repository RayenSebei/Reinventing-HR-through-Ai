"""Trust Ledger: append-only, hash-chained event log.

hash_i = SHA256(prev_hash || canonical(event_i)). Tampering with any row breaks
`verify()` for that row and every later row. This is tamper-evident, not
tamper-proof: someone who can rewrite the whole table could rebuild the chain.
The ledger stores IDs and hashes, never CV text or contact data.
"""
from __future__ import annotations

from . import db
from .canonical import canonical, sha256_hex

GENESIS = "0" * 64


def append(conn, actor: str, type_: str, case_id: str | None, subject: str | None, body: dict) -> str:
    row = conn.execute("SELECT hash FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
    prev = row[0] if row else GENESIS
    ts = db.now()
    event = {"ts": ts, "actor": actor, "type": type_, "case_id": case_id, "subject": subject, "body": body}
    h = sha256_hex(prev + canonical(event))
    conn.execute(
        "INSERT INTO ledger (ts, actor, type, case_id, subject, body_json, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?)",
        (ts, actor, type_, case_id, subject, canonical(body), prev, h),
    )
    return h


def record(actor: str, type_: str, case_id: str | None, subject: str | None, body: dict) -> str:
    with db.tx() as conn:
        return append(conn, actor, type_, case_id, subject, body)


def verify() -> dict:
    prev = GENESIS
    rows = db.q("SELECT * FROM ledger ORDER BY seq")
    for r in rows:
        event = {"ts": r["ts"], "actor": r["actor"], "type": r["type"], "case_id": r["case_id"],
                 "subject": r["subject"], "body": db.loads(r["body_json"], {})}
        expected = sha256_hex(prev + canonical(event))
        if r["prev_hash"] != prev or r["hash"] != expected:
            return {"ok": False, "events": len(rows), "first_bad_seq": r["seq"]}
        prev = r["hash"]
    return {"ok": True, "events": len(rows), "head": prev}
