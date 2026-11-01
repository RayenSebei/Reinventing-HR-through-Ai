"""F4: free interview slots from the agenda (interviews + internal meetings), working hours only."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from helpers_assist import CASE, H, demo, shortlisted  # noqa: F401
from app import config, db


def _q(c, **kw):
    cand = kw.pop("candidate_id", None) or shortlisted(c)[0]["id"]
    params = {"candidate_id": cand, "interviewer_id": "U-MGR", "duration": 45, "timezone": "Africa/Tunis", **kw}
    return c.get(f"/api/cases/{CASE}/slots", headers=H(), params=params)


def _when(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _busy(cand_id):
    out = []
    for r in db.q("SELECT scheduled_start s, duration_minutes d FROM interviews WHERE status IN ('scheduled','confirmed') "
                  "AND (interviewer_id='U-MGR' OR candidate_id=?)", (cand_id,)):
        out.append((_when(r["s"]), _when(r["s"]) + timedelta(minutes=r["d"])))
    for r in db.q("SELECT DISTINCT m.start s, m.duration_minutes d FROM meetings m LEFT JOIN meeting_attendees a "
                  "ON a.meeting_id=m.id WHERE m.status='scheduled' AND (m.organizer_id='U-MGR' OR a.user_id='U-MGR')"):
        out.append((_when(r["s"]), _when(r["s"]) + timedelta(minutes=r["d"])))
    return out


def test_slots_are_free_future_and_inside_working_hours(demo):
    cand = shortlisted(demo)[0]["id"]
    r = _q(demo, candidate_id=cand)
    assert r.status_code == 200, r.text
    slots = r.json()["slots"]
    assert 3 <= len(slots) <= 5
    busy = _busy(cand)
    assert busy, "the demo should have something in the calendar"
    tz = ZoneInfo("Africa/Tunis")
    for s in slots:
        a, b = _when(s["start"]), _when(s["end"])
        assert b - a == timedelta(minutes=45) and a > datetime.now(timezone.utc)
        la, lb = a.astimezone(tz), b.astimezone(tz)
        assert la.weekday() < 5 and la.hour >= config.WORK_START_HOUR and (lb.hour, lb.minute) <= (config.WORK_END_HOUR, 0)
        assert not (la.hour < 13 and lb.hour * 60 + lb.minute > 12 * 60), "no slot crosses lunch"
        assert all(not (a < be and bs < b) for bs, be in busy), s


def test_a_slot_taken_by_a_meeting_is_no_longer_suggested(demo):
    first = _q(demo).json()["slots"][0]
    r = demo.post("/api/meetings", headers=H("U-MGR"), json={
        "title": "Budget review", "start": first["start"], "duration_minutes": 60, "timezone": "Africa/Tunis",
        "attendee_ids": [], "location": "", "description": ""})
    assert r.status_code in (200, 201), r.text
    assert first["start"] not in [s["start"] for s in _q(demo).json()["slots"]]


def test_a_suggested_slot_can_be_booked(demo):
    cand = shortlisted(demo)[0]["id"]
    slot = _q(demo, candidate_id=cand).json()["slots"][0]
    r = demo.post("/api/interviews", headers=H(), json={
        "case_id": CASE, "candidate_id": cand, "interviewer_id": "U-MGR", "interview_type": "technical",
        "scheduled_start": slot["start"], "duration_minutes": 45, "timezone": "Africa/Tunis"})
    assert r.status_code == 201, r.text


@pytest.mark.parametrize("bad", [{"duration": 10}, {"duration": 50}, {"timezone": "Mars/Base"}, {"days": 60},
                                 {"unknown": "x"}, {"interviewer_id": "U-AUD"}])
def test_bad_parameters_are_refused(demo, bad):
    assert _q(demo, **bad).status_code in (404, 422)


def test_only_recruiters_on_the_case_can_ask(demo):
    cand = shortlisted(demo)[0]["id"]
    r = demo.get(f"/api/cases/{CASE}/slots", headers=H("U-AUD"),
                 params={"candidate_id": cand, "interviewer_id": "U-MGR", "duration": 45, "timezone": "UTC"})
    assert r.status_code == 403


def test_not_shortlisted_candidate_is_refused(demo):
    other = [x for x in demo.get("/api/candidates?case_id=CASE-DEMO&limit=100", headers=H()).json()["items"]
             if not x["shortlisted"]][0]["id"]
    assert _q(demo, candidate_id=other).status_code == 409


def test_feature_switch_off(demo, monkeypatch):
    monkeypatch.setenv("FEAT_SLOTS_MODE", "off")
    r = _q(demo)
    assert r.status_code == 404 and r.json()["error"]["code"] == "FEATURE_OFF"
