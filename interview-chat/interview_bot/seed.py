"""Demo data: 4 staff users, 1 job, 4 fictional candidates. Runs only on an empty database."""
import json

from . import db, ledger, services
from .config import BASE_DIR, settings
from .security import hash_password

USERS = [
    ("sarra", "Sarra (Recruiter)", "recruiter"),
    ("karim", "Karim (Hiring manager)", "hiring_manager"),
    ("admin", "HR Admin", "hr_admin"),
    ("audit", "Auditor (read-only)", "auditor"),
]


def seed_demo(with_candidates: bool = True) -> bool:
    if db.one("SELECT 1 FROM users LIMIT 1"):
        return False
    pw = hash_password(settings.demo_password)
    with db.tx() as conn:
        for username, name, role in USERS:
            conn.execute("INSERT INTO users (username, display_name, role, pw_hash, created_at) VALUES (?,?,?,?,?)",
                         (username, name, role, pw, db.now()))
        ledger.append("system", "demo.seeded", {"users": [u[0] for u in USERS]}, conn=conn)
    recruiter = db.one("SELECT id, username, role FROM users WHERE username='sarra'")
    spec = json.loads((BASE_DIR / "data" / "jobs" / "backend_developer.json").read_text(encoding="utf-8"))
    job_id = services.create_job(spec, recruiter)

    manifest = BASE_DIR / "data" / "cvs" / "candidates.json"
    if with_candidates and manifest.exists():
        for c in json.loads(manifest.read_text(encoding="utf-8")):
            data = (manifest.parent / c["file"]).read_bytes()
            services.add_candidate(job_id, c["full_name"], c["email"], c["file"], data, recruiter)
    return True
