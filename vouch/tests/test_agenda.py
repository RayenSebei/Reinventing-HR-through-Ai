"""Agenda: internal meetings, one calendar feed, interview-format recommendation (human decides),
and who conducted the interview (AI chat -> a person, never back)."""
from datetime import timedelta

from app import db
from app.main import app
from app.security import issue_token
from app.seed import seed
from starlette.testclient import TestClient


def _auth(user_id="U-REC"):
    return {"Authorization": "Bearer " + issue_token(user_id)}


def _at(days=2, hours=10, minutes=0):
    base = db.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return (base + timedelta(days=days, hours=hours, minutes=minutes)).isoformat().replace("+00:00", "Z")


def _day(days=0):
    return (db.utcnow() + timedelta(days=days)).date().isoformat()


def _candidate(candidate_id, score=70, flags=(), missing=()):
    db.q("INSERT INTO candidates VALUES(?,?,?,?,?,?)",
         (candidate_id, "CASE-DEMO", candidate_id, "Private Candidate", "private@example.invalid", db.now()))
    row = {"candidate_id": candidate_id, "pseudonym": candidate_id, "score": score, "position": 1,
           "flags": list(flags), "missing": list(missing),
           "breakdown": [{"criterion": "Python", "weight": 40, "status": "SOURCED"},
                         {"criterion": "Tests", "weight": 35, "status": "SOURCED" if not missing else "NOT_FOUND"},
                         {"criterion": "Git", "weight": 25, "status": "SOURCED"}]}
    prev = db.one("SELECT version, payload_json FROM rankings WHERE case_id='CASE-DEMO' AND status='CONFIRMED' "
                  "ORDER BY version DESC LIMIT 1")
    rows = (db.loads(prev["payload_json"]) if prev else []) + [row]
    version = (db.one("SELECT MAX(version) v FROM rankings WHERE case_id='CASE-DEMO'")["v"] or 0) + 1
    db.q("UPDATE rankings SET status='SUPERSEDED' WHERE case_id='CASE-DEMO' AND status='CONFIRMED'")
    db.q("INSERT INTO rankings VALUES(?,?,?,?,?,?,?,?,?)",
         (f"R-{candidate_id}", "CASE-DEMO", version, "CONFIRMED", db.dumps(rows), "U-REC", "U-REC", db.now(), db.now()))
    for r in rows:
        db.q("INSERT INTO shortlisted_candidates VALUES(?,?,?)", ("CASE-DEMO", version, r["candidate_id"]))


def _interview(client, candidate_id, start=None, interviewer="U-MGR", minutes=60):
    r = client.post("/api/interviews", headers=_auth(), json={
        "case_id": "CASE-DEMO", "candidate_id": candidate_id, "interviewer_id": interviewer,
        "interview_type": "technical", "scheduled_start": start or _at(), "duration_minutes": minutes,
        "timezone": "Africa/Tunis", "location": "Room 2", "preparation_notes": ""})
    assert r.status_code == 201, r.text
    return r.json()


def _meeting(client, who="U-REC", **kw):
    body = {"title": "Weekly HR sync", "start": _at(days=2, hours=14), "duration_minutes": 30,
            "timezone": "Africa/Tunis", "location": "Room 1", "description": "Pipeline review",
            "attendee_ids": ["U-MGR"], **kw}
    return client.post("/api/meetings", headers=_auth(who), json=body)


# --- internal meetings --------------------------------------------------------------------
def test_recruiter_creates_meeting_and_it_shows_in_agenda():
    seed()
    with TestClient(app) as c:
        r = _meeting(c)
        assert r.status_code == 201, r.text
        m = r.json()
        assert m["title"] == "Weekly HR sync" and sorted(m["attendee_ids"]) == ["U-MGR", "U-REC"]
        ag = c.get(f"/api/agenda?from={_day(0)}&to={_day(7)}", headers=_auth()).json()
        ev = [e for e in ag["events"] if e["kind"] == "meeting"]
        assert len(ev) == 1 and ev[0]["title"] == "Weekly HR sync" and ev[0]["private"] is False


def test_non_attendee_sees_only_busy():
    seed()
    with TestClient(app) as c:
        assert _meeting(c, title="Salary review [[REDTEAM-CANARY-AG1]]", description="secret notes",
                        location="CFO office").status_code == 201
        for uid in ("U-ADM", "U-AUD"):
            ag = c.get(f"/api/agenda?from={_day(0)}&to={_day(7)}", headers=_auth(uid))
            assert ag.status_code == 200
            text = ag.text
            assert "REDTEAM-CANARY-AG1" not in text and "secret notes" not in text and "CFO office" not in text
            ev = [e for e in ag.json()["events"] if e["kind"] == "meeting"]
            assert ev and ev[0]["title"] == "Busy" and ev[0]["private"] is True


