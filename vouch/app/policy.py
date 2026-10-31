"""Persisted runtime policy managed by HR administrators."""
from __future__ import annotations

from . import config, db


def defaults() -> dict:
    return {"approval_ttl_minutes": config.APPROVAL_MINUTES, "review_weight_threshold": 30}


def read() -> dict:
    values = defaults()
    for row in db.q("SELECT key, value_json FROM app_policy"):
        values[row["key"]] = db.loads(row["value_json"])
    return values


def update(values: dict, actor: str) -> dict:
    with db.tx() as conn:
        for key, value in values.items():
            conn.execute(
                "INSERT INTO app_policy(key,value_json,updated_by,updated_at) VALUES(?,?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, "
                "updated_by=excluded.updated_by, updated_at=excluded.updated_at",
                (key, db.dumps(value), actor, db.now()),
            )
        from . import ledger
        ledger.append(conn, actor, "POLICY_UPDATED", None, None, {"fields": sorted(values)})
    return read()
