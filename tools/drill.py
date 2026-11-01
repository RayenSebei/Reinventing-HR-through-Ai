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
        '        if not row:   # D11: the CV address is only a suggestion; a recruiter must confirm it first\n'
        '            raise conflict("RECIPIENT_NOT_CONFIRMED", "Confirm this candidate\'s email address before proposing an action.")\n',
        '        row = row or {"email": cand["contact_email"]}\n',
        ["tests/test_hitl.py::test_proposal_refused_until_recipient_confirmed"]),
    "recipient re-check at execute (I5)": (
        "app/gateway.py",
        '                        if not confirmed or db.loads(p["payload_json"]).get("recipient") != confirmed["email"]:\n',
        '                        if False:\n',
        ["tests/test_hitl.py::test_execute_refused_when_recipient_differs_from_confirmed",
         "tests/test_invariants.py"]),
    "single-address recipient validation (OB-03)": (
        "app/contacts.py",
        "    if not isinstance(value, str) or len(value) > 254 or not _ADDRESS.fullmatch(value):\n",
        "    if not isinstance(value, str):\n",
        ["tests/test_hitl.py::test_recipient_must_be_one_clean_address"]),
    "server-side review gate on ranking confirm (HI-03)": (
        "app/main.py",
        '    await run_in_threadpool(reviews.enforce_ranking, u, request.path_params["case_id"], request.path_params["version"])\n',
        "",
        ["tests/test_hitl.py::test_another_users_review_does_not_count"]),
    "server-side review gate on explicit shortlist (HI-03)": (
        "app/main.py",
        '    await run_in_threadpool(reviews.enforce_selected, u, request.path_params["case_id"], list(body.candidate_ids))\n',
        "",
        ["tests/test_hitl.py::test_shortlist_of_unopened_candidate_is_refused",
         "tests/test_hitl.py::test_shortlist_confirm_requires_opening_dossiers",
         "tests/test_hitl.py::test_upload_response_is_not_a_review"]),
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
    "approval needs the hash the manager viewed (review P0)": (
        "app/gateway.py",
        '    if decision == "approved" and not viewed_sha256:\n',
        '    if False:\n',
        ["tests/test_review_findings.py::test_approve_requires_the_hash_the_manager_viewed"]),
    "approval refused if content changed since viewed (review P0)": (
        "app/gateway.py",
        '        if viewed_sha256 and not hmac.compare_digest(viewed_sha256, p["payload_sha256"]):\n',
        '        if False:\n',
        ["tests/test_review_findings.py::test_approve_refused_when_content_changed_after_manager_viewed_it"]),
    "subject rejects every control/line-separator char (review P0)": (
        "app/gateway.py",
        '_CONTROL = re.compile(r"[\\x00-\\x1f\\x7f-\\x9f\\u2028\\u2029]")\n',
        '_CONTROL = re.compile(r"[\\r\\n]")\n',
        ["tests/test_review_findings.py::test_subject_rejects_any_line_break_or_control_character"]),
    "login throttle per account AND client (review P1)": (
        "app/main.py",
        '    return f"{email}|{client}"\n',
        '    return email\n',
        ["tests/test_review_findings.py::test_failed_logins_from_one_client_do_not_lock_the_manager_elsewhere"]),
    "extraction redacted for every non-recruiter (review P1)": (
        "app/cases.py",
        '    if user["role"] != "recruiter":          # same rule as page_png: only recruiters see contact details\n',
        '    if user["role"] == "hiring_manager":\n',
        ["tests/test_review_findings.py::test_extraction_is_redacted_for_every_role_except_recruiter"]),
    "page preview size guard (review P1)": (
        "app/documents.py",
        '        w, h = page.get_size()     # what pdfium will actually rasterize\n',
        '        w, h = 1.0, 1.0\n',
        ["tests/test_review_findings.py::test_page_preview_refuses_oversized_pages"]),
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
