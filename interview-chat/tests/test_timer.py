"""Interview timer: answers are saved with their response time; the server enforces the limit."""
from conftest import candidate_id_by_file, invite_and_get_token, login

from interview_bot import db
from interview_bot.config import settings


def _start(client, lang="en"):
    cid = candidate_id_by_file("amine")
    T = {"X-Interview-Token": invite_and_get_token(client, cid)}
    client.post("/api/interview/start", headers=T, json={"language": lang, "consent": True})
    return cid, T


def _shift_start(cid, seconds):
    conn = db.connect()
    conn.execute("UPDATE interview_sessions SET started_at = started_at - ? WHERE candidate_id=?", (seconds, cid))
    conn.close()


def test_info_reports_time_left(client):
    cid, T = _start(client)
    timer = client.get("/api/interview/info", headers=T).json()["timer"]
    assert timer["limit_s"] == settings.interview_time_limit_min * 60
    assert 0 < timer["remaining_s"] <= timer["limit_s"]


def test_each_answer_is_saved_with_its_response_time(client):
    cid, T = _start(client)
    client.post("/api/interview/message", headers=T,
                json={"text": "I built a booking REST API with Flask and wrote the endpoints myself."})
    t = client.get(f"/api/candidates/{cid}/transcript", headers=login(client, "sarra")).json()
    answer = [m for m in t if m["sender"] == "candidate"][0]
    assert answer["text"].startswith("I built") and isinstance(answer["flags"]["seconds"], int)


def test_answer_in_grace_period_is_kept_then_interview_closes(client):
    cid, T = _start(client)
    _shift_start(cid, settings.interview_time_limit_min * 60 + 10)       # 10 s after the limit
    r = client.post("/api/interview/message", headers=T, json={"text": "My last answer about SQL indexes and query plans."}).json()
    assert r["completed"] is True
    assert db.one("SELECT COUNT(*) AS n FROM messages WHERE sender='candidate'")["n"] == 1
    assert db.one("SELECT state FROM interview_sessions WHERE candidate_id=?", (cid,))["state"] == "completed"


def test_late_answer_is_refused_and_report_generated(client):
    cid, T = _start(client)
    _shift_start(cid, settings.interview_time_limit_min * 60 + 120)      # 2 minutes too late
    r = client.post("/api/interview/message", headers=T, json={"text": "Too late answer."}).json()
    assert r["completed"] is True
    assert db.one("SELECT COUNT(*) AS n FROM messages WHERE sender='candidate'")["n"] == 0
    assert db.one("SELECT COUNT(*) AS n FROM reports WHERE candidate_id=?", (cid,))["n"] >= 1


def test_abandoned_interview_closes_when_link_reopened(client):
    cid, T = _start(client)
    _shift_start(cid, settings.interview_time_limit_min * 60 + 120)
    info = client.get("/api/interview/info", headers=T).json()
    assert info["state"] == "completed"


def test_no_limit_when_set_to_zero(client, monkeypatch):
    monkeypatch.setattr(settings, "interview_time_limit_min", 0)
    cid, T = _start(client)
    _shift_start(cid, 10 * 3600)
    r = client.post("/api/interview/message", headers=T, json={"text": "I built a REST API with FastAPI and PostgreSQL."}).json()
    assert r["completed"] is False
