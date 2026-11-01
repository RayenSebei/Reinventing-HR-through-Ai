"""F3: candidates who have not replied to a sent message are detected; follow-ups stay human-approved."""
from datetime import timedelta

from helpers_assist import CASE, H, demo, shortlisted  # noqa: F401
from app import config, db


def _send_invite(c, cand):
    con = c.get(f"/api/candidates/{cand}/contact", headers=H()).json()
    c.post(f"/api/candidates/{cand}/contact/confirm", headers=H(), json={"email": con["suggested_email"]})
    p = c.post(f"/api/cases/{CASE}/proposals", headers=H(), json={"candidate_id": cand, "start": "2031-03-04T10:00:00Z"}).json()
    c.post(f"/api/proposals/{p['id']}/approve", headers=H("U-MGR"), json={"payload_sha256": p["payload_sha256"]})
    r = c.post(f"/api/proposals/{p['id']}/execute", headers=H())
    assert r.status_code == 200, r.text
    return r.json()["outbox_id"]


def _age(oid, days):
    """Move this send back in time; older sends to the same candidate (e.g. from the demo seed) move further back."""
    def iso(d):
        return (db.utcnow() - timedelta(days=d)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    db.q("UPDATE outbox SET created_at=? WHERE id<>? AND proposal_id IN (SELECT id FROM proposals WHERE candidate_id="
         "(SELECT p.candidate_id FROM outbox o JOIN proposals p ON p.id=o.proposal_id WHERE o.id=?))", (iso(days + 30), oid, oid))
    db.q("UPDATE outbox SET created_at=? WHERE id=?", (iso(days), oid))


def _items(c, uid="U-REC"):
    r = c.get("/api/follow-ups/awaiting-reply", headers=H(uid))
    assert r.status_code == 200, r.text
    return {i["outbox_id"]: i for i in r.json()["items"]}


def test_seeded_demo_has_one_overdue_and_one_answered_invitation(demo):
    items = demo.get("/api/follow-ups/awaiting-reply", headers=H()).json()["items"]
    assert [i["overdue"] for i in items] == [True]
    assert db.one("SELECT source FROM outbox_replies")["source"] == "inbox"


def test_sent_message_without_reply_is_listed_and_becomes_overdue(demo):
    cand = shortlisted(demo)[0]["id"]
    oid = _send_invite(demo, cand)
    item = _items(demo)[oid]
    assert item["candidate_id"] == cand and not item["overdue"] and item["days_waiting"] == 0
    assert "recipient" not in str(item) and "@" not in str(item)          # no contact details in the list
    _age(oid, config.REPLY_WAIT_DAYS + 1)
    item = _items(demo)[oid]
    assert item["overdue"] and item["days_waiting"] == config.REPLY_WAIT_DAYS + 1


def test_marking_replied_removes_it_and_is_ledgered(demo):
    oid = _send_invite(demo, shortlisted(demo)[0]["id"])
    assert demo.post(f"/api/outbox/{oid}/replied", headers=H(), json={}).status_code == 200
    assert oid not in _items(demo)
    assert demo.post(f"/api/outbox/{oid}/replied", headers=H(), json={}).status_code == 409
    types = [e["type"] for e in demo.get(f"/api/ledger?case_id={CASE}", headers=H("U-AUD")).json()]
    assert "REPLY_RECORDED" in types


def test_follow_up_draft_needs_manager_approval_and_creates_a_task(demo):
    oid = _send_invite(demo, shortlisted(demo)[0]["id"])
    _age(oid, config.REPLY_WAIT_DAYS + 1)
    r = demo.post(f"/api/outbox/{oid}/follow-up", headers=H(), json={})
    assert r.status_code == 201, r.text
    p = r.json()["proposal"]
    assert p["kind"] == "follow_up" and p["status"] == "PENDING_APPROVAL" and p["approval"] is None
    assert not db.q("SELECT 1 FROM outbox WHERE proposal_id=?", (p["id"],))       # nothing sent
    task = db.one("SELECT * FROM follow_up_tasks WHERE proposal_id=?", (p["id"],))
    assert task and task["task_type"] == "follow_up" and task["origin"] == "workflow"
    again = demo.post(f"/api/outbox/{oid}/follow-up", headers=H(), json={})
    assert again.status_code == 200 and again.json()["proposal"]["id"] == p["id"]   # idempotent
    assert _items(demo)[oid]["follow_up_proposal_id"] == p["id"]


def test_a_newer_message_replaces_the_older_one(demo):
    cand = shortlisted(demo)[0]["id"]
    first = _send_invite(demo, cand)
    second = _send_invite(demo, cand)
    items = _items(demo)
    assert second in items and first not in items


def test_scope_and_roles(demo):
    oid = _send_invite(demo, shortlisted(demo)[0]["id"])
    assert demo.post(f"/api/outbox/{oid}/replied", headers=H("U-AUD"), json={}).status_code == 403
    assert demo.post(f"/api/outbox/{oid}/follow-up", headers=H("U-MGR"), json={}).status_code == 403
    assert demo.post("/api/outbox/OUT-NOPE/replied", headers=H(), json={}).status_code == 404
    assert demo.get("/api/follow-ups/awaiting-reply?x=1", headers=H()).status_code == 422


def test_feature_switch_off(demo, monkeypatch):
    monkeypatch.setenv("FEAT_REPLY_TRACKING_MODE", "off")
    assert demo.get("/api/follow-ups/awaiting-reply", headers=H()).status_code == 404


def test_no_follow_up_after_the_candidate_replied(demo):
    oid = _send_invite(demo, shortlisted(demo)[0]["id"])
    demo.post(f"/api/outbox/{oid}/replied", headers=H(), json={})
    r = demo.post(f"/api/outbox/{oid}/follow-up", headers=H(), json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "ALREADY_REPLIED"
