"""HI-07: stateful invariant fuzzer over the real API (master plan Section 8.3).

Random, seeded sequences of: create proposal, confirm/change recipient (good and hostile values),
edit, approve, reject, execute, retry, move the clock, flip the outbound kill switch, act as the
wrong user. After EVERY step the database is checked against the invariants below.

Default run: VOUCH_FUZZ_SEQUENCES=300 (CI budget). Full run: VOUCH_FUZZ_SEQUENCES=10000.
A violation prints the seed and the step list so it can be replayed.
"""
import os
import random
import tempfile
from pathlib import Path

os.environ.setdefault("VOUCH_DATA_DIR", tempfile.mkdtemp(prefix="vouch-fuzz-tests-"))

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app import config, db, ledger  # noqa: E402
from app.canonical import payload_hash  # noqa: E402
from app.main import app  # noqa: E402
from app.security import issue_token  # noqa: E402
from app.seed import seed  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CVS = [REPO / "sentinel" / "datasets" / "clean_cvs" / "clean_cv.pdf",
       REPO / "sentinel" / "datasets" / "adversarial_cvs" / "keyword_stuffing.pdf"]
CASE = "CASE-DEMO"
SEQUENCES = int(os.environ.get("VOUCH_FUZZ_SEQUENCES", "300"))
STEPS = 8
USERS = ["U-REC", "U-MGR", "U-ADM", "U-AUD"]
EMAILS = ["cand@candidates.example.invalid", "other@candidates.example.invalid",
          "a@x.example\r\nBcc: z@x.example", "a@x.example, b@x.example", "Name <a@x.example>"]


class _Resp:
    def __init__(self, code):
        self.status_code, self.ok = code, 200 <= code < 300


def H(uid):
    return {"Authorization": "Bearer " + issue_token(uid)}


@pytest.fixture(scope="module")
def world():
    seed()
    sent = []        # every call that reached the transport: (mode at send time, outbox_id, payload_json)
    with TestClient(app) as c:
        cands = []
        for cv in CVS:
            with open(cv, "rb") as f:
                cands.append(c.post(f"/api/cases/{CASE}/candidates", headers=H("U-REC"),
                                    files={"file": (cv.name, f, "application/pdf")}).json()["candidate_id"])
        rk = c.post(f"/api/cases/{CASE}/ranking", headers=H("U-REC")).json()
        for row in rk["rows"]:
            c.get(f"/api/candidates/{row['candidate_id']}/dossier", headers=H("U-REC"))
        assert c.post(f"/api/cases/{CASE}/ranking/{rk['version']}/shortlist", headers=H("U-REC"),
                      json={"candidate_ids": [r["candidate_id"] for r in rk["rows"]]}).status_code == 200
        yield c, cands, sent


def check_invariants(sent, confirmed_at_execute, since_rowid=0):
    # I1: every outbox row is backed by one approved, used approval whose hash equals the sent payload,
    #     from someone other than the proposal's creator. (Rows after since_rowid; a full pass uses 0.)
    for o in db.q("SELECT rowid AS rid, * FROM outbox WHERE rowid > ?", (since_rowid,)):
        a = db.q("SELECT * FROM approvals WHERE proposal_id=? AND used_at IS NOT NULL", (o["proposal_id"],))
        p = db.one("SELECT * FROM proposals WHERE id=?", (o["proposal_id"],))
        assert len(a) == 1, f"I1/I2: {o['id']} has {len(a)} used approvals"
        assert a[0]["decision"] == "approved", "I1: used approval is not an approval"
        assert a[0]["payload_sha256"] == payload_hash(db.loads(o["payload_json"])), "I1: sent bytes != approved hash"
        assert a[0]["approver_id"] != p["created_by"], "I1: self-approval"
        # I5: the recipient is exactly the human-confirmed address at the time of execution, one address
        rec = db.loads(o["payload_json"])["recipient"]
        assert rec == confirmed_at_execute[o["id"]], "I5: recipient differs from confirmed contact"
        assert all(ch not in rec for ch in "\r\n,;<> "), "I5: recipient is not a single clean address"
    # I2: at most one outbox row per proposal
    assert db.one("SELECT COUNT(*) n FROM (SELECT proposal_id FROM outbox GROUP BY proposal_id HAVING COUNT(*)>1)")["n"] == 0
    # I4: nothing reached the transport unless the switch was 'live' at that moment; each outbox id
    #     delivered at most once
    assert all(mode == "live" for mode, _, _ in sent), "I4: something left while not live"
    twice = db.one("SELECT COUNT(*) n FROM (SELECT outbox_id FROM delivery_attempts WHERE status='DELIVERED' "
                   "GROUP BY outbox_id HAVING COUNT(*) > 1)")["n"]
    assert twice == 0, "I9: an outbox item was delivered twice"
    if since_rowid == 0:      # full pass: every transport call belongs to a real outbox row
        known = {r["id"] for r in db.q("SELECT id FROM outbox")}
        assert {oid for _, oid, _ in sent} <= known, "I1: transport call for an unknown outbox id"


