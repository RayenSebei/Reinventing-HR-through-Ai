"""Test-only helpers (VOUCH_TEST_MODE=1, localhost only). Never enable in production.

reset(): wipe the database and create the synthetic identities from
sentinel/datasets/documentation/fixture_contract.yaml (plus an auditor), so the
SENTINEL runner can drive everything else through the public API.
"""
from __future__ import annotations

from . import config, db
from .errors import ApiError, not_found
from .security import hash_password, issue_token

IDENTITIES = [
    ("R-ALPHA", "r-alpha@test.example.invalid", "Recruiter Alpha", "recruiter"),
    ("R-BETA", "r-beta@test.example.invalid", "Recruiter Beta", "recruiter"),
    ("M-ALPHA", "m-alpha@test.example.invalid", "Manager Alpha", "hiring_manager"),
    ("M-BETA", "m-beta@test.example.invalid", "Manager Beta", "hiring_manager"),
    ("A-AUDIT", "a-audit@test.example.invalid", "Auditor", "auditor"),
]


def guard(request) -> None:
    host = request.client.host if request.client else ""
    if not config.TEST_MODE or host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        raise not_found("Endpoint")


def reset() -> dict:
    db.wipe()
    db.CLOCK_OFFSET_MINUTES = 0
    with db.tx() as conn:
        for uid, email, name, role in IDENTITIES:
            conn.execute("INSERT INTO users VALUES (?,?,?,?,?)", (uid, email, name, role, hash_password("test-" + uid)))
    return {"tokens": {uid: issue_token(uid) for uid, *_ in IDENTITIES}}


def set_clock(advance_minutes: int) -> dict:
    if not -10000 < advance_minutes < 10000:
        raise ApiError(422, "SCHEMA_INVALID", "advance_minutes out of range")
    db.CLOCK_OFFSET_MINUTES = advance_minutes
    return {"offset_minutes": advance_minutes}
