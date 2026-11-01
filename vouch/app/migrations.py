"""Additive, versioned schema migrations (R21).

Rules: never edit a shipped CREATE TABLE; never ALTER a table that existing code writes with
positional `INSERT ... VALUES (?,...)` (adding a column would break those inserts). New data
goes into new tables. Every step is idempotent so a re-run on an existing database is safe.
"""
from __future__ import annotations

MIGRATIONS: list[tuple[int, str, str]] = [
    (1, "contact confirmations (HI-04/D11: a human confirms the recipient)", """
CREATE TABLE IF NOT EXISTS contact_confirmations (
  candidate_id TEXT PRIMARY KEY REFERENCES candidates(id),
  email TEXT NOT NULL, confirmed_by TEXT NOT NULL REFERENCES users(id), confirmed_at TEXT NOT NULL
);
"""),
    (2, "dossier reviews (HI-03: server-side review gate)", """
CREATE TABLE IF NOT EXISTS reviews (
  user_id TEXT NOT NULL REFERENCES users(id), candidate_id TEXT NOT NULL REFERENCES candidates(id),
  doc_sha256 TEXT NOT NULL, opened_at TEXT NOT NULL,
  PRIMARY KEY (user_id, candidate_id, doc_sha256)
);
"""),
    (3, "evidence archive (reserved: RB-05 re-evaluation was not adopted; main locks criteria after analysis)", """
CREATE TABLE IF NOT EXISTS evidence_archive (
  id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, criterion_id TEXT NOT NULL, criterion_label TEXT NOT NULL,
  status TEXT NOT NULL, quote TEXT, page INTEGER, source TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
  archived_at TEXT NOT NULL, archived_by TEXT NOT NULL
);
"""),
    (4, "delivery attempts (RB-07: retries are recorded, same approved payload)", """
CREATE TABLE IF NOT EXISTS delivery_attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, outbox_id TEXT NOT NULL REFERENCES outbox(id),
  attempt INTEGER NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
  actor TEXT NOT NULL, ts TEXT NOT NULL, UNIQUE (outbox_id, attempt)
);
"""),
    (5, "outbox backstop (HL-01/HL-02/I1/I2: the database refuses an unapproved or second send)", """
CREATE UNIQUE INDEX IF NOT EXISTS outbox_one_per_proposal ON outbox(proposal_id);
CREATE TRIGGER IF NOT EXISTS outbox_requires_used_matching_approval
BEFORE INSERT ON outbox
WHEN NOT EXISTS (
  SELECT 1 FROM approvals a JOIN proposals p ON p.id = a.proposal_id
  WHERE a.proposal_id = NEW.proposal_id
    AND a.decision = 'approved'
    AND a.used_at IS NOT NULL
    AND a.payload_sha256 = p.payload_sha256
    AND p.payload_json = NEW.payload_json
    AND p.case_id = NEW.case_id
    AND a.approver_id <> p.created_by
)
BEGIN
  SELECT RAISE(ABORT, 'OUTBOX_REQUIRES_APPROVAL');
END;
CREATE TRIGGER IF NOT EXISTS outbox_payload_immutable
BEFORE UPDATE OF payload_json, proposal_id, case_id ON outbox
BEGIN
  SELECT RAISE(ABORT, 'OUTBOX_PAYLOAD_IMMUTABLE');
END;
"""),
]

LATEST = MIGRATIONS[-1][0]


def apply(conn) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)")
    done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
    from .db import now
    for version, name, sql in MIGRATIONS:
        if version in done:
            continue
        conn.executescript("BEGIN IMMEDIATE;" + sql + "COMMIT;")
        conn.execute("INSERT OR IGNORE INTO schema_migrations VALUES (?,?,?)", (version, name, now()))
    return current(conn)


def current(conn) -> int:
    row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return row[0] or 0
