"""SQLite storage. One file, WAL mode, foreign keys on. Swap for PostgreSQL later."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('recruiter','hiring_manager','hr_admin','auditor')),
  pw_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cases (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
  owner_id TEXT NOT NULL REFERENCES users(id), status TEXT NOT NULL DEFAULT 'open',
  criteria_confirmed_by TEXT, criteria_confirmed_at TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS case_members (
  case_id TEXT NOT NULL REFERENCES cases(id), user_id TEXT NOT NULL REFERENCES users(id),
  PRIMARY KEY (case_id, user_id)
);
CREATE TABLE IF NOT EXISTS criteria (
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id), label TEXT NOT NULL,
  kind TEXT NOT NULL, weight INTEGER NOT NULL, aliases_json TEXT NOT NULL DEFAULT '[]', position INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS candidates (
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id), pseudonym TEXT NOT NULL,
  display_name TEXT NOT NULL, contact_email TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL REFERENCES candidates(id),
  case_id TEXT NOT NULL REFERENCES cases(id), sha256 TEXT NOT NULL, filename TEXT NOT NULL,
  path TEXT NOT NULL, pages INTEGER NOT NULL, uploaded_by TEXT NOT NULL,
  analysis_json TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS findings (
  id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), type TEXT NOT NULL,
  severity TEXT NOT NULL, page INTEGER, excerpt TEXT NOT NULL, boxes_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS evidence_items (
  id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL REFERENCES candidates(id),
  criterion_id TEXT NOT NULL REFERENCES criteria(id), status TEXT NOT NULL
    CHECK (status IN ('SOURCED','NEEDS_REVIEW','NOT_FOUND','VERIFIED')),
  quote TEXT, page INTEGER, source TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
  boxes_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS rankings (
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id), version INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('DRAFT','CONFIRMED','SUPERSEDED')),
  payload_json TEXT NOT NULL, created_by TEXT NOT NULL, confirmed_by TEXT, confirmed_at TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proposals (
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
  candidate_id TEXT NOT NULL REFERENCES candidates(id), kind TEXT NOT NULL,
  payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL, created_by TEXT NOT NULL,
  status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL REFERENCES proposals(id),
  payload_sha256 TEXT NOT NULL, approver_id TEXT NOT NULL, decision TEXT NOT NULL,
  nonce TEXT NOT NULL, expires_at TEXT NOT NULL, used_at TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
  id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL REFERENCES proposals(id),
  case_id TEXT NOT NULL, payload_json TEXT NOT NULL, delivery_status TEXT NOT NULL,
  delivery_detail TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, actor TEXT NOT NULL,
  type TEXT NOT NULL, case_id TEXT, subject TEXT, body_json TEXT NOT NULL,
  prev_hash TEXT NOT NULL, hash TEXT NOT NULL
);
"""

_conn: sqlite3.Connection | None = None


CLOCK_OFFSET_MINUTES = 0   # test mode only (see testmode.set_clock)


def utcnow() -> datetime:
    from datetime import timedelta
    return datetime.now(timezone.utc) + timedelta(minutes=CLOCK_OFFSET_MINUTES)


def now() -> str:
    return utcnow().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


def connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(config.DB_PATH), check_same_thread=False, isolation_level=None)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _conn.execute("PRAGMA busy_timeout=5000")   # RB-03: wait for a lock instead of failing at once
        _conn.executescript(SCHEMA)
        from . import migrations
        migrations.apply(_conn)
    return _conn


@contextmanager
def tx():
    """One serialized transaction. SQLite + a lock keeps single-use approvals atomic."""
    conn = connect()
    with _lock:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise


def q(sql: str, args: tuple = ()) -> list[sqlite3.Row]:
    with _lock:
        return connect().execute(sql, args).fetchall()


def one(sql: str, args: tuple = ()) -> sqlite3.Row | None:
    rows = q(sql, args)
    return rows[0] if rows else None


def wipe() -> None:
    """Delete everything (test mode / demo reset)."""
    conn = connect()
    with _lock:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                                                "AND name <> 'schema_migrations'")]
        conn.execute("PRAGMA foreign_keys=OFF")
        for t in tables:
            conn.execute(f"DELETE FROM {t}")
        conn.execute("DELETE FROM sqlite_sequence")
        conn.execute("PRAGMA foreign_keys=ON")


def dumps(obj) -> str:
    """Plain JSON for storage (decimals allowed). Hashed payloads use canonical.canonical."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def loads(s: str | None, default=None):
    return json.loads(s) if s else default
