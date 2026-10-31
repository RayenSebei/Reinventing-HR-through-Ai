"""Demo data: 4 users (one per role) and one open case with the synthetic job's criteria.
All data is fictional. Password for every demo user: demo1234"""
from __future__ import annotations

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
    with db.tx() as conn:
        for uid, email, name, role in USERS:
            conn.execute("INSERT INTO users VALUES (?,?,?,?,?)", (uid, email, name, role, hash_password("demo1234")))
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
    return "Seeded demo users (password demo1234): " + ", ".join(e for _, e, _, _ in USERS)
