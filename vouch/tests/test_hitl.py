"""Human-in-the-loop, outbound and reliability contracts (master plan Phases 1-2).

Each test names the plan ID it proves. Run from vouch/:  python -m pytest -q tests/test_hitl.py
"""
import os
import sqlite3
import tempfile
from pathlib import Path

os.environ.setdefault("VOUCH_DATA_DIR", tempfile.mkdtemp(prefix="vouch-hitl-tests-"))

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app import config, db  # noqa: E402
from app.main import app  # noqa: E402
from app.security import issue_token  # noqa: E402
from app.seed import seed  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CLEAN = REPO / "sentinel" / "datasets" / "clean_cvs" / "clean_cv.pdf"
CASE = "CASE-DEMO"


def H(uid="U-REC"):
    return {"Authorization": "Bearer " + issue_token(uid)}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "OUTBOUND_MODE", "sink", raising=False)
    monkeypatch.setattr(config, "N8N_WEBHOOK_URL", "")
    seed()
    with TestClient(app) as c:
        yield c


def upload(c, path=CLEAN):
    with open(path, "rb") as f:
        r = c.post(f"/api/cases/{CASE}/candidates", headers=H(), files={"file": (path.name, f, "application/pdf")})
    assert r.status_code in (201, 202), r.text
    return r.json()


def open_all_dossiers(c, rows, uid="U-REC"):
    for row in rows:
        assert c.get(f"/api/candidates/{row['candidate_id']}/dossier", headers=H(uid)).status_code == 200


def shortlist(c, review=True):
    rk = c.post(f"/api/cases/{CASE}/ranking", headers=H()).json()
    if review:
        open_all_dossiers(c, rk["rows"])
    return c.post(f"/api/cases/{CASE}/ranking/{rk['version']}/shortlist", headers=H(),
                  json={"candidate_ids": [r["candidate_id"] for r in rk["rows"]]})


def confirm_contact(c, cand_id, email=None):
    if email is None:
        email = c.get(f"/api/candidates/{cand_id}/contact", headers=H()).json()["suggested_email"]
    return c.post(f"/api/candidates/{cand_id}/contact/confirm", headers=H(), json={"email": email})


def approve_viewed(c, pid, uid="U-MGR"):
    """The manager approves exactly the version they just looked at."""
    viewed = c.get(f"/api/proposals/{pid}", headers=H(uid)).json()["payload_sha256"]
    return c.post(f"/api/proposals/{pid}/approve", headers=H(uid), json={"payload_sha256": viewed})


def ready_proposal(c, approve=True):
    d = upload(c)
    assert shortlist(c).status_code == 200
    assert confirm_contact(c, d["candidate_id"]).status_code == 200
    p = c.post(f"/api/cases/{CASE}/proposals", headers=H(), json={"candidate_id": d["candidate_id"]})
    assert p.status_code == 201, p.text
    p = p.json()
    if approve:
        assert approve_viewed(c, p["id"]).status_code == 200
    return d, p


