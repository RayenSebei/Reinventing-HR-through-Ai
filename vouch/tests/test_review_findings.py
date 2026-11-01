"""Regression tests for the external review findings (2026-11-01). Written red first."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("VOUCH_DATA_DIR", tempfile.mkdtemp(prefix="vouch-findings-tests-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app import config, db, evidence, gateway  # noqa: E402
from app.errors import ApiError  # noqa: E402
from app.main import app  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_hitl import CASE, H, confirm_contact, shortlist, upload  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    from app.seed import seed
    monkeypatch.setattr(config, "OUTBOUND_MODE", "sink", raising=False)
    monkeypatch.setattr(config, "N8N_WEBHOOK_URL", "")
    monkeypatch.setenv("VOUCH_DEMO_MODE", "1")
    seed()
    from app import main
    main._fails.clear()
    with TestClient(app) as c:
        yield c


def _proposal(c):
    d = upload(c)
    assert shortlist(c).status_code == 200
    assert confirm_contact(c, d["candidate_id"]).status_code == 200
    r = c.post(f"/api/cases/{CASE}/proposals", headers=H(), json={"candidate_id": d["candidate_id"]})
    assert r.status_code == 201, r.text
    return r.json()


# --- P0: the manager's approval is bound to the content they viewed ------------------------
def test_approve_requires_the_hash_the_manager_viewed(client):
    p = _proposal(client)
    r = client.post(f"/api/proposals/{p['id']}/approve", headers=H("U-MGR"), json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "APPROVAL_HASH_REQUIRED"
    assert not db.q("SELECT 1 FROM approvals WHERE proposal_id=?", (p["id"],))


def test_approve_refused_when_content_changed_after_manager_viewed_it(client):
    p = _proposal(client)
    viewed = client.get(f"/api/proposals/{p['id']}", headers=H("U-MGR")).json()["payload_sha256"]
    client.patch(f"/api/proposals/{p['id']}", headers=H(), json={"body": "Changed after the manager looked."})
    r = client.post(f"/api/proposals/{p['id']}/approve", headers=H("U-MGR"), json={"payload_sha256": viewed})
    assert r.status_code == 409 and r.json()["error"]["code"] == "PAYLOAD_CHANGED_SINCE_VIEWED"
    assert not db.q("SELECT 1 FROM approvals WHERE proposal_id=?", (p["id"],))
    assert "APPROVED" not in [e["type"] for e in client.get(f"/api/ledger?case_id={CASE}", headers=H("U-AUD")).json()]


def test_approve_with_the_viewed_current_hash_works(client):
    p = _proposal(client)
    viewed = client.get(f"/api/proposals/{p['id']}", headers=H("U-MGR")).json()["payload_sha256"]
    r = client.post(f"/api/proposals/{p['id']}/approve", headers=H("U-MGR"), json={"payload_sha256": viewed})
    assert r.status_code == 200
    assert db.one("SELECT payload_sha256 FROM approvals WHERE proposal_id=?", (p["id"],))["payload_sha256"] == viewed


def test_recruiter_still_gets_403_not_a_validation_error(client):
    p = _proposal(client)
    assert client.post(f"/api/proposals/{p['id']}/approve", headers=H(), json={}).status_code == 403


# --- P0: subject and recipient cannot smuggle header lines ---------------------------------
@pytest.mark.parametrize("subject", ["Hi Bcc: x@evil.example", "Hi\x85Bcc: x@evil.example", "Hi\x0bthere",
                                     "Hi\x00", "Hi x", "Hi\tBcc: x@evil.example"])
def test_subject_rejects_any_line_break_or_control_character(subject):
    with pytest.raises(ApiError):
        gateway._validate_payload({"recipient": "a@candidates.example.invalid", "subject": subject, "kind": "follow_up"})


# --- P1: one person's failed logins do not lock everyone else out --------------------------
def test_failed_logins_from_one_client_do_not_lock_the_manager_elsewhere(client):
    for _ in range(12):        # an attacker types wrong passwords for the manager's account
        client.post("/api/auth/login", json={"email": "manager@vouch.demo", "password": "wrong-password"})
    assert client.post("/api/auth/login", json={"email": "manager@vouch.demo", "password": "demo1234"}).status_code == 429
    with TestClient(app, client=("198.51.100.7", 50000)) as office:    # the real manager, another machine
        r = office.post("/api/auth/login", json={"email": "manager@vouch.demo", "password": "demo1234"})
        assert r.status_code == 200, r.text


def test_password_spraying_from_one_client_is_limited(client):
    codes = [client.post("/api/auth/login", json={"email": f"user{i}@vouch.demo", "password": "x"}).status_code
             for i in range(60)]
    assert 429 in codes


# --- P1: only recruiters see unredacted CV text --------------------------------------------
@pytest.mark.parametrize("uid", ["U-MGR", "U-AUD", "U-ADM"])
def test_extraction_is_redacted_for_every_role_except_recruiter(client, uid):
    d = upload(client, Path(__file__).resolve().parents[2] / "sentinel_hr" / "fixtures" / "ai004_contact_canary.pdf")
    doc = d["document"]["id"]
    r = client.get(f"/api/documents/{doc}/extraction", headers=H(uid))
    if r.status_code in (403, 404):
        return                                  # no case access at all is also fine
    text = r.json()["visible_text"] + r.json()["hidden_text"]
    assert "candidate-ai04@example.invalid" not in text and "[EMAIL]" in text


# --- P1: negated mentions are not evidence --------------------------------------------------
@pytest.mark.parametrize("line", ["Not familiar with Python", "I have not used Python yet", "Haven't worked with Python",
                                  "No knowledge of Python", "Never touched Python", "Did not use Python",
                                  "Aucune expérience en Python", "Jamais utilisé Python", "Sans expérience Python"])
def test_negated_mentions_are_not_evidence(line):
    criterion = {"id": "c1", "label": "Python experience", "aliases": []}
    pages = {1: [(line, [])]}
    assert evidence.lexicon_match(criterion, pages)["status"] == "NOT_FOUND", line
    assert evidence.verify_quote("Python", 1, pages)[0] == "NOT_FOUND", line


def test_positive_mentions_still_count():
    criterion = {"id": "c1", "label": "Python experience", "aliases": []}
    pages = {1: [("Built Python services for three years; never missed a release", [{"x0": 0, "top": 0, "x1": 1, "bottom": 1}])]}
    assert evidence.lexicon_match(criterion, pages)["status"] != "NOT_FOUND"


# --- P1: a huge PDF page cannot exhaust memory, in analysis or in the page preview ----------
def _big_page_pdf(side_pt=14400, user_unit=None):
    import io
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument.new()
    doc.new_page(side_pt, side_pt)
    buf = io.BytesIO()
    doc.save(buf)
    data = buf.getvalue()
    if user_unit:   # /UserUnit multiplies the real page size without changing the MediaBox numbers
        data = data.replace(b"/Type /Page", b"/Type /Page /UserUnit %d" % user_unit, 1)
    return data


def test_page_preview_refuses_oversized_pages():
    from app import documents
    with pytest.raises(ApiError):
        documents.render_page_png(_big_page_pdf(), 1)


def test_analysis_refuses_oversized_pages():
    from app import documents
    with pytest.raises(ApiError):
        documents.analyse_pdf(_big_page_pdf())
