"""TQ-03 protection-removal drill: "tests that can fail".

For each protection, copy vouch/ to a temporary folder, remove the protection with an exact text
edit, run the named tests there, and REQUIRE them to fail. If the tests still pass with the
protection removed, they do not prove anything and the drill fails.

Usage (from the repository root):  python -m tools.drill [--only NAME,NAME]
Never touches the real vouch/ folder.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# name -> (file, exact text to remove/replace, replacement, tests that must go red)
DRILL = {
    "recipient confirmation at create (D11)": (
        "app/gateway.py",
        '        raise conflict("RECIPIENT_NOT_CONFIRMED", "Confirm this candidate\'s email address before proposing an action.")\n',
        '        recipient = cand["contact_email"]\n',
        ["tests/test_hitl.py::test_proposal_refused_until_recipient_confirmed"]),
    "recipient re-check at execute (I5)": (
        "app/gateway.py",
        '    if db.loads(p["payload_json"]).get("recipient") != contacts.confirmed_email(p["candidate_id"]):\n',
        '    if False:\n',
        ["tests/test_hitl.py::test_execute_refused_when_recipient_differs_from_confirmed",
         "tests/test_invariants.py"]),
    "single-address recipient validation (OB-03)": (
        "app/contacts.py",
        "    if not isinstance(value, str) or len(value) > 254 or not _ADDRESS.fullmatch(value):\n",
        "    if not isinstance(value, str):\n",
        ["tests/test_hitl.py::test_recipient_must_be_one_clean_address"]),
    "server-side review gate (HI-03)": (
        "app/cases.py",
        "    reviews.enforce(user, db.loads(r[\"payload_json\"]))     # HI-03: server-side review gate\n",
        "",
        ["tests/test_hitl.py::test_shortlist_confirm_requires_opening_dossiers",
         "tests/test_hitl.py::test_another_users_review_does_not_count"]),
    "outbox database trigger (HL-01 backstop)": (
        "app/migrations.py",
        "  SELECT RAISE(ABORT, 'OUTBOX_REQUIRES_APPROVAL');\n",
        "  SELECT 1;\n",
        ["tests/test_hitl.py::test_direct_outbox_insert_refused_by_database"]),
    "kill switch 'disabled' (HL-07)": (
        "app/delivery.py",
        '    if mode == "disabled":\n',
        '    if False:\n',
        ["tests/test_hitl.py::test_kill_switch_disabled_holds_everything"]),
    "never re-send a delivered item (RB-07)": (
        "app/delivery.py",
        '    if row["delivery_status"] in ("DELIVERED", "SANDBOX_ONLY"):\n',
        '    if False:\n',
        ["tests/test_hitl.py::test_retry_after_failure_sends_same_payload_once"]),
    "criteria-change archive + re-evaluation (RB-05)": (
        "app/cases.py",
        '        conn.execute("DELETE FROM evidence_items WHERE candidate_id IN (SELECT id FROM candidates WHERE case_id=?)", (case_id,))\n',
        "",
        ["tests/test_hitl.py::test_criteria_change_after_analysis_keeps_working"]),
    "n8n attribution switched off (HL-04)": (
        "../n8n/vouch-deliver.workflow.json",
        '"appendAttribution": false',
        '"appendAttribution": true',
        ["tests/test_config_and_n8n.py::test_n8n_does_not_append_text_the_manager_never_approved"]),
}


def run(name: str, spec, keep: bool = False) -> tuple[bool, str]:
    rel, old, new, tests = spec
    tmp = Path(tempfile.mkdtemp(prefix="vouch-drill-"))
    try:
        shutil.copytree(REPO / "vouch", tmp / "vouch", ignore=shutil.ignore_patterns("data", "node_modules", "__pycache__", "frontend"))
        shutil.copytree(REPO / "n8n", tmp / "n8n")
        shutil.copytree(REPO / "sentinel", tmp / "sentinel")
        shutil.copytree(REPO / "sentinel_hr", tmp / "sentinel_hr", ignore=shutil.ignore_patterns("reports"))
        target = (tmp / "vouch" / rel).resolve()
        text = target.read_text(encoding="utf-8")
        if text.count(old) != 1:
            return False, f"anchor not found exactly once in {rel} (the drill is out of date)"
        target.write_text(text.replace(old, new), encoding="utf-8")
        env = {**os.environ, "VOUCH_DATA_DIR": str(tmp / "data"), "VOUCH_FUZZ_SEQUENCES": "300"}
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *tests],
                           cwd=str(tmp / "vouch"), env=env, capture_output=True, text=True, timeout=600)
        red = r.returncode != 0
        tail = (r.stdout.strip().splitlines() or [""])[-1]
        return red, tail
    finally:
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    names = [n for n in DRILL if not args.only or any(o.lower() in n.lower() for o in args.only.split(","))]
    failures = 0
    print(f"{'protection removed':48} | tests went red? | last line")
    for n in names:
        red, tail = run(n, DRILL[n])
        failures += not red
        print(f"{n:48} | {'YES' if red else 'NO  <-- PROBLEM':15} | {tail}")
    print(f"\n{len(names) - failures}/{len(names)} removals turned their tests red.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
