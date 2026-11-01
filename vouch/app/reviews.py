"""Server-side review gate (HI-03; fixes ground-truth G9 "top-3 gate is frontend-only").

A review row is written only when a user opens a dossier through the API route
GET /api/candidates/{id}/dossier, never when an upload or another call returns dossier data.
A review counts only for the user who made it and only for the document version (SHA-256) seen.
"""
from __future__ import annotations

from . import config, db, ledger
from .errors import conflict


def record(user: dict, cand_id: str) -> None:
    doc = db.one("SELECT case_id, sha256 FROM documents WHERE candidate_id=?", (cand_id,))
    if not doc:
        return
    with db.tx() as conn:
        cur = conn.execute("INSERT OR IGNORE INTO reviews VALUES (?,?,?,?)", (user["id"], cand_id, doc["sha256"], db.now()))
        if cur.rowcount:
            ledger.append(conn, user["id"], "DOSSIER_REVIEWED", doc["case_id"], cand_id, {"doc_sha256": doc["sha256"]})


def required(rows: list[dict]) -> list[str]:
    """Candidates the confirming user must have opened: the top N positions plus every flagged row."""
    top = sorted(rows, key=lambda r: (r.get("position", 0), r.get("pseudonym", "")))[: max(config.REVIEW_TOP_N, 1)]
    need = [r["candidate_id"] for r in top]
    need += [r["candidate_id"] for r in rows if r.get("flags") and r["candidate_id"] not in need]
    return need


def missing(user: dict, rows: list[dict]) -> list[str]:
    out = []
    for cid in required(rows):
        doc = db.one("SELECT sha256 FROM documents WHERE candidate_id=?", (cid,))
        if not doc:
            continue
        seen = db.one("SELECT 1 FROM reviews WHERE user_id=? AND candidate_id=? AND doc_sha256=?",
                      (user["id"], cid, doc["sha256"]))
        if not seen:
            out.append(cid)
    return out


def enforce(user: dict, rows: list[dict]) -> None:
    todo = missing(user, rows)
    if todo:
        pseudos = {r["candidate_id"]: r.get("pseudonym", r["candidate_id"]) for r in rows}
        raise conflict("REVIEW_REQUIRED", "Open these dossiers before confirming the shortlist: "
                       + ", ".join(pseudos.get(c, c) for c in todo) + ".")