def test_meeting_validation_and_roles():
    seed()
    with TestClient(app) as c:
        assert _meeting(c, who="U-AUD").status_code == 403                       # auditors read only
        assert _meeting(c, attendee_ids=["U-NOPE"]).status_code == 422
        assert _meeting(c, start=_at(days=-1)).status_code == 422                 # past
        assert _meeting(c, duration_minutes=5).status_code == 422
        assert _meeting(c, title="").status_code == 422
        assert _meeting(c, extra="x").status_code == 422                          # unknown field


def test_meeting_and_interview_cannot_overlap_for_the_same_person():
    seed()
    _candidate("cand-a")
    with TestClient(app) as c:
        _interview(c, "cand-a", start=_at(days=2, hours=10), interviewer="U-MGR")
        r = _meeting(c, start=_at(days=2, hours=10, minutes=30), attendee_ids=["U-MGR"])
        assert r.status_code == 409 and r.json()["error"]["code"] == "MEETING_CONFLICT"
        assert _meeting(c, start=_at(days=2, hours=11), attendee_ids=["U-MGR"]).status_code == 201
        # and the other way round: an interview can't be put on top of the interviewer's meeting
        _candidate("cand-b")
        r2 = c.post("/api/interviews", headers=_auth(), json={
            "case_id": "CASE-DEMO", "candidate_id": "cand-b", "interviewer_id": "U-MGR",
            "interview_type": "screening", "scheduled_start": _at(days=2, hours=11, minutes=15),
            "duration_minutes": 30, "timezone": "UTC", "location": "", "preparation_notes": ""})
        assert r2.status_code == 409 and r2.json()["error"]["code"] == "INTERVIEW_CONFLICT"


def test_only_organizer_edits_or_cancels_and_cancelled_frees_the_slot():
    seed()
    with TestClient(app) as c:
        m = _meeting(c).json()
        assert c.patch(f"/api/meetings/{m['id']}", headers=_auth("U-MGR"), json={"title": "x"}).status_code == 403
        r = c.patch(f"/api/meetings/{m['id']}", headers=_auth(), json={"title": "HR sync (moved)",
                                                                        "start": _at(days=3, hours=9)})
        assert r.status_code == 200 and r.json()["title"] == "HR sync (moved)"
        assert c.delete(f"/api/meetings/{m['id']}", headers=_auth()).status_code == 200
        ag = c.get(f"/api/agenda?from={_day(0)}&to={_day(7)}", headers=_auth()).json()
        assert not [e for e in ag["events"] if e["kind"] == "meeting"]
        assert _meeting(c, start=_at(days=3, hours=9)).status_code == 201


def test_meetings_are_ledgered_without_their_content():
    seed()
    with TestClient(app) as c:
        _meeting(c, title="Confidential [[REDTEAM-CANARY-AG2]]")
        led = c.get("/api/ledger", headers=_auth("U-AUD"))
        assert led.status_code == 200 and "MEETING_CREATED" in led.text and "REDTEAM-CANARY-AG2" not in led.text


def test_agenda_shows_interviews_only_from_visible_cases_and_validates_range():
    seed()
    _candidate("cand-a")
    db.q("INSERT INTO users VALUES(?,?,?,?,?)", ("U-OUT", "out@vouch.demo", "Outsider", "recruiter", "x"))
    with TestClient(app) as c:
        _interview(c, "cand-a")
        mine = c.get(f"/api/agenda?from={_day(0)}&to={_day(7)}", headers=_auth()).json()
        assert [e["kind"] for e in mine["events"]] == ["interview"]
        assert mine["events"][0]["candidate_pseudonym"] == "cand-a"
        out = c.get(f"/api/agenda?from={_day(0)}&to={_day(7)}", headers=_auth("U-OUT")).json()
        assert out["events"] == []
        assert c.get("/api/agenda?from=bad&to=x", headers=_auth()).status_code == 422
        assert c.get(f"/api/agenda?from={_day(0)}&to={_day(90)}", headers=_auth()).status_code == 422   # max 62 days
        assert c.get(f"/api/agenda?from={_day(0)}&to={_day(7)}&x=1", headers=_auth()).status_code == 422


# --- interview format: AI suggests, a person decides -------------------------------------------
def test_strong_match_is_suggested_for_senior_hr():
    seed()
    _candidate("cand-strong", score=92)
    with TestClient(app) as c:
        i = _interview(c, "cand-strong")
        f = c.get(f"/api/interviews/{i['id']}/format", headers=_auth()).json()
        assert f["recommended"] == "senior_hr" and f["decided"] is None and f["reasons"]
        assert "3/3" in " ".join(f["reasons"])


