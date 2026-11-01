"""Regression contracts for the read-only dashboard; uses an isolated SQLite DB."""
import os
import tempfile
from pathlib import Path

os.environ.setdefault("VOUCH_DATA_DIR", tempfile.mkdtemp(prefix="vouch-dashboard-tests-"))

import pytest
from starlette.testclient import TestClient

from app import cases, config, db, dashboard, ledger, retention
from app.canonical import canonical
from app.main import app
from app.seed import seed
from app.security import issue_token


@pytest.fixture
def client():
    seed()
    with TestClient(app) as client:
        yield client


def auth(uid="U-REC"):
    return {"Authorization": "Bearer " + issue_token(uid)}


def get(client, uid="U-REC", suffix=""):
    return client.get("/api/dashboard/overview" + suffix, headers=auth(uid))


def add_case(id, owner="U-REC", member="U-REC"):
    db.q("INSERT INTO cases(id,title,owner_id,created_at) VALUES(?,?,?,?)", (id, id, owner, db.now()))
    if member:
        db.q("INSERT INTO case_members VALUES(?,?)", (id, member))


def add_candidate(id, case_id="CASE-DEMO"):
    db.q("INSERT INTO candidates VALUES(?,?,?,?,?,?)", (id, case_id, id, "Private name", "private@example.invalid", db.now()))
    db.q("INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?,?,?)", ("D" + id, id, case_id, "a" * 64, "private.pdf", "/not-read", 1, "U-REC", "{}", "ANALYSED", db.now()))


def test_authentication_and_strict_queries(client):
    assert client.get("/api/dashboard/overview").status_code == 401
    for suffix in ("?role=auditor", "?limit=100", "?case_id=", "?case_id=CASE-DEMO&case_id=CASE-DEMO"):
        assert get(client, suffix=suffix).status_code == 422
    assert get(client, suffix="?case_id=missing").status_code == 404


def test_membership_scopes_every_projection(client):
    add_case("SECRET", member=None)
    add_candidate("hidden", "SECRET")
    db.q("INSERT INTO findings VALUES(?,?,?,?,?,?,?)", ("f", "Dhidden", "HIDDEN_TEXT", "high", 1, "private excerpt", "[]"))
    ledger.record("U-REC", "EXECUTION_DENIED", "SECRET", "hidden", {})
    ledger.record("system", "ASSURANCE_RUN_STARTED", None, None, {})
    member = get(client).json()
    assert member["kpis"]["cases"] == 1
    assert member["kpis"]["cvs_analysed"] == member["kpis"]["gateway_refusals"] == 0
    assert member["alerts_by_type"] == []
    assert sum(member["activity_trends"]["security_alerts"]) == 0
    assert all(e["case_id"] == "CASE-DEMO" for e in member["recent_events"])
    assert get(client, suffix="?case_id=SECRET").status_code == 404
    for uid in ("U-ADM", "U-AUD"):
        elevated = get(client, uid).json()
        assert elevated["kpis"]["cases"] == 2
        assert elevated["kpis"]["cvs_analysed"] == elevated["kpis"]["gateway_refusals"] == 1
        assert elevated["alerts_by_type"][0]["count"] == 1
        assert sum(elevated["activity_trends"]["security_alerts"]) == 1
        assert get(client, uid, "?case_id=SECRET").status_code == 200
    db.q("DELETE FROM case_members WHERE user_id='U-MGR'")
    manager = get(client, "U-MGR").json()
    assert manager["kpis"]["cases"] == manager["kpis"]["ledger_events"] == 0
    assert manager["recent_events"] == manager["attention"] == []


def test_counts_are_not_capped_at_api_page_size(client):
    for i in range(105):
        add_case(f"case-{i}")
        add_candidate(f"candidate-{i}")
    result = get(client).json()
    assert result["kpis"]["cases"] == 106
    assert result["kpis"]["cvs_analysed"] == 105
    assert result["pipeline"][0]["count"] == 105


def test_findings_exclude_model_fallback_and_do_not_duplicate_documents(client):
    add_candidate("one")
    for i, (kind, severity) in enumerate((("MODEL_FALLBACK", "low"), ("HIDDEN_TEXT", "high"), ("HIDDEN_TEXT", "medium"))):
        db.q("INSERT INTO findings VALUES(?,?,?,?,?,?,?)", (str(i), "Done", kind, severity, 1, "secret", "[]"))
    result = get(client).json()
    assert result["kpis"]["cvs_analysed"] == 1
    assert result["kpis"]["security_alerts"] == 2
    assert result["alerts_by_type"] == [{"type": "HIDDEN_TEXT", "count": 2, "max_severity": "high"}]
    assert "secret" not in str(result) and "private@example.invalid" not in str(result)


