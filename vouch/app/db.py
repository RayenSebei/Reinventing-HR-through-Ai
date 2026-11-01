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
CREATE TABLE IF NOT EXISTS shortlisted_candidates (
  case_id TEXT NOT NULL REFERENCES cases(id), ranking_version INTEGER NOT NULL,
  candidate_id TEXT NOT NULL REFERENCES candidates(id),
  PRIMARY KEY (case_id, ranking_version, candidate_id)
);
CREATE TABLE IF NOT EXISTS app_policy (
  key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_by TEXT NOT NULL, updated_at TEXT NOT NULL
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
CREATE TABLE IF NOT EXISTS interviews (
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
  candidate_id TEXT NOT NULL REFERENCES candidates(id),
  interviewer_id TEXT NOT NULL REFERENCES users(id),
  interview_type TEXT NOT NULL CHECK (interview_type IN ('screening','technical','behavioral','final','other')),
  scheduled_start TEXT NOT NULL, duration_minutes INTEGER NOT NULL CHECK (duration_minutes BETWEEN 15 AND 240),
  timezone TEXT NOT NULL, location TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled','confirmed','completed','cancelled')),
  preparation_notes TEXT NOT NULL DEFAULT '', feedback TEXT NOT NULL DEFAULT '',
  created_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  cancelled_at TEXT, completed_at TEXT
);
CREATE INDEX IF NOT EXISTS interviews_case_start ON interviews(case_id, scheduled_start);
CREATE INDEX IF NOT EXISTS interviews_interviewer_start ON interviews(interviewer_id, scheduled_start);
CREATE TABLE IF NOT EXISTS follow_up_tasks (
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
  title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
  task_type TEXT NOT NULL CHECK (task_type IN ('review_cv','review_assessment','approve_communication',
    'send_approved_communication','schedule_interview','confirm_interview','collect_feedback','follow_up','other')),
  candidate_id TEXT REFERENCES candidates(id), interview_id TEXT REFERENCES interviews(id),
  proposal_id TEXT REFERENCES proposals(id), assigned_to TEXT REFERENCES users(id),
  due_at TEXT, priority TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN ('low','normal','high','urgent')),
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','in_progress','completed')),
  origin TEXT NOT NULL DEFAULT 'manual' CHECK (origin IN ('manual','workflow','demo')),
  dedupe_key TEXT UNIQUE, created_by TEXT NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT
);
CREATE INDEX IF NOT EXISTS follow_up_case_due ON follow_up_tasks(case_id, due_at, status);
CREATE TABLE IF NOT EXISTS chat_interview_sessions (
  id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
  candidate_id TEXT NOT NULL REFERENCES candidates(id), proposal_id TEXT REFERENCES proposals(id),
  token_hash TEXT UNIQUE NOT NULL, expires_at TEXT NOT NULL,
  language TEXT, consent_at TEXT,
  time_limit_minutes INTEGER NOT NULL DEFAULT 20 CHECK (time_limit_minutes BETWEEN 1 AND 240),
  state TEXT NOT NULL DEFAULT 'pending_approval'
    CHECK (state IN ('pending_approval','invited','in_progress','completed','expired','revoked')),
  plan_json TEXT NOT NULL DEFAULT '[]', q_index INTEGER NOT NULL DEFAULT 0,
  started_at TEXT, ended_at TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chat_sessions_candidate ON chat_interview_sessions(candidate_id, created_at);
CREATE TABLE IF NOT EXISTS chat_interview_messages (
  id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES chat_interview_sessions(id),
  sender TEXT NOT NULL CHECK (sender IN ('assistant','candidate')),
  question_id TEXT, text TEXT NOT NULL, flags_json TEXT NOT NULL DEFAULT '{}',
  response_seconds INTEGER, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chat_messages_session ON chat_interview_messages(session_id, created_at);
CREATE TABLE IF NOT EXISTS chat_interview_reports (
  id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL REFERENCES candidates(id),
  session_id TEXT NOT NULL REFERENCES chat_interview_sessions(id),
  report_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_report_views (
  user_id TEXT NOT NULL REFERENCES users(id), candidate_id TEXT NOT NULL REFERENCES candidates(id),
  viewed_at TEXT NOT NULL, PRIMARY KEY (user_id, candidate_id)
);
CREATE TABLE IF NOT EXISTS candidate_decisions (
  id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL REFERENCES candidates(id),
  case_id TEXT NOT NULL REFERENCES cases(id),
  decision TEXT NOT NULL CHECK (decision IN ('advance','hold','reject')),
  reason TEXT NOT NULL, decided_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, actor TEXT NOT NULL,
  type TEXT NOT NULL, case_id TEXT, subject TEXT, body_json TEXT NOT NULL,
  prev_hash TEXT NOT NULL, hash TEXT NOT NULL, mac TEXT NOT NULL DEFAULT ''
);
CREATE TRIGGER IF NOT EXISTS ledger_no_update BEFORE UPDATE ON ledger
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS ledger_no_delete BEFORE DELETE ON ledger
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
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
        _conn.executescript(SCHEMA)
        columns = {row["name"] for row in _conn.execute("PRAGMA table_info(ledger)").fetchall()}
        if "mac" not in columns:
            _conn.execute("ALTER TABLE ledger ADD COLUMN mac TEXT NOT NULL DEFAULT ''")
        interview_columns = {row["name"] for row in _conn.execute("PRAGMA table_info(interviews)").fetchall()}
        if interview_columns and "completed_at" not in interview_columns:
            _conn.execute("ALTER TABLE interviews ADD COLUMN completed_at TEXT")
        chat_columns = {row["name"] for row in _conn.execute("PRAGMA table_info(chat_interview_sessions)").fetchall()}
        if chat_columns and "time_limit_minutes" not in chat_columns:
            _conn.execute("ALTER TABLE chat_interview_sessions ADD COLUMN time_limit_minutes INTEGER NOT NULL DEFAULT 20")
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
        conn.execute("DROP TRIGGER IF EXISTS ledger_no_update")
        conn.execute("DROP TRIGGER IF EXISTS ledger_no_delete")
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        conn.execute("PRAGMA foreign_keys=OFF")
        for t in tables:
            conn.execute(f"DELETE FROM {t}")
        conn.execute("DELETE FROM sqlite_sequence")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)


def dumps(obj) -> str:
    """Plain JSON for storage (decimals allowed). Hashed payloads use canonical.canonical."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def loads(s: str | None, default=None):
    return json.loads(s) if s else default
