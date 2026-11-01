"""Demo data: users and a case with synthetic job criteria.
All candidates and CV fixtures are fictional test data."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from . import cases, config, db, ledger, scheduling, schemas
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

DEMO_CVS = [
    ("demo_en_software_support.pdf", "English software support"),
    ("demo_en_quality_assistant.pdf", "English quality assurance"),
    ("demo_en_data_operations.pdf", "English data operations"),
    ("demo_fr_quality_analyst.pdf", "French quality analyst"),
    ("demo_ar_it_support.pdf", "Arabic IT support"),
    ("demo_mixed_product_qa.pdf", "Multilingual product QA"),
    ("demo_en_cloud_intern.pdf", "English operations intern"),
    ("metadata_injection.pdf", "Attack CV · metadata"),
    ("fr_injection.pdf", "Attack CV · French"),
    ("ar_injection.pdf", "Attack CV · Arabic"),
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


def seed_demo() -> str:
    """Reset and load synthetic CVs, a sample shortlist, interviews, and reminders."""
    message = seed()
    recruiter = dict(db.one("SELECT * FROM users WHERE id='U-REC'"))
    fixture_dir = config.REPO / "sentinel_hr" / "fixtures"
    candidates = []
    for filename, _label in DEMO_CVS:
        dossier = cases.upload_cv(recruiter, "CASE-DEMO", filename, (fixture_dir / filename).read_bytes())
        candidates.append(dossier["candidate_id"])
    ranking = cases.draft_ranking(recruiter, "CASE-DEMO")
    # This shortlist is preloaded fictional demo state, not a model decision.
    selected = [candidates[0], candidates[3]]
    cases.shortlist(recruiter, "CASE-DEMO", ranking["version"],
                    schemas.ShortlistSet(candidate_ids=selected))

    start = db.utcnow().replace(minute=0, second=0, microsecond=0)   # whole hours read better on the agenda
    first_interview = scheduling.create_interview(recruiter, schemas.InterviewCreate(
        case_id="CASE-DEMO", candidate_id=selected[0], interviewer_id="U-MGR",
        interview_type="technical", scheduled_start=(start + timedelta(days=2, hours=10)).isoformat().replace("+00:00", "Z"),
        duration_minutes=60, timezone="UTC", location="Vouch demo room",
        preparation_notes="Review the candidate's Python validation and regression-test examples."))
    second_interview = scheduling.create_interview(recruiter, schemas.InterviewCreate(
        case_id="CASE-DEMO", candidate_id=selected[1], interviewer_id="U-MGR",
        interview_type="screening", scheduled_start=(start + timedelta(days=3, hours=10)).isoformat().replace("+00:00", "Z"),
        duration_minutes=45, timezone="UTC", location="Vouch demo room",
        preparation_notes="Discuss the candidate's multilingual QA experience."))
    scheduling.ensure_workflow_task(
        recruiter, case_id="CASE-DEMO", dedupe_key=f"demo:interview:{first_interview['id']}:confirm",
        title="Confirm technical interview", task_type="confirm_interview",
        candidate_id=selected[0], interview_id=first_interview["id"], assigned_to="U-REC",
        due_at=(start + timedelta(days=1)).isoformat().replace("+00:00", "Z"), priority="high")
    scheduling.ensure_workflow_task(
        recruiter, case_id="CASE-DEMO", dedupe_key=f"demo:interview:{second_interview['id']}:feedback",
        title="Collect interview feedback", task_type="collect_feedback",
        candidate_id=selected[1], interview_id=second_interview["id"], assigned_to="U-MGR",
        due_at=(start + timedelta(days=4)).isoformat().replace("+00:00", "Z"), priority="normal")
    scheduling.ensure_workflow_task(
        recruiter, case_id="CASE-DEMO", dedupe_key="demo:attack-review",
        title="Review attack CV findings", task_type="review_cv",
        candidate_id=candidates[-1], assigned_to="U-REC",
        due_at=(start + timedelta(days=1, hours=2)).isoformat().replace("+00:00", "Z"), priority="urgent")
    meetings = _demo_meetings(recruiter)
    return (f"{message}; loaded {len(DEMO_CVS)} synthetic CVs (including 3 attack CVs), {meetings} internal meetings, a preloaded sample "
            "shortlist, 2 interviews, and 3 follow-up tasks.")


def _demo_meetings(recruiter: dict) -> int:
    """Two fictional internal meetings so the agenda shows interviews next to non-recruitment work."""
    from . import agenda
    from .errors import ApiError
    base = db.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    plan = [
        ("Weekly HR team sync", 1, 9, 45, "Room 3 · HR floor", ["U-MGR", "U-ADM"], "Pipeline review and hiring priorities."),
        ("Onboarding plan for new hires", 4, 14, 60, "Video call", ["U-ADM"], "Prepare first-week schedule and accounts."),
    ]
    made = 0
    for title, day, hour, minutes, where, people, notes in plan:
        start = (base + timedelta(days=day, hours=hour)).isoformat().replace("+00:00", "Z")
        try:
            agenda.create_meeting(recruiter, schemas.MeetingCreate(
                title=title, start=start, duration_minutes=minutes, timezone="Africa/Tunis",
                location=where, description=notes, attendee_ids=people))
            made += 1
        except ApiError:
            pass        # a demo interview happens to sit there; skip rather than double-book
    return made
