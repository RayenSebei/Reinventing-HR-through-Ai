"""Regression contracts for the read-only dashboard; uses an isolated SQLite DB."""
import os
import tempfile
from pathlib import Path

os.environ.setdefault("VOUCH_DATA_DIR", tempfile.mkdtemp(prefix="vouch-dashboard-tests-"))

import pytest
from starlette.testclient import TestClient

from app import db, dashboard, ledger
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
    assert all(e["case_id"] == "CASE-DEMO" for e in member["recent_events"])
    assert get(client, suffix="?case_id=SECRET").status_code == 404
    for uid in ("U-ADM", "U-AUD"):
        elevated = get(client, uid).json()
        assert elevated["kpis"]["cases"] == 2
        assert elevated["kpis"]["cvs_analysed"] == elevated["kpis"]["gateway_refusals"] == 1
        assert elevated["alerts_by_type"][0]["count"] == 1
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
