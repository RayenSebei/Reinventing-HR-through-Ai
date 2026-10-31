"""Unit tests for the security-critical pieces. Run from vouch/:  python -m pytest -q"""
import os
import tempfile
from pathlib import Path

os.environ.setdefault("VOUCH_DATA_DIR", tempfile.mkdtemp(prefix="vouch-test-"))

import pytest  # noqa: E402

from app import db, documents, ledger, ranking  # noqa: E402
from app.canonical import canonical, payload_hash  # noqa: E402
from app.schemas import CriteriaSet, Empty, ProposalEdit  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DS = REPO / "sentinel" / "datasets"
FX = REPO / "sentinel_hr" / "fixtures"


# --- canonical hashing -----------------------------------------------------------
def test_canonical_is_order_independent():
    assert canonical({"b": 1, "a": "x"}) == canonical({"a": "x", "b": 1})
    assert payload_hash({"b": 1, "a": "x"}) == payload_hash({"a": "x", "b": 1})


def test_any_change_changes_the_hash():
    p = {"recipient": "a@example.invalid", "start": "2030-05-01T10:00:00Z"}
    assert payload_hash(p) != payload_hash({**p, "start": "2030-05-01T10:00:01Z"})


def test_canonical_rejects_floats():
    with pytest.raises(ValueError):
        canonical({"x": 1.5})


# --- request hardening ------------------------------------------------------------
def test_unknown_fields_are_rejected():
    with pytest.raises(Exception):
        Empty.model_validate({"role": "hiring_manager"})
    with pytest.raises(Exception):
        ProposalEdit.model_validate({"candidate_id": "CANDIDATE-OTHER"})


def test_weights_must_sum_to_100():
    with pytest.raises(Exception):
        CriteriaSet.model_validate({"criteria": [{"label": "Python", "weight": 60}]})


# --- ledger -------------------------------------------------------------------------
def test_ledger_detects_tampering():
    db.wipe()
    for i in range(3):
        ledger.record("tester", "EVENT", None, f"S{i}", {"i": i})
    assert ledger.verify()["ok"]
    db.q("UPDATE ledger SET body_json=? WHERE seq=2", ('{"i":99}',))
    v = ledger.verify()
    assert not v["ok"] and v["first_bad_seq"] == 2


# --- document security --------------------------------------------------------------
EXPECTED = {
    "clean_cvs/clean_cv.pdf": set(),
    "adversarial_cvs/hidden_text.pdf": {"HIDDEN_TEXT"},          # text render mode 3
    "adversarial_cvs/white_on_white.pdf": {"HIDDEN_TEXT"},
    "adversarial_cvs/suspicious_font_sizes.pdf": {"TINY_FONT", "OVERSIZED_FONT"},
    "adversarial_cvs/keyword_stuffing.pdf": {"KEYWORD_DENSITY"},
    "adversarial_cvs/contradictory_dates.pdf": {"DATE_CONFLICT", "INSTRUCTION_PHRASE"},
    "adversarial_cvs/visible_injection.pdf": {"INSTRUCTION_PHRASE"},
}


@pytest.mark.parametrize("rel,expected", EXPECTED.items())
def test_fixture_findings(rel, expected):
    a = documents.analyse_pdf((DS / rel).read_bytes())
    found = {f["type"] for f in documents.find_findings(a)}
    assert expected <= found
    if not expected:
        assert found == set(), f"false alarm on clean CV: {found}"


def test_hidden_text_never_in_visible_text():
    a = documents.analyse_pdf((DS / "adversarial_cvs/hidden_text.pdf").read_bytes())
    assert "ignore prior rules" not in documents.visible_text(a).lower()
    assert "ignore prior rules" in documents.hidden_text(a).lower()


def test_arabic_reads_in_logical_order():
    a = documents.analyse_pdf((FX / "ar_injection.pdf").read_bytes())
    assert "تجاهل التعليمات" in documents.visible_text(a)
    assert "INSTRUCTION_PHRASE" in {f["type"] for f in documents.find_findings(a)}


def test_off_page_and_metadata_attacks():
    a = documents.analyse_pdf((FX / "off_page.pdf").read_bytes())
    assert "OFF_PAGE" in {f["type"] for f in documents.find_findings(a)}
    m = documents.analyse_pdf((FX / "metadata_injection.pdf").read_bytes())
    assert "METADATA_INSTRUCTION" in {f["type"] for f in documents.find_findings(m)}


def test_rejects_non_pdf():
    with pytest.raises(Exception):
        documents.analyse_pdf(b"hello")


# --- ranking ------------------------------------------------------------------------
def test_ranking_is_deterministic_and_never_rejects():
    crit = [{"id": "c1", "label": "Python", "weight": 60}, {"id": "c2", "label": "Git", "weight": 40}]
    cands = [
        {"id": "x", "pseudonym": "Candidate 002", "finding_count": 0,
         "evidence": [{"criterion_id": "c1", "status": "SOURCED"}, {"criterion_id": "c2", "status": "NOT_FOUND"}]},
        {"id": "y", "pseudonym": "Candidate 001", "finding_count": 2,
         "evidence": [{"criterion_id": "c1", "status": "SOURCED"}, {"criterion_id": "c2", "status": "NOT_FOUND"}]},
    ]
    r1, r2 = ranking.rank(crit, cands), ranking.rank(crit, list(reversed(cands)))
    assert r1 == r2
    assert [r["score"] for r in r1] == [60, 60] and r1[0]["position"] == r1[1]["position"] == 1
    assert "DOCUMENT_FINDINGS" in r1[0]["flags"] and len(r1) == 2   # flagged, not removed