# --- HI-04 / D11: a human confirms the recipient ---------------------------------------
def test_proposal_refused_until_recipient_confirmed(client):
    d = upload(client)
    assert shortlist(client).status_code == 200
    r = client.post(f"/api/cases/{CASE}/proposals", headers=H(), json={"candidate_id": d["candidate_id"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "RECIPIENT_NOT_CONFIRMED"


def test_cv_email_is_only_a_suggestion(client):
    d = upload(client)
    info = client.get(f"/api/candidates/{d['candidate_id']}/contact", headers=H()).json()
    assert info["suggested_email"] and info["confirmed_email"] is None
    assert info["source"] == "cv_text"


@pytest.mark.parametrize("bad", ["a@x.example\r\nBcc: evil@x.example", "a@x.example, b@x.example",
                                 "a@x.example;b@x.example", "not-an-address", "a@x.\nexample", "<a@x.example>",
                                 "Name <a@x.example>", "a@x.example\x00"])
def test_recipient_must_be_one_clean_address(client, bad):
    d = upload(client)
    r = confirm_contact(client, d["candidate_id"], bad)
    assert r.status_code == 422, (bad, r.text)


def test_surrounding_whitespace_is_stripped_never_stored(client):
    d = upload(client)
    r = confirm_contact(client, d["candidate_id"], "  a@x.example\r\n")
    assert r.status_code == 200 and r.json()["confirmed_email"] == "a@x.example"


def test_edit_recipient_to_injection_is_refused(client):
    _, p = ready_proposal(client, approve=False)
    r = client.patch(f"/api/proposals/{p['id']}", headers=H(), json={"recipient": "a@x.example\r\nBcc: z@x.example"})
    assert r.status_code == 422


def test_only_recruiter_member_confirms_recipient(client):
    d = upload(client)
    r = client.post(f"/api/candidates/{d['candidate_id']}/contact/confirm", headers=H("U-MGR"),
                    json={"email": "someone@candidates.example.invalid"})
    assert r.status_code == 403


def test_contact_never_in_ledger(client):
    d = upload(client)
    confirm_contact(client, d["candidate_id"], "canary-contact@candidates.example.invalid")
    led = client.get(f"/api/ledger?case_id={CASE}", headers=H("U-AUD")).text
    assert "canary-contact" not in led and "CONTACT_CONFIRMED" in led


def test_execute_refused_when_recipient_differs_from_confirmed(client):
    d, p = ready_proposal(client, approve=False)
    client.patch(f"/api/proposals/{p['id']}", headers=H(), json={"recipient": "other@candidates.example.invalid"})
    assert approve_viewed(client, p["id"]).status_code == 200
    r = client.post(f"/api/proposals/{p['id']}/execute", headers=H())
    assert r.status_code == 409 and r.json()["error"]["code"] == "RECIPIENT_NOT_CONFIRMED"
    assert client.get(f"/api/cases/{CASE}/outbox", headers=H()).json() == []


# --- HI-03: review gate on the server ------------------------------------------------------
def test_shortlist_confirm_requires_opening_dossiers(client):
    upload(client)
    r = shortlist(client, review=False)
    assert r.status_code == 409 and r.json()["error"]["code"] == "REVIEW_REQUIRED"


def test_another_users_review_does_not_count(client):
    upload(client)
    rk = client.post(f"/api/cases/{CASE}/ranking", headers=H()).json()
    open_all_dossiers(client, rk["rows"], uid="U-MGR")
    r = client.post(f"/api/cases/{CASE}/ranking/{rk['version']}/confirm", headers=H())
    assert r.status_code == 409


def test_upload_response_is_not_a_review(client):
    upload(client)       # the upload returns the dossier, but that is not the recruiter opening it
    assert shortlist(client, review=False).status_code == 409


# --- RB-05 was not adopted: main locks criteria once evidence exists (CRITERIA_LOCKED, tested in
# test_dashboard.py). A review gate still applies to the explicit shortlist. -------------------
def test_shortlist_of_unopened_candidate_is_refused(client):
    d = upload(client)
    rk = client.post(f"/api/cases/{CASE}/ranking", headers=H()).json()
    r = client.post(f"/api/cases/{CASE}/ranking/{rk['version']}/shortlist", headers=H(),
                    json={"candidate_ids": [d["candidate_id"]]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "REVIEW_REQUIRED"
    assert not db.q("SELECT 1 FROM shortlisted_candidates WHERE candidate_id=?", (d["candidate_id"],))


# --- HL-01/HL-02 backstop: the database refuses an unapproved send --------------------------
def test_direct_outbox_insert_refused_by_database(client):
    _, p = ready_proposal(client, approve=False)
    with pytest.raises(sqlite3.DatabaseError):
        db.q("INSERT INTO outbox VALUES (?,?,?,?,?,?,?)",
             ("OUT-X", p["id"], CASE, '{"x":1}', "QUEUED", "", db.now()))


def test_one_outbox_row_per_proposal(client):
    _, p = ready_proposal(client)
    assert client.post(f"/api/proposals/{p['id']}/execute", headers=H()).status_code == 200
    row = db.one("SELECT * FROM outbox WHERE proposal_id=?", (p["id"],))
    with pytest.raises(sqlite3.DatabaseError):
        db.q("INSERT INTO outbox VALUES (?,?,?,?,?,?,?)",
             ("OUT-Y", p["id"], CASE, row["payload_json"], "QUEUED", "", db.now()))


# --- HL-07: global outbound kill switch ------------------------------------------------------
class _Resp:
    def __init__(self, code):
        self.status_code, self.ok = code, 200 <= code < 300


def test_kill_switch_disabled_holds_everything(client, monkeypatch):
    calls = []
    monkeypatch.setattr("requests.post", lambda *a, **k: calls.append(1) or _Resp(200))
    monkeypatch.setattr(config, "N8N_WEBHOOK_URL", "https://n8n.example.invalid/webhook/x")
    monkeypatch.setattr(config, "N8N_HMAC_SECRET", "s" * 32)
    monkeypatch.setattr(config, "OUTBOUND_MODE", "disabled")
    _, p = ready_proposal(client)
    out = client.post(f"/api/proposals/{p['id']}/execute", headers=H()).json()
    row = db.one("SELECT delivery_status FROM outbox WHERE id=?", (out["outbox_id"],))
    assert calls == [] and row["delivery_status"] == "HELD_OUTBOUND_DISABLED"


def test_kill_switch_sink_never_calls_n8n(client, monkeypatch):
    calls = []
    monkeypatch.setattr("requests.post", lambda *a, **k: calls.append(1) or _Resp(200))
    monkeypatch.setattr(config, "N8N_WEBHOOK_URL", "https://n8n.example.invalid/webhook/x")
    monkeypatch.setattr(config, "N8N_HMAC_SECRET", "s" * 32)
    monkeypatch.setattr(config, "OUTBOUND_MODE", "sink")
    _, p = ready_proposal(client)
    out = client.post(f"/api/proposals/{p['id']}/execute", headers=H()).json()
    row = db.one("SELECT delivery_status FROM outbox WHERE id=?", (out["outbox_id"],))
    assert calls == [] and row["delivery_status"] == "SANDBOX_ONLY"


def test_kill_switch_live_calls_n8n_once(client, monkeypatch):
    calls = []
    monkeypatch.setattr("requests.post", lambda *a, **k: calls.append(k) or _Resp(200))
    monkeypatch.setattr(config, "N8N_WEBHOOK_URL", "https://n8n.example.invalid/webhook/x")
    monkeypatch.setattr(config, "N8N_HMAC_SECRET", "s" * 32)
    monkeypatch.setattr(config, "OUTBOUND_MODE", "live")
    _, p = ready_proposal(client)
    out = client.post(f"/api/proposals/{p['id']}/execute", headers=H()).json()
    assert len(calls) == 1 and calls[0]["json"]["outbox_id"] == out["outbox_id"]
    assert db.one("SELECT delivery_status FROM outbox WHERE id=?", (out["outbox_id"],))["delivery_status"] == "DELIVERED"


# --- RB-07: human-triggered retry resends the same approved bytes, once -----------------------
def test_retry_after_failure_sends_same_payload_once(client, monkeypatch):
    sent = []
    answers = iter([_Resp(503), _Resp(200), _Resp(200)])
    monkeypatch.setattr("requests.post", lambda *a, **k: sent.append(k["json"]["payload_json"]) or next(answers))
    monkeypatch.setattr(config, "N8N_WEBHOOK_URL", "https://n8n.example.invalid/webhook/x")
    monkeypatch.setattr(config, "N8N_HMAC_SECRET", "s" * 32)
    monkeypatch.setattr(config, "OUTBOUND_MODE", "live")
    _, p = ready_proposal(client)
    oid = client.post(f"/api/proposals/{p['id']}/execute", headers=H()).json()["outbox_id"]
    assert db.one("SELECT delivery_status FROM outbox WHERE id=?", (oid,))["delivery_status"] == "DELIVERY_FAILED"
    r = client.post(f"/api/outbox/{oid}/retry", headers=H())
    assert r.status_code == 200 and r.json()["delivery_status"] == "DELIVERED"
    again = client.post(f"/api/outbox/{oid}/retry", headers=H())
    assert again.status_code == 409 and again.json()["error"]["code"] == "ALREADY_DELIVERED"
    assert len(sent) == 2 and sent[0] == sent[1]


def test_retry_needs_case_membership(client, monkeypatch):
    monkeypatch.setattr("requests.post", lambda *a, **k: _Resp(500))
    monkeypatch.setattr(config, "N8N_WEBHOOK_URL", "https://n8n.example.invalid/webhook/x")
    monkeypatch.setattr(config, "N8N_HMAC_SECRET", "s" * 32)
    monkeypatch.setattr(config, "OUTBOUND_MODE", "live")
    _, p = ready_proposal(client)
    oid = client.post(f"/api/proposals/{p['id']}/execute", headers=H()).json()["outbox_id"]
    assert client.post(f"/api/outbox/{oid}/retry", headers=H("U-AUD")).status_code in (403, 404)


# --- RB-09 / RB-06: health and readiness --------------------------------------------------------
def test_healthz_and_readyz(client):
    assert client.get("/api/healthz").json() == {"ok": True}
    r = client.get("/api/readyz").json()
    assert r["ok"] and r["integrity"] == "ok" and r["ledger_ok"] and r["schema_version"] >= 1