def check_ledger():
    # I6: ledger chain verifies (O(n), so checked every few steps and at the end)
    assert ledger.verify()["ok"], "I6: ledger chain broken"


def test_invariants_hold_under_random_sequences(world, monkeypatch):
    c, cands, sent = world
    monkeypatch.setattr(config, "N8N_WEBHOOK_URL", "https://n8n.example.invalid/webhook/x")
    monkeypatch.setattr(config, "N8N_HMAC_SECRET", "s" * 32)
    monkeypatch.setattr(config, "OUTBOUND_MODE", "sink")     # restored after the test even on failure
    monkeypatch.setattr(db, "CLOCK_OFFSET_MINUTES", 0)
    state = {"answer": 200}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.append((config.OUTBOUND_MODE, json["outbox_id"], json["payload_json"]))
        return _Resp(state["answer"])
    monkeypatch.setattr("requests.post", fake_post)
    confirmed_at_execute = {}
    steps_run = 0
    props = []                       # proposals live across sequences so long paths are reachable
    checked_upto = 0
    for seq in range(SEQUENCES):
        rng = random.Random(seq)
        log = []
        for _ in range(STEPS):
            act = rng.choice(["create", "create", "confirm", "edit", "approve", "approve", "reject",
                              "execute", "execute", "execute", "retry", "retry", "clock", "mode", "answer"])
            # mostly the right person for the action, sometimes anyone (authorization is fuzzed too)
            right = {"create": "U-REC", "confirm": "U-REC", "edit": "U-REC", "approve": "U-MGR", "reject": "U-MGR",
                     "execute": rng.choice(["U-REC", "U-MGR"]), "retry": "U-REC"}.get(act, "U-REC")
            who = right if rng.random() < 0.8 else rng.choice(USERS)
            pid = rng.choice(props[-6:]) if props else None
            log.append((act, who, pid))
            if act == "create":
                r = c.post(f"/api/cases/{CASE}/proposals", headers=H(who),
                           json={"candidate_id": rng.choice(cands), "kind": rng.choice(["interview_invite", "follow_up"])})
                if r.status_code == 201:
                    props.append(r.json()["id"])
            elif act == "confirm":
                email = EMAILS[0] if rng.random() < 0.6 else rng.choice(EMAILS)
                c.post(f"/api/candidates/{rng.choice(cands)}/contact/confirm", headers=H(who), json={"email": email})
            elif act == "edit" and pid:
                field = rng.choice(["recipient", "subject", "start"])
                val = {"recipient": rng.choice(EMAILS), "subject": "Changed", "start": "2031-01-01T10:00:00Z"}[field]
                c.patch(f"/api/proposals/{pid}", headers=H(who), json={field: val})
            elif act in ("approve", "reject") and pid:
                c.post(f"/api/proposals/{pid}/{act}", headers=H(who))
            elif act == "execute" and pid:
                p = db.one("SELECT candidate_id FROM proposals WHERE id=?", (pid,))
                conf = db.one("SELECT email FROM contact_confirmations WHERE candidate_id=?", (p["candidate_id"],))
                r = c.post(f"/api/proposals/{pid}/execute", headers=H(who))
                if r.status_code == 200:
                    confirmed_at_execute[r.json()["outbox_id"]] = conf["email"] if conf else None
            elif act == "retry":
                o = db.one("SELECT id FROM outbox ORDER BY random() LIMIT 1")
                if o:
                    c.post(f"/api/outbox/{o['id']}/retry", headers=H(who))
            elif act == "clock":
                db.CLOCK_OFFSET_MINUTES = rng.choice([0, 0, 10, 20, -5])
            elif act == "mode":
                config.OUTBOUND_MODE = rng.choice(["disabled", "sink", "live"])
            elif act == "answer":
                state["answer"] = rng.choice([200, 200, 500, 503])
            steps_run += 1
            try:
                full = steps_run % 100 == 0
                check_invariants(sent, confirmed_at_execute, 0 if full else checked_upto)
                checked_upto = db.one("SELECT COALESCE(MAX(rowid), 0) AS m FROM outbox")["m"]
                if full:
                    check_ledger()
            except AssertionError as e:
                raise AssertionError(f"seed={seq} steps={log}: {e}") from None
    check_invariants(sent, confirmed_at_execute, 0)
    check_ledger()
    executions = db.one("SELECT COUNT(*) n FROM outbox")["n"]
    # A fuzzer that never reaches a send proves nothing: require real coverage of the risky paths.
    assert executions >= SEQUENCES // 30, f"fuzzer reached only {executions} executions"
    assert any(m == "live" for m, _, _ in sent), "fuzzer never exercised a live delivery"
    print(f"fuzzer: {SEQUENCES} sequences, {steps_run} steps, "
          f"{db.one('SELECT COUNT(*) n FROM outbox')['n']} executions, {len(sent)} transport calls, 0 violations")
