"""Role-scoped workspace and administrator API contracts."""
import hashlib
import hmac
import os
import tempfile
from datetime import datetime, timedelta, timezone

os.environ.setdefault("VOUCH_DATA_DIR", tempfile.mkdtemp(prefix="vouch-workspace-tests-"))

import pytest
from starlette.testclient import TestClient

from app import config, db, ledger, ranking
from app.canonical import canonical
from app.main import app
from app.seed import seed
from app.security import issue_token


@pytest.fixture
def client():
    seed()
    with TestClient(app) as test_client:
        yield test_client


def auth(user_id="U-REC"):
    return {"Authorization": "Bearer " + issue_token(user_id)}


def add_case(case_id, member="U-REC"):
    db.q("INSERT INTO cases(id,title,owner_id,created_at) VALUES(?,?,?,?)",
         (case_id, case_id, "U-REC", db.now()))
    if member:
        db.q("INSERT INTO case_members VALUES(?,?)", (case_id, member))


def add_candidate(candidate_id, case_id="CASE-DEMO", name="Private name"):
    db.q("INSERT INTO candidates VALUES(?,?,?,?,?,?)",
         (candidate_id, case_id, candidate_id, name, "private@example.invalid", db.now()))


def add_document(candidate_id, case_id="CASE-DEMO", finding="HIDDEN_TEXT"):
    doc_id = f"DOC-{candidate_id}"
    db.q("INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?,?,?)",
         (doc_id, candidate_id, case_id, (candidate_id * 64)[:64], "private.pdf", "/not-read", 1,
          "U-REC", "{}", "ANALYSED", db.now()))
    if finding:
        db.q("INSERT INTO findings VALUES(?,?,?,?,?,?,?)",
             (f"F-{candidate_id}", doc_id, finding, "high", 1, "private excerpt", "[]"))
    return doc_id


def test_candidate_table_is_scoped_searchable_sortable_and_paginated(client):
    add_candidate("candidate-b", name="Taylor Private")
    add_candidate("candidate-a", name="Jordan Private")
    add_document("candidate-b")
    ranking_payload = [
        {"candidate_id": "candidate-a", "score": 80, "position": 1},
        {"candidate_id": "candidate-b", "score": 50, "position": 2},
    ]
    db.q("INSERT INTO rankings VALUES(?,?,?,?,?,?,?,?,?)",
         ("rank-1", "CASE-DEMO", 1, "CONFIRMED", db.dumps(ranking_payload), "U-REC", "U-REC", db.now(), db.now()))
    db.q("INSERT INTO shortlisted_candidates VALUES(?,?,?)", ("CASE-DEMO", 1, "candidate-a"))
    add_case("CASE-HIDDEN", member=None)
    add_candidate("secret-candidate", "CASE-HIDDEN")

    response = client.get("/api/candidates?case_id=CASE-DEMO&sort=pseudonym&order=asc&limit=1",
                          headers=auth())
    assert response.status_code == 200
    result = response.json()
    assert result["total"] == 2 and len(result["items"]) == 1
    assert result["items"][0]["id"] == "candidate-a"
    assert result["items"][0]["display_name"] == "Jordan Private"
    assert "private@example.invalid" not in response.text and "secret-candidate" not in response.text
    unshortlisted = client.get("/api/candidates?shortlisted=false", headers=auth()).json()
    assert unshortlisted["total"] == 1 and "display_name" not in unshortlisted["items"][0]
    assert client.get("/api/candidates?search=secret", headers=auth()).json()["total"] == 0
    assert client.get("/api/candidates?finding_type=HIDDEN_TEXT", headers=auth()).json()["total"] == 1
    assert client.get("/api/candidates?sort=created_at&sort=pseudonym", headers=auth()).status_code == 422
    shortlisted = client.get("/api/candidates?shortlisted=true&sort=score&order=desc", headers=auth()).json()
    assert shortlisted["total"] == 1
    assert shortlisted["items"][0]["display_name"] == "Jordan Private"
    assert shortlisted["items"][0]["score"] == 80
    assert client.get("/api/candidates?case_id=CASE-HIDDEN", headers=auth()).status_code == 404
    assert client.get("/api/candidates?sort=contact_email", headers=auth()).status_code == 422


