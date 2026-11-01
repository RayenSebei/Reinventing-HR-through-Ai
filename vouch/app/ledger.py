"""Trust Ledger: append-only, hash-chained event log.

hash_i = SHA256(prev_hash || canonical(event_i))
mac_i = HMAC-SHA256(VOUCH_LEDGER_KEY, mac_(i-1) || hash_i)

`verify()` checks both chains. The separately reported head lets an auditor detect
tail truncation by comparing it with a previously recorded head. This is
tamper-evident, not tamper-proof. The ledger stores IDs and hashes, never CV text
or contact data.
"""
from __future__ import annotations

import hashlib
import hmac

from . import db
from .canonical import canonical, sha256_hex

GENESIS = "0" * 64


def append(conn, actor: str, type_: str, case_id: str | None, subject: str | None, body: dict) -> str:
    row = conn.execute("SELECT hash, mac FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
    prev, prev_mac = (row["hash"], row["mac"]) if row else (GENESIS, GENESIS)
    ts = db.now()
    event = {"ts": ts, "actor": actor, "type": type_, "case_id": case_id, "subject": subject, "body": body}
    h = sha256_hex(prev + canonical(event))
    mac = hmac.new(config_key(), (prev_mac + h).encode("ascii"), hashlib.sha256).hexdigest()
    conn.execute(
        "INSERT INTO ledger (ts, actor, type, case_id, subject, body_json, prev_hash, hash, mac) VALUES (?,?,?,?,?,?,?,?,?)",
        (ts, actor, type_, case_id, subject, canonical(body), prev, h, mac),
    )
    return h


def config_key() -> bytes:
    from . import config
    return config.LEDGER_KEY.encode("utf-8")


def initialize() -> None:
    """Sign a pre-HMAC ledger once when upgrading an existing database."""
    conn = db.connect()
    rows = conn.execute("SELECT * FROM ledger ORDER BY seq").fetchall()
    if not rows or all(row["mac"] for row in rows):
        return
    if any(row["mac"] for row in rows):
        raise RuntimeError("The ledger contains an incomplete HMAC chain.")
    prev_hash, prev_mac = GENESIS, GENESIS
    with db.tx() as conn:
        conn.execute("DROP TRIGGER IF EXISTS ledger_no_update")
        conn.execute("DROP TRIGGER IF EXISTS ledger_no_delete")
        for row in rows:
            event = {"ts": row["ts"], "actor": row["actor"], "type": row["type"], "case_id": row["case_id"],
                     "subject": row["subject"], "body": db.loads(row["body_json"], {})}
            expected = sha256_hex(prev_hash + canonical(event))
            if row["prev_hash"] != prev_hash or row["hash"] != expected:
                raise RuntimeError(f"Existing ledger failed verification at sequence {row['seq']}.")
            mac = hmac.new(config_key(), (prev_mac + row["hash"]).encode("ascii"), hashlib.sha256).hexdigest()
            conn.execute("UPDATE ledger SET mac=? WHERE seq=?", (mac, row["seq"]))
            prev_hash, prev_mac = row["hash"], mac
        conn.execute("CREATE TRIGGER ledger_no_update BEFORE UPDATE ON ledger "
                     "BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END")
        conn.execute("CREATE TRIGGER ledger_no_delete BEFORE DELETE ON ledger "
                     "BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END")


def record(actor: str, type_: str, case_id: str | None, subject: str | None, body: dict) -> str:
    with db.tx() as conn:
        return append(conn, actor, type_, case_id, subject, body)


def verify() -> dict:
    prev = GENESIS
    prev_mac = GENESIS
    rows = db.q("SELECT * FROM ledger ORDER BY seq")
    for r in rows:
        event = {"ts": r["ts"], "actor": r["actor"], "type": r["type"], "case_id": r["case_id"],
                 "subject": r["subject"], "body": db.loads(r["body_json"], {})}
        expected = sha256_hex(prev + canonical(event))
        expected_mac = hmac.new(config_key(), (prev_mac + r["hash"]).encode("ascii"), hashlib.sha256).hexdigest()
        if r["prev_hash"] != prev or r["hash"] != expected or not hmac.compare_digest(r["mac"], expected_mac):
            return {"ok": False, "events": len(rows), "first_bad_seq": r["seq"]}
        prev, prev_mac = r["hash"], r["mac"]
    return {"ok": True, "events": len(rows), "head": prev, "head_mac": prev_mac}


def head() -> dict:
    verification = verify()
    row = db.one("SELECT seq, hash, mac FROM ledger ORDER BY seq DESC LIMIT 1")
    return {"ok": verification["ok"], "seq": row["seq"] if row else 0,
            "hash": row["hash"] if row else GENESIS, "mac": row["mac"] if row else GENESIS,
            "first_bad_seq": verification.get("first_bad_seq")}