def test_effective_approval_states_and_latest_decision(client):
    add_candidate("one")
    for i in range(5):
        db.q("INSERT INTO proposals VALUES(?,?,?,?,?,?,?,?,?,?)", (f"p{i}", "CASE-DEMO", "one", "interview_invite", "{}", "current", "U-REC", "APPROVED", db.now(), db.now()))
    for i, (hash_, expiry, decision) in enumerate((("current", "2099-01-01T00:00:00Z", "approved"), ("old", "2099-01-01T00:00:00Z", "approved"), ("current", "2000-01-01T00:00:00Z", "approved"), ("current", "2099-01-01T00:00:00Z", "rejected"))):
        db.q("INSERT INTO approvals VALUES(?,?,?,?,?,?,?,?,?)", (f"a{i}", f"p{i}", hash_, "U-MGR", decision, "nonce", expiry, None, db.now()))
    result = get(client).json()
    assert result["proposals_by_status"] == {"approved": 1, "changed": 1, "expired": 1, "rejected": 1, "pending": 1, "sent": 0, "used": 0}
    assert result["kpis"]["pending_approval"] == 3
    approvals = [a for a in result["attention"] if a["kind"] == "approval"]
    assert [a["id"] for a in approvals] == ["p0"]
    manager = get(client, "U-MGR").json()
    assert {a["id"] for a in manager["attention"]} == {"p1", "p2", "p4"}
    assert all(a["expires_at"] is None for a in manager["attention"])
    # Same timestamp: rowid breaks the tie, as it does in the gateway.
    db.q("INSERT INTO approvals VALUES(?,?,?,?,?,?,?,?,?)", ("latest", "p0", "current", "U-MGR", "rejected", "nonce2", "2099-01-01T00:00:00Z", None, db.now()))
    assert get(client).json()["proposals_by_status"]["approved"] == 0


def test_shortlist_counts_current_candidates_not_versions(client):
    add_candidate("one")
    for version, status in ((1, "SUPERSEDED"), (2, "CONFIRMED")):
        db.q("INSERT INTO rankings VALUES(?,?,?,?,?,?,?,?,?)", (str(version), "CASE-DEMO", version, status, canonical([{"candidate_id": "one"}]), "U-REC", "U-REC", db.now(), db.now()))
    assert get(client).json()["pipeline"][2]["count"] == 1


def test_endpoint_performs_no_writes_and_is_not_cached(client):
    before = db.connect().total_changes
    response = get(client)
    assert response.status_code == 200
    assert db.connect().total_changes == before
    assert response.headers["cache-control"] == "no-store"
    assert "prev_hash" in response.json()["recent_events"][0]


def test_assurance_reports_its_model_not_the_live_model(client, monkeypatch, tmp_path):
    monkeypatch.setattr(dashboard.config, "REPO", tmp_path)
    assert get(client).json()["assurance"] == {"available": False}
    report = tmp_path / "sentinel_hr" / "reports" / "latest.json"
    report.parent.mkdir(parents=True)
    report.write_text('{"totals":{"pass":7,"scenarios":9,"fail":1,"blocked":0,"error":1},"target":{"model_mode":"stub"},"generated_at":"2026-01-01T00:00:00Z"}')
    assert get(client).json()["assurance"]["model_mode"] == "stub"
    assert get(client).json()["assurance"]["pass"] == 7
    report.write_text('{')
    assert get(client).json()["assurance"] == {"available": False}


def test_csp_keeps_scripts_strict(client):
    response = get(client)
    directives = response.headers["content-security-policy"].split(";")
    scripts = next(d for d in directives if d.strip().startswith("script-src "))
    assert "'self'" in scripts
    assert "unsafe-inline" not in scripts and "unsafe-eval" not in scripts


def test_new_frontend_renders_text_only():
    root = Path(__file__).resolve().parents[1] / "frontend" / "src"
    for file in root.rglob("*"):
        if file.suffix in (".ts", ".tsx", ".js", ".jsx"):
            source = file.read_text(encoding="utf-8")
            assert "dangerouslySetInnerHTML" not in source, file
            assert ".innerHTML" not in source, file


def _case_with_criteria(client, title="Privacy case"):
    response = client.post("/api/cases", headers=auth(),
                           json={"title": title, "manager_id": "U-MGR"})
    assert response.status_code == 201
    case_id = response.json()["id"]
    response = client.put(f"/api/cases/{case_id}/criteria", headers=auth(),
                          json={"criteria": [{"label": "Python experience", "weight": 100}]})
    assert response.status_code == 200
    assert client.post(f"/api/cases/{case_id}/criteria/confirm", headers=auth(), json={}).status_code == 200
    return case_id