def test_compare_analytics_and_outbox_follow_case_membership(client):
    add_candidate("compare-1")
    add_candidate("compare-2")
    add_document("compare-1")
    proposal_id = "proposal-compare"
    db.q("INSERT INTO proposals VALUES(?,?,?,?,?,?,?,?,?,?)",
         (proposal_id, "CASE-DEMO", "compare-1", "interview_invite", "{}", "b" * 64,
          "U-REC", "EXECUTED", db.now(), db.now()))
    db.q("INSERT INTO outbox VALUES(?,?,?,?,?,?,?)",
         ("outbox-compare", proposal_id, "CASE-DEMO", '{"recipient":"private@example.invalid"}',
          "SANDBOX_ONLY", "", db.now()))
    add_case("CASE-HIDDEN", member=None)
    add_candidate("secret", "CASE-HIDDEN")
    compared = client.get("/api/candidates/compare?candidate_ids=compare-1,compare-2", headers=auth())
    assert compared.status_code == 200
    assert [row["pseudonym"] for row in compared.json()["candidates"]] == ["compare-1", "compare-2"]
    assert "Private name" not in compared.text and "private@example.invalid" not in compared.text
    assert client.get("/api/candidates/compare?candidate_ids=compare-1,secret", headers=auth()).status_code == 404
    assert client.get("/api/candidates/compare?candidate_ids=compare-1", headers=auth()).status_code == 422

    analytics = client.get("/api/cases/CASE-DEMO/analytics", headers=auth()).json()
    assert analytics["funnel"][0] == {"stage": "Candidates", "count": 2}
    assert analytics["funnel"][1] == {"stage": "CVs uploaded", "count": 1}
    assert analytics["findings_by_type"] == [{"type": "HIDDEN_TEXT", "count": 1}]
    assert analytics["time_to_shortlist_seconds"] is None
    assert client.get("/api/cases/CASE-HIDDEN/analytics", headers=auth()).status_code == 404
    outbox = client.get("/api/workspace/outbox?case_id=CASE-DEMO", headers=auth()).json()
    assert outbox["items"][0]["delivery_status"] == "SANDBOX_ONLY"
    assert outbox["items"][0]["pseudonym"] == "compare-1"
    assert "private@example.invalid" not in str(outbox)
    assert client.get("/api/workspace/outbox?case_id=CASE-HIDDEN", headers=auth()).status_code == 404
    assert client.get("/api/workspace/outbox?unknown=x", headers=auth()).status_code == 422


def test_scoped_ledger_chain_and_signed_export(client):
    add_case("CASE-HIDDEN", member=None)
    ledger.record("U-REC", "CASE_VISIBLE_EVENT", "CASE-DEMO", "visible", {"safe": True})
    ledger.record("U-REC", "CASE_SECRET_EVENT", "CASE-HIDDEN", "secret", {"safe": True})

    scoped = client.get("/api/audit/ledger", headers=auth()).json()
    assert scoped["complete_chain_visible"] is False
    assert all(event["case_id"] == "CASE-DEMO" for event in scoped["events"])
    assert all({"prev_hash", "hash", "mac"} <= event.keys() for event in scoped["events"])
    assert "CASE_SECRET_EVENT" not in str(scoped)

    export = client.get("/api/audit/export", headers=auth()).json()
    payload = {key: value for key, value in export.items()
               if key not in {"signature", "signature_algorithm"}}
    expected = hmac.new(config.LEDGER_KEY.encode(), canonical(payload).encode(), hashlib.sha256).hexdigest()
    assert export["signature_algorithm"] == "HMAC-SHA256"
    assert hmac.compare_digest(export["signature"], expected)
    assert export["complete_chain"] is False
    assert "CASE_SECRET_EVENT" not in str(export)

    global_ledger = client.get("/api/audit/ledger", headers=auth("U-AUD")).json()
    assert global_ledger["complete_chain_visible"] is True
    assert any(event["type"] == "CASE_SECRET_EVENT" for event in global_ledger["events"])
    assert client.get("/api/audit/ledger?case_id=CASE-HIDDEN", headers=auth()).status_code == 404


