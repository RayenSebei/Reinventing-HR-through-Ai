"""Demo data: 4 users (one per role) and one open case with the synthetic job's criteria.
All data is fictional. With VOUCH_DEMO=1 every demo user's password is demo1234; otherwise
(WA-02) a random password is generated once and printed, so no known password exists."""
from __future__ import annotations

import os
import secrets

from . import db, ledger
from .canonical import canonical
from .security import hash_password

USERS = [
    ("U-REC", "recruiter@vouch.demo", "Sara (Recruiter)", "recruiter"),
    ("U-MGR", "manager@vouch.demo", "Karim (Hiring manager)", "hiring_manager"),
    ("U-ADM", "admin@vouch.demo", "Lina (HR admin)", "hr_admin"),
    ("U-AUD", "auditor@vouch.demo", "Omar (Auditor)", "auditor"),
]

CRITERIA = [
    ("Python used in a software project", "skill", 40, ["scripts"]),
    ("Can explain a test strategy", "skill", 35, []),
    ("Version control (Git)", "skill", 25, []),
]


def seed() -> str:
    db.connect()
    db.wipe()
    demo = os.environ.get("VOUCH_DEMO") == "1"
    password = "demo1234" if demo else secrets.token_urlsafe(12)
    with db.tx() as conn:
        for uid, email, name, role in USERS:
            conn.execute("INSERT INTO users VALUES (?,?,?,?,?)", (uid, email, name, role, hash_password(password)))
        cid = "CASE-DEMO"
        conn.execute("INSERT INTO cases (id,title,description,owner_id,criteria_confirmed_by,criteria_confirmed_at,created_at) "
                     "VALUES (?,?,?,?,?,?,?)",
                     (cid, "Junior Software Reliability Analyst",
                      "Synthetic role. Python in a software project, explain a test strategy, version control.",
                      "U-REC", "U-REC", db.now(), db.now()))
        conn.execute("INSERT INTO case_members VALUES (?,?)", (cid, "U-REC"))
        conn.execute("INSERT INTO case_members VALUES (?,?)", (cid, "U-MGR"))
        for i, (label, kind, w, aliases) in enumerate(CRITERIA):
            conn.execute("INSERT INTO criteria VALUES (?,?,?,?,?,?,?)", (db.new_id("CRIT"), cid, label, kind, w, canonical(aliases), i))
        ledger.append(conn, "U-REC", "CASE_CREATED", cid, cid, {"manager_id": "U-MGR", "seed": True})
        ledger.append(conn, "U-REC", "CRITERIA_CONFIRMED", cid, cid, {"seed": True})
    users = ", ".join(e for _, e, _, _ in USERS)
    if demo:
        return f"Seeded demo users (VOUCH_DEMO=1, password demo1234): {users}"
    return (f"Seeded demo users: {users}\nPassword for all of them (shown once, not stored): {password}\n"
            "Set VOUCH_DEMO=1 to use the documented demo password instead.")