def _upload(client, case_id, filename):
    repo = Path(__file__).resolve().parents[2]
    data = (repo / "sentinel_hr" / "fixtures" / filename).read_bytes()
    return client.post(f"/api/cases/{case_id}/candidates", headers=auth(),
                       files={"file": (filename, data, "application/pdf")})


def test_criteria_lock_duplicate_detection_and_explicit_shortlist(client):
    case_id = _case_with_criteria(client)
    first = _upload(client, case_id, "ai004_contact_canary.pdf")
    second = _upload(client, case_id, "fr_clean.pdf")
    assert first.status_code == second.status_code == 201
    cand1, cand2 = first.json()["candidate_id"], second.json()["candidate_id"]

    duplicate = _upload(client, case_id, "ai004_contact_canary.pdf")
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DUPLICATE_DOCUMENT"
    assert duplicate.json()["error"]["candidate_id"] == cand1

    locked = client.put(f"/api/cases/{case_id}/criteria", headers=auth(),
                        json={"criteria": [{"label": "Java", "weight": 100}]})
    assert locked.status_code == 409 and locked.json()["error"]["code"] == "CRITERIA_LOCKED"
    assert "display_name" not in client.get(f"/api/candidates/{cand1}", headers=auth()).json()
    assert all("display_name" not in row for row in
               client.get(f"/api/cases/{case_id}/candidates", headers=auth()).json())

    ranking = client.post(f"/api/cases/{case_id}/ranking", headers=auth(), json={}).json()
    proposal = client.post(f"/api/cases/{case_id}/proposals", headers=auth(), json={"candidate_id": cand2})
    assert proposal.status_code == 409
    assert proposal.json()["error"]["code"] == "SHORTLIST_NOT_CONFIRMED"
    client.get(f"/api/candidates/{cand1}/dossier", headers=auth())   # HI-03: open the dossier first
    shortlisted = client.post(
        f"/api/cases/{case_id}/ranking/{ranking['version']}/shortlist", headers=auth(),
        json={"candidate_ids": [cand1]})
    assert shortlisted.status_code == 200
    assert client.get(f"/api/candidates/{cand1}", headers=auth()).json()["display_name"] == "Taylor Example (fictional)"
    assert "display_name" not in client.get(f"/api/candidates/{cand2}", headers=auth()).json()
    assert client.post(f"/api/cases/{case_id}/proposals", headers=auth(),
                       json={"candidate_id": cand2}).status_code == 409
    contact = client.get(f"/api/candidates/{cand1}/contact", headers=auth()).json()   # D11
    client.post(f"/api/candidates/{cand1}/contact/confirm", headers=auth(),
                json={"email": contact["suggested_email"]})
    assert client.post(f"/api/cases/{case_id}/proposals", headers=auth(),
                       json={"candidate_id": cand1}).status_code == 201


def test_candidate_erasure_preserves_ledger_and_retention_purge(client, monkeypatch):
    case_id = _case_with_criteria(client, "Erasure case")
    response = _upload(client, case_id, "ai004_contact_canary.pdf")
    candidate_id = response.json()["candidate_id"]
    sha = response.json()["document"]["sha256"]
    original = config.ORIGINALS_DIR / f"{sha}.pdf"
    assert original.exists()
    deleted = client.delete(f"/api/candidates/{candidate_id}", headers=auth())
    assert deleted.status_code == 200 and not original.exists()
    assert db.one("SELECT 1 FROM candidates WHERE id=?", (candidate_id,)) is None
    assert any(event["type"] == "DOCUMENT_ERASED" for event in
               client.get(f"/api/ledger?case_id={case_id}", headers=auth("U-AUD")).json())
    assert ledger.verify()["ok"]

    retained_case = _case_with_criteria(client, "Retention case")
    retained = _upload(client, retained_case, "fr_clean.pdf").json()
    db.q("UPDATE candidates SET created_at='2000-01-01T00:00:00Z' WHERE id=?", (retained["candidate_id"],))
    result = retention.purge_expired()
    assert result["deleted"] == 1
    assert db.one("SELECT 1 FROM candidates WHERE id=?", (retained["candidate_id"],)) is None


def test_batch_upload_returns_a_result_for_each_file(client):
    case_id = _case_with_criteria(client, "Batch upload case")
    repo = Path(__file__).resolve().parents[2]
    valid_pdf = (repo / "sentinel_hr" / "fixtures" / "fr_clean.pdf").read_bytes()
    response = client.post(
        f"/api/cases/{case_id}/candidates", headers=auth(),
        files=[("file", ("bad.pdf", b"not a PDF", "application/pdf")),
               ("file", ("good.pdf", valid_pdf, "application/pdf"))])
    assert response.status_code == 207
    results = response.json()
    assert [result["ok"] for result in results] == [False, True]
    assert db.one("SELECT COUNT(*) AS n FROM candidates WHERE case_id=?", (case_id,))["n"] == 1
