"""Retention purge job for candidate records and their original CV files."""
from __future__ import annotations

import json
from datetime import timedelta

from . import cases, config, db


def purge_expired() -> dict:
    cutoff = (db.utcnow() - timedelta(days=config.RETENTION_DAYS)).replace(microsecond=0)
    cutoff_text = cutoff.isoformat().replace("+00:00", "Z")
    candidate_ids = [row["id"] for row in db.q(
        "SELECT id FROM candidates WHERE created_at < ? ORDER BY created_at", (cutoff_text,))]
    for candidate_id in candidate_ids:
        cases._erase_candidate(candidate_id, "system:retention", "retention_expired")
    return {"deleted": len(candidate_ids), "retention_days": config.RETENTION_DAYS, "cutoff": cutoff_text}


if __name__ == "__main__":
    print(json.dumps(purge_expired(), sort_keys=True))