def test_flagged_cv_is_suggested_for_a_recruiter_not_ai():
    seed()
    _candidate("cand-flag", score=95, flags=["DOCUMENT_FINDINGS"])
    with TestClient(app) as c:
        i = _interview(c, "cand-flag")
        assert c.get(f"/api/interviews/{i['id']}/format", headers=_auth()).json()["recommended"] == "recruiter"


def test_other_profiles_get_ai_chat_first_round_with_safeguards_stated():
    seed()
    _candidate("cand-mid", score=55, missing=["Tests"])
    with TestClient(app) as c:
        i = _interview(c, "cand-mid")
        f = c.get(f"/api/interviews/{i['id']}/format", headers=_auth()).json()
        assert f["recommended"] == "ai_chat"
        text = " ".join(f["reasons"]).lower()
        assert "person reads" in text and "ask for a human" in text


def test_recommendation_is_only_a_suggestion_until_a_recruiter_decides():
    seed()
    _candidate("cand-mid", score=55)
    with TestClient(app) as c:
        i = _interview(c, "cand-mid")
        assert c.post(f"/api/interviews/{i['id']}/format", headers=_auth("U-MGR"),
                      json={"format": "senior_hr"}).status_code == 403        # only a recruiter decides
        assert c.post(f"/api/interviews/{i['id']}/format", headers=_auth("U-AUD"),
                      json={"format": "senior_hr"}).status_code in (403, 404)
        assert c.post(f"/api/interviews/{i['id']}/format", headers=_auth(),
                      json={"format": "robot"}).status_code == 422
        r = c.post(f"/api/interviews/{i['id']}/format", headers=_auth(), json={"format": "senior_hr"})
        assert r.status_code == 200
        f = r.json()
        assert f["decided"] == "senior_hr" and f["decided_by"] == "U-REC" and f["overridden"] is True
        led = c.get("/api/ledger?case_id=CASE-DEMO", headers=_auth("U-AUD")).json()
        ev = [e for e in led if e["type"] == "INTERVIEW_FORMAT_DECIDED"]
        assert ev and ev[-1]["body"]["recommended"] == "ai_chat" and ev[-1]["body"]["decided"] == "senior_hr"


def test_agenda_carries_the_format_for_colouring():
    seed()
    _candidate("cand-strong", score=92)
    with TestClient(app) as c:
        i = _interview(c, "cand-strong")
        c.post(f"/api/interviews/{i['id']}/format", headers=_auth(), json={"format": "senior_hr"})
        ev = c.get(f"/api/agenda?from={_day(0)}&to={_day(7)}", headers=_auth()).json()["events"][0]
        assert ev["format"]["recommended"] == "senior_hr" and ev["format"]["decided"] == "senior_hr"


# --- who conducted it: AI chat -> a person, never back ---------------------------------------------
def test_interviewed_by_ai_can_become_human_but_not_back():
    seed()
    _candidate("cand-mid", score=55)
    with TestClient(app) as c:
        i = _interview(c, "cand-mid")
        url = f"/api/interviews/{i['id']}/conducted-by"
        assert c.post(url, headers=_auth(), json={"by": "ai"}).status_code == 200
        r = c.post(url, headers=_auth("U-MGR"), json={"by": "human"})       # the assigned interviewer may record it
        assert r.status_code == 200 and r.json()["conducted_by"] == "human" and r.json()["conducted_by_set_by"] == "U-MGR"
        back = c.post(url, headers=_auth(), json={"by": "ai"})
        assert back.status_code == 409 and back.json()["error"]["code"] == "ALREADY_HUMAN"
        assert c.post(url, headers=_auth("U-AUD"), json={"by": "human"}).status_code in (403, 404)
        led = c.get("/api/ledger?case_id=CASE-DEMO", headers=_auth("U-AUD")).json()
        assert [e["body"]["by"] for e in led if e["type"] == "INTERVIEW_CONDUCTED_BY"] == ["ai", "human"]


def test_format_endpoints_are_case_scoped():
    seed()
    _candidate("cand-mid", score=55)
    db.q("INSERT INTO users VALUES(?,?,?,?,?)", ("U-OUT", "out@vouch.demo", "Outsider", "recruiter", "x"))
    with TestClient(app) as c:
        i = _interview(c, "cand-mid")
        assert c.get(f"/api/interviews/{i['id']}/format", headers=_auth("U-OUT")).status_code == 404
        assert c.post(f"/api/interviews/{i['id']}/format", headers=_auth("U-OUT"), json={"format": "ai_chat"}).status_code == 404
        assert c.post(f"/api/interviews/{i['id']}/conducted-by", headers=_auth("U-OUT"), json={"by": "human"}).status_code == 404
