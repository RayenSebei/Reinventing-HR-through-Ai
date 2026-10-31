"""Append-only, hash-chained audit log.

Each row stores the hash of the previous row. Editing or deleting any past row
breaks the chain, and verify() reports the first broken row.
"""
import hashlib

from . import db

GENESIS = "0" * 64


def _row_hash(ts: float, actor: str, action: str, data_json: str, prev_hash: str) -> str:
    material = f"{ts:.6f}|{actor}|{action}|{data_json}|{prev_hash}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def append(actor: str, action: str, data: dict, conn=None) -> str:
    """Write one entry. Pass `conn` to join an existing transaction."""
    if conn is None:
        with db.tx() as c:
            return append(actor, action, data, conn=c)
    last = conn.execute("SELECT hash FROM ledger ORDER BY id DESC LIMIT 1").fetchone()
    prev = last["hash"] if last else GENESIS
    ts = db.now()
    data_json = db.dumps(data)
    h = _row_hash(ts, actor, action, data_json, prev)
    conn.execute(
        "INSERT INTO ledger (ts, actor, action, data_json, prev_hash, hash) VALUES (?,?,?,?,?,?)",
        (ts, actor, action, data_json, prev, h),
    )
    return h


def verify() -> dict:
    rows = db.many("SELECT * FROM ledger ORDER BY id")
    prev = GENESIS
    for row in rows:
        expected = _row_hash(row["ts"], row["actor"], row["action"], row["data_json"], prev)
        if row["prev_hash"] != prev or row["hash"] != expected:
            return {"valid": False, "entries": len(rows), "first_broken_id": row["id"]}
        prev = row["hash"]
    return {"valid": True, "entries": len(rows), "head": prev}


def entries(limit: int = 200, candidate_id: int | None = None) -> list:
    rows = db.many("SELECT * FROM ledger ORDER BY id DESC LIMIT ?", (limit * 5 if candidate_id else limit,))
    out = []
    for r in rows:
        data = db.loads(r["data_json"]) or {}
        if candidate_id is not None and data.get("candidate_id") != candidate_id:
            continue
        out.append({"id": r["id"], "ts": r["ts"], "actor": r["actor"], "action": r["action"],
                    "data": data, "hash": r["hash"][:16]})
        if len(out) >= limit:
            break
    return out