def test_admin_user_and_policy_management(client):
    assert client.get("/api/admin/users", headers=auth()).status_code == 403
    admin = auth("U-ADM")
    users = client.get("/api/admin/users", headers=admin)
    assert users.status_code == 200 and all("pw_hash" not in user for user in users.json())
    invalid_email = client.post("/api/admin/users", headers=admin,
                                json={"email": "not an email", "name": "Bad", "role": "recruiter",
                                      "password": "long-enough-password"})
    assert invalid_email.status_code == 422

    created = client.post("/api/admin/users", headers=admin,
                          json={"email": "new.person@example.invalid", "name": "New Person",
                                "role": "recruiter", "password": "long-enough-password"})
    assert created.status_code == 201 and "password" not in created.json()
    user_id = created.json()["id"]
    duplicate = client.post("/api/admin/users", headers=admin,
                            json={"email": "new.person@example.invalid", "name": "Duplicate",
                                  "role": "auditor", "password": "long-enough-password"})
    assert duplicate.status_code == 409
    changed = client.patch(f"/api/admin/users/{user_id}/role", headers=admin, json={"role": "auditor"})
    assert changed.status_code == 200 and changed.json()["role"] == "auditor"
    assert client.patch("/api/admin/users/U-ADM/role", headers=admin, json={"role": "recruiter"}).status_code == 409

    current = client.get("/api/admin/policy", headers=admin).json()
    assert current == {"approval_ttl_minutes": config.APPROVAL_MINUTES, "review_weight_threshold": 30}
    updated = client.put("/api/admin/policy", headers=admin,
                         json={"approval_ttl_minutes": 25, "review_weight_threshold": 40})
    assert updated.status_code == 200
    assert client.get("/api/meta").json()["approval_minutes"] == 25
    borderline = ranking.rank(
        [{"id": "criterion", "label": "Python", "weight": 35}],
        [{"id": "candidate", "pseudonym": "Candidate 001", "finding_count": 0,
          "evidence": [{"criterion_id": "criterion", "status": "NEEDS_REVIEW"}]}])
    assert "BORDERLINE_REVIEW" not in borderline[0]["flags"]

    add_candidate("policy-candidate")
    db.q("INSERT INTO rankings VALUES(?,?,?,?,?,?,?,?,?)",
         ("rank-policy", "CASE-DEMO", 1, "CONFIRMED",
          db.dumps([{"candidate_id": "policy-candidate", "score": 50, "position": 1}]),
          "U-REC", "U-REC", db.now(), db.now()))
    db.q("INSERT INTO shortlisted_candidates VALUES(?,?,?)",
         ("CASE-DEMO", 1, "policy-candidate"))
    proposal = client.post("/api/cases/CASE-DEMO/proposals", headers=auth(),
                           json={"candidate_id": "policy-candidate"})
    assert proposal.status_code == 201
    approved = client.post(f"/api/proposals/{proposal.json()['id']}/approve",
                           headers=auth("U-MGR"), json={})
    expiry = datetime.fromisoformat(approved.json()["approval"]["expires_at"].replace("Z", "+00:00"))
    assert expiry > datetime.now(timezone.utc) + timedelta(minutes=20)
    assert client.put("/api/admin/policy", headers=admin, json={"approval_ttl_minutes": 0}).status_code == 422
    assert client.put("/api/admin/policy", headers=auth(), json={"review_weight_threshold": 5}).status_code == 403
    assert any(event["type"] == "POLICY_UPDATED" for event in client.get("/api/ledger", headers=admin).json())


def test_spa_fallback_never_handles_api_or_asset_paths(client):
    route = client.get("/cases/CASE-DEMO", headers=auth())
    assert route.status_code == 200 and "<html" in route.text.lower()
    api_404 = client.get("/api/route-that-does-not-exist", headers=auth())
    assert api_404.status_code == 404 and api_404.json()["error"]["code"] == "NOT_FOUND"
    api_root = client.get("/api")
    assert api_root.status_code == 404 and "html" not in api_root.text.lower()
    assert client.get("/missing.js").status_code == 404
