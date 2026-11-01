from datetime import timedelta

from app import db, scheduling
from app.main import app
from app.seed import seed, seed_demo
from app.security import issue_token
from starlette.testclient import TestClient


def _auth(user_id="U-REC"):
    return {"Authorization": "Bearer " + issue_token(user_id)}


def _candidate(candidate_id, case_id="CASE-DEMO"):
    db.q("INSERT INTO candidates VALUES(?,?,?,?,?,?)",
         (candidate_id, case_id, candidate_id, "Private Candidate", "private@example.invalid", db.now()))
    db.q("INSERT INTO rankings VALUES(?,?,?,?,?,?,?,?,?)",
         (f"R-{candidate_id}", case_id, 1, "CONFIRMED",
          db.dumps([{"candidate_id": candidate_id, "score": 70, "position": 1}]),
          "U-REC", "U-REC", db.now(), db.now()))
    db.q("INSERT INTO shortlisted_candidates VALUES(?,?,?)", (case_id, 1, candidate_id))


def _outsider():
    db.q("INSERT INTO users VALUES(?,?,?,?,?)",
         ("U-OUT", "outside@vouch.demo", "Outside user", "hiring_manager", "unused"))


def _start(days=2, hours=0):
    return (db.utcnow() + timedelta(days=days, hours=hours)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _interview_body(candidate_id, *, start=None, interviewer="U-MGR"):
    return {"case_id": "CASE-DEMO", "candidate_id": candidate_id, "interviewer_id": interviewer,
            "interview_type": "technical", "scheduled_start": start or _start(),
            "duration_minutes": 60, "timezone": "Europe/Paris", "location": "Video",
            "preparation_notes": "Review the candidate's testing discussion."}


def test_interview_creation_is_scoped_shortlist_gated_and_persistent():
    seed()
    _candidate("candidate-interview")
    _outsider()
    with TestClient(app) as client:
        response = client.post("/api/interviews", headers=_auth(), json=_interview_body("candidate-interview"))
        assert response.status_code == 201
        interview = response.json()
        assert interview["status"] == "scheduled"
        assert interview["timezone"] == "Europe/Paris"
        listed = client.get("/api/interviews?case_id=CASE-DEMO", headers=_auth())
        assert listed.status_code == 200 and listed.json()["total"] == 1
        assert client.get(f"/api/interviews/{interview['id']}", headers=_auth("U-MGR")).status_code == 200
        assert client.get(f"/api/interviews/{interview['id']}", headers=_auth("U-AUD")).status_code == 200
        assert client.get(f"/api/interviews/{interview['id']}", headers=_auth("U-OUT")).status_code == 404

        updated = client.patch(f"/api/interviews/{interview['id']}", headers=_auth("U-MGR"),
                               json={"status": "completed", "feedback": "Strong debugging approach."})
        assert updated.status_code == 200
        assert updated.json()["status"] == "completed" and updated.json()["completed_at"]
        assert client.get("/api/interviews?status=completed", headers=_auth()).json()["total"] == 1
        assert "Strong debugging approach" not in str(client.get("/api/ledger", headers=_auth()).json())
        assert client.patch(f"/api/interviews/{interview['id']}", headers=_auth("U-MGR"),
                            json={"location": "Elsewhere"}).status_code == 422


def test_interview_overlap_cancel_and_input_validation():
    seed()
    _candidate("candidate-overlap")
    db.q("INSERT INTO users VALUES(?,?,?,?,?)",
         ("U-ALT", "alternate@vouch.demo", "Alternate interviewer", "hiring_manager", "unused"))
    db.q("INSERT INTO case_members VALUES(?,?)", ("CASE-DEMO", "U-ALT"))
    start = _start()
    with TestClient(app) as client:
        first = client.post("/api/interviews", headers=_auth(),
                            json=_interview_body("candidate-overlap", start=start)).json()
        candidate_collision = client.post("/api/interviews", headers=_auth(),
                                          json=_interview_body("candidate-overlap", start=start, interviewer="U-ALT"))
        assert candidate_collision.status_code == 409
        assert candidate_collision.json()["error"]["code"] == "INTERVIEW_CONFLICT"

        _candidate("candidate-other")
        interviewer_collision = client.post("/api/interviews", headers=_auth(),
                                            json=_interview_body("candidate-other", start=start))
        assert interviewer_collision.status_code == 409

        cancelled = client.request("DELETE", f"/api/interviews/{first['id']}", headers=_auth(), json={})
        assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
        retry = client.post("/api/interviews", headers=_auth(),
                            json=_interview_body("candidate-overlap", start=start, interviewer="U-ALT"))
        assert retry.status_code == 201
        assert client.post("/api/interviews", headers=_auth(),
                           json=_interview_body("candidate-overlap", start="2020-01-01T10:00:00Z")).status_code == 422
        invalid_timezone = _interview_body("candidate-overlap")
        invalid_timezone["timezone"] = "Not/AZone"
        assert client.post("/api/interviews", headers=_auth(), json=invalid_timezone).status_code == 422
        assert client.post("/api/interviews", headers=_auth("U-MGR"),
                           json=_interview_body("candidate-overlap")).status_code == 403
        unshortlisted = {"case_id": "CASE-DEMO", "candidate_id": "missing", "interviewer_id": "U-MGR",
                         "interview_type": "screening", "scheduled_start": _start(), "duration_minutes": 45,
                         "timezone": "UTC"}
        assert client.post("/api/interviews", headers=_auth(), json=unshortlisted).status_code == 404


def test_follow_up_tasks_are_scoped_linked_filterable_and_audited():
    seed()
    _candidate("candidate-task")
    _outsider()
    with TestClient(app) as client:
        interview_response = client.post("/api/interviews", headers=_auth(),
                                         json=_interview_body("candidate-task"))
        assert interview_response.status_code == 201
        interview_id = interview_response.json()["id"]
        created = client.post("/api/follow-ups", headers=_auth(), json={
            "case_id": "CASE-DEMO", "title": "Collect interview feedback", "description": "Complete the panel form.",
            "task_type": "collect_feedback", "candidate_id": "candidate-task",
            "interview_id": interview_id, "assigned_to": "U-MGR",
            "due_at": _start(), "priority": "high"})
        assert created.status_code == 201
        task = created.json()
        assert task["status"] == "open" and task["assigned_to"] == "U-MGR"
        assert client.get("/api/follow-ups?assigned_to=U-MGR&priority=high", headers=_auth()).json()["total"] == 1
        assert client.get(f"/api/follow-ups/{task['id']}", headers=_auth("U-MGR")).status_code == 200
        assert client.get(f"/api/follow-ups/{task['id']}", headers=_auth("U-OUT")).status_code == 404

        completed = client.patch(f"/api/follow-ups/{task['id']}", headers=_auth(),
                                 json={"status": "completed"})
        assert completed.status_code == 200 and completed.json()["completed_at"]
        assert client.get("/api/follow-ups?bucket=completed", headers=_auth()).json()["total"] == 1
        ledger_events = client.get("/api/ledger?case_id=CASE-DEMO", headers=_auth()).json()
        assert any(event["type"] == "FOLLOW_UP_UPDATED" for event in ledger_events)
        assert "Complete the panel form" not in str(ledger_events)

        mismatch = client.post("/api/follow-ups", headers=_auth(), json={
            "case_id": "CASE-DEMO", "title": "Mismatched interview", "interview_id": interview_id,
            "candidate_id": "different-candidate"})
        assert mismatch.status_code == 404
        assert client.post("/api/follow-ups", headers=_auth("U-MGR"), json={
            "case_id": "CASE-DEMO", "title": "Unauthorized"}).status_code == 403


def test_workflow_follow_up_deduplication_returns_existing_task():
    seed()
    first = scheduling.ensure_workflow_task(
        {"id": "U-REC"}, case_id="CASE-DEMO", dedupe_key="proposal:123:approve",
        title="Approve communication", task_type="approve_communication")
    repeated = scheduling.ensure_workflow_task(
        {"id": "U-REC"}, case_id="CASE-DEMO", dedupe_key="proposal:123:approve",
        title="Approve communication", task_type="approve_communication")
    assert first["id"] == repeated["id"]
    assert db.one("SELECT COUNT(*) n FROM follow_up_tasks")["n"] == 1


def test_demo_seed_preloads_fictional_interviews_and_follow_ups():
    message = seed_demo()
    assert "10 synthetic CVs" in message and "3 attack CVs" in message
    assert db.one("SELECT COUNT(*) n FROM candidates WHERE case_id='CASE-DEMO'")["n"] == 10
    assert db.one("SELECT COUNT(*) n FROM interviews WHERE case_id='CASE-DEMO'")["n"] == 2
    assert db.one("SELECT COUNT(*) n FROM follow_up_tasks WHERE case_id='CASE-DEMO'")["n"] == 3
    assert db.one("SELECT COUNT(*) n FROM shortlisted_candidates WHERE case_id='CASE-DEMO'")["n"] == 2
    assert all(row["status"] == "scheduled" for row in db.q("SELECT status FROM interviews"))
