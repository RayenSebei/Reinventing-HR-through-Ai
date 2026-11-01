"""RB-14 config validation, WA-02 demo credentials, and FX31 lint of the n8n delivery workflow.

The n8n checks are static: they read n8n/vouch-deliver.workflow.json. Node types, parameter
names and typeVersions were checked against the official n8n repository
(github.com/n8n-io/n8n, packages/nodes-base) — see docs/plan/N8N_VERIFICATION.md.
"""
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("VOUCH_DATA_DIR", tempfile.mkdtemp(prefix="vouch-cfg-tests-"))

import pytest  # noqa: E402

from app import config  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / "n8n" / "vouch-deliver.workflow.json"

# type -> typeVersions that exist in the official source (n8n-io/n8n, checked 2026-11-01)
OFFICIAL = {
    "n8n-nodes-base.webhook": {1, 1.1, 2, 2.1, 2.2},
    "n8n-nodes-base.crypto": {1, 2},
    "n8n-nodes-base.if": {1, 2, 2.1, 2.2, 2.3, 2.4},
    "n8n-nodes-base.emailSend": {1, 2, 2.1},
    "n8n-nodes-base.respondToWebhook": {1, 1.1, 1.2, 1.3, 1.4, 1.5},
}


# --- RB-14: fail fast on unsafe or incomplete settings --------------------------------------
@pytest.mark.parametrize("env,problem", [
    ({"VOUCH_OUTBOUND_MODE": "loud"}, "VOUCH_OUTBOUND_MODE"),
    ({"VOUCH_OUTBOUND_MODE": "live"}, "VOUCH_N8N_WEBHOOK_URL"),
    ({"VOUCH_OUTBOUND_MODE": "live", "VOUCH_N8N_WEBHOOK_URL": "https://n8n.example.invalid/w"}, "VOUCH_N8N_HMAC_SECRET"),
    ({"VOUCH_OUTBOUND_MODE": "live", "VOUCH_N8N_WEBHOOK_URL": "https://n8n.example.invalid/w",
      "VOUCH_N8N_HMAC_SECRET": "short"}, "VOUCH_N8N_HMAC_SECRET"),
    ({"VOUCH_OUTBOUND_MODE": "live", "VOUCH_N8N_WEBHOOK_URL": "https://n8n.example.invalid/w",
      "VOUCH_N8N_HMAC_SECRET": "x" * 32, "VOUCH_DEMO_MODE": "1"}, "VOUCH_DEMO_MODE"),
    ({"VOUCH_MODEL": "openai"}, "VOUCH_OPENAI_API_KEY"),
    ({"VOUCH_REVIEW_TOP_N": "0"}, "VOUCH_REVIEW_TOP_N"),
])
def test_bad_settings_are_refused(env, problem):
    problems = config.validate(env)
    assert any(problem in p for p in problems), problems


def test_good_settings_pass():
    assert config.validate({}) == []
    assert config.validate({"VOUCH_OUTBOUND_MODE": "live", "VOUCH_N8N_WEBHOOK_URL": "https://n8n.example.invalid/w",
                            "VOUCH_N8N_HMAC_SECRET": "x" * 32}) == []


def test_problems_never_print_secret_values():
    problems = config.validate({"VOUCH_OUTBOUND_MODE": "live", "VOUCH_N8N_WEBHOOK_URL": "https://n8n.example.invalid/w",
                                "VOUCH_N8N_HMAC_SECRET": "tiny-SECRET-canary"})
    assert problems and not any("SECRET-canary" in p for p in problems)


def test_default_outbound_mode_is_sink():
    assert config.validate({}) == [] and config.outbound_mode_from({}) == "sink"


# --- WA-02: no known password unless demo mode is explicit ----------------------------------
def test_seed_password_is_random_without_demo_flag(monkeypatch):
    from app import seed as seedmod
    monkeypatch.delenv("VOUCH_DEMO_MODE", raising=False)
    msg = seedmod.seed()
    assert "demo1234" not in msg
    from app import db
    from app.security import check_password
    assert not check_password("demo1234", db.one("SELECT pw_hash FROM users WHERE id='U-REC'")["pw_hash"])


def test_seed_uses_demo_password_only_with_flag(monkeypatch):
    from app import db, seed as seedmod
    from app.security import check_password
    monkeypatch.setenv("VOUCH_DEMO_MODE", "1")
    seedmod.seed()
    assert check_password("demo1234", db.one("SELECT pw_hash FROM users WHERE id='U-REC'")["pw_hash"])


# --- FX31 / R25: the n8n workflow uses official nodes and sends exactly what was approved -------
@pytest.fixture(scope="module")
def wf():
    return json.loads(WORKFLOW.read_text(encoding="utf-8"))


def test_every_node_is_an_official_type_and_version(wf):
    for n in wf["nodes"]:
        assert n["type"] in OFFICIAL, f"{n['name']}: {n['type']} is not in the verified list"
        assert n["typeVersion"] in OFFICIAL[n["type"]], f"{n['name']}: typeVersion {n['typeVersion']}"


def _send(wf):
    return [n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.emailSend"]


def test_one_send_node_with_no_cc_bcc_and_no_wait_operation(wf):
    sends = _send(wf)
    assert len(sends) == 1
    p = sends[0]["parameters"]
    assert p.get("operation", "send") == "send"           # never "Send and Wait for Response"
    opts = p.get("options", {})
    assert "ccEmail" not in opts and "bccEmail" not in opts


def test_n8n_does_not_append_text_the_manager_never_approved(wf):
    # emailSend >= 2.1 appends an n8n attribution line unless appendAttribution is false
    # (packages/nodes-base/nodes/EmailSend/v2/send.operation.ts).
    opts = _send(wf)[0]["parameters"].get("options", {})
    assert opts.get("appendAttribution") is False


def test_signature_comparison_does_not_compare_raw_signatures(wf):
    """The If node's equality is not constant-time, so it must compare HMACs of the two
    signatures (double HMAC), never the raw computed signature against the header."""
    ifs = [n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.if"]
    assert len(ifs) == 1
    blob = json.dumps(ifs[0]["parameters"])
    assert "x-vouch-signature" not in blob.lower()
    hmacs = [n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.crypto" and n["parameters"].get("action") == "hmac"]
    assert len(hmacs) == 3


def test_send_happens_only_after_the_signature_check(wf):
    conns = wf["connections"]
    send = _send(wf)[0]["name"]
    if_name = [n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.if"][0]["name"]
    true_branch = [c["node"] for c in conns[if_name]["main"][0]]
    false_branch = [c["node"] for c in conns[if_name]["main"][1]]
    assert send in true_branch and send not in false_branch
    upstream = {src for src, v in conns.items() for outs in v["main"] for c in outs if c["node"] == send}
    assert upstream == {if_name}
