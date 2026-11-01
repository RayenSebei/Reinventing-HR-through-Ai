"""SQLite storage. One connection per call, WAL mode, foreign keys on.

Swap for Postgres later by keeping the same function names.
"""
import json
import sqlite3
import time
from contextlib import contextmanager

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('recruiter','hiring_manager','hr_admin','auditor')),
    pw_hash TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    spec_json TEXT NOT NULL,          -- requirements + question bank (see data/jobs/*.json)
    created_by INTEGER REFERENCES users(id),
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS candidates (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES jobs(id),
    alias TEXT NOT NULL,              -- what the AI and the evaluator see, never the name
    full_name TEXT NOT NULL,          -- shown to HR only
    contact_email TEXT NOT NULL,      -- used only by the outbox, never sent to the LLM
    cv_filename TEXT,
    cv_sha256 TEXT,
    cv_text_minimised TEXT,           -- hidden content removed + PII masked: the only CV text the LLM sees
    cv_findings_json TEXT,            -- hidden-content report
    cv_evidence_json TEXT,            -- requirement -> verified CV quotes
    status TEXT NOT NULL DEFAULT 'new',
    created_by INTEGER REFERENCES users(id),
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,               -- interview_invite | schedule_slots
    candidate_id INTEGER NOT NULL REFERENCES candidates(id),
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    proposed_by INTEGER NOT NULL REFERENCES users(id),
    proposed_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | approved | rejected | executed
    decided_by INTEGER REFERENCES users(id),
    decided_at REAL,
    decision_note TEXT
);

CREATE TABLE IF NOT EXISTS interview_sessions (
    id INTEGER PRIMARY KEY,
    candidate_id INTEGER NOT NULL REFERENCES candidates(id),
    proposal_id INTEGER REFERENCES proposals(id),
    token_hash TEXT UNIQUE NOT NULL,  -- we store only the hash of the link token
    expires_at REAL NOT NULL,
    language TEXT,
    consent_at REAL,
    state TEXT NOT NULL DEFAULT 'invited',   -- invited | in_progress | completed | expired | revoked
    plan_json TEXT,
    q_index INTEGER NOT NULL DEFAULT 0,
    followups_used INTEGER NOT NULL DEFAULT 0,
    started_at REAL,
    ended_at REAL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES interview_sessions(id),
    sender TEXT NOT NULL CHECK (sender IN ('bot','candidate')),
    question_id TEXT,
    text TEXT NOT NULL,
    flags_json TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY,
    candidate_id INTEGER NOT NULL REFERENCES candidates(id),
    session_id INTEGER REFERENCES interview_sessions(id),
    report_json TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS report_views (
    user_id INTEGER NOT NULL REFERENCES users(id),
    candidate_id INTEGER NOT NULL REFERENCES candidates(id),
    viewed_at REAL NOT NULL,
    PRIMARY KEY (user_id, candidate_id)
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY,
    candidate_id INTEGER NOT NULL REFERENCES candidates(id),
    decision TEXT NOT NULL CHECK (decision IN ('advance','hold','reject')),
    reason TEXT NOT NULL,
    decided_by INTEGER NOT NULL REFERENCES users(id),
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY,
    proposal_id INTEGER REFERENCES proposals(id),
    to_addr TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ledger (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    data_json TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_cache (
    key TEXT PRIMARY KEY,
    output TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def tx():
    """Transaction: commits on success, rolls back on error."""
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()


def one(sql: str, params=()):
    conn = connect()
    try:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def many(sql: str, params=()):
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def now() -> float:
    return time.time()


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def loads(text):
    return json.loads(text) if text else None
