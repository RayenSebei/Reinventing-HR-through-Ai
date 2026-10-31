#!/usr/bin/env python3
"""SENTINEL HR runner: executes the 24 scenarios in sentinel/scenarios/ against Vouch's
PUBLIC API only. No database access. Outcomes follow sentinel/documentation/
evaluation_methodology.md: PASS / FAIL / BLOCKED / ERROR. Blocked is never a pass.

Usage
  python sentinel_hr/runner.py --spawn            # start an isolated Vouch (test mode) and attack it
  python sentinel_hr/runner.py --base http://127.0.0.1:8000   # attack a running test-mode instance
  python sentinel_hr/runner.py --spawn --only PI-001,AP-003

The isolated instance uses a temporary database, so demo data is never touched.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import scenarios_hr  # noqa: E402

REPORTS = HERE / "reports"
SEVERITY_ORDER = ["critical", "high", "medium", "low"]


def load_library() -> dict[str, dict]:
    lib = {}
    for f in sorted((REPO / "sentinel" / "scenarios").glob("*/scenarios.yaml")):
        for s in yaml.safe_load(f.read_text(encoding="utf-8"))["scenarios"]:
            lib[s["id"]] = s
    return lib


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def spawn() -> tuple[subprocess.Popen, str, str]:
    port = free_port()
    data = tempfile.mkdtemp(prefix="vouch-sentinel-")
    env = {**os.environ, "VOUCH_TEST_MODE": "1", "VOUCH_MODEL": "stub", "VOUCH_DATA_DIR": data,
           "VOUCH_N8N_WEBHOOK_URL": "", "VOUCH_APPROVAL_MINUTES": "15"}
    proc = subprocess.Popen([sys.executable, "-m", "app", "--port", str(port)], cwd=str(REPO / "vouch"), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if requests.get(base + "/api/meta", timeout=1).ok:
                return proc, base, data
        except requests.RequestException:
            pass
        time.sleep(0.2)
    proc.kill()
    raise SystemExit("Could not start the isolated Vouch instance.")


def run(base: str, only: set[str] | None) -> dict:
    lib = load_library()
    meta = requests.get(base + "/api/meta", timeout=5).json()
    if not meta.get("test_mode"):
        raise SystemExit("Target is not in test mode (VOUCH_TEST_MODE=1). Refusing to reset its data.")
    results = []
    for sid, scen in lib.items():
        if only and sid not in only:
            continue
        fn = scenarios_hr.SCENARIOS.get(sid)
        t0 = time.time()
        if fn is None:
            res = {"outcome": "BLOCKED", "assertions": [], "reason": "No executable mapping for this scenario."}
        else:
            ctx = scenarios_hr.Ctx(base)
            try:
                res = fn(ctx)
            except scenarios_hr.Blocked as b:
                res = {"outcome": "BLOCKED", "assertions": ctx.assertions, "reason": str(b)}
            except Exception as e:
                res = {"outcome": "ERROR", "assertions": ctx.assertions,
                       "reason": f"{type(e).__name__}: {e}", "trace": traceback.format_exc(limit=3)}
        results.append({"id": sid, "name": scen["name"], "category": scen["category"], "severity": scen["severity"],
                        "duration_ms": int((time.time() - t0) * 1000), **res})
        mark = {"PASS": "PASS ", "FAIL": "FAIL!", "BLOCKED": "BLOCK", "ERROR": "ERROR"}[results[-1]["outcome"]]
        print(f"  {mark}  {sid:7s} [{scen['severity']:8s}] {scen['name']}")
    return summarize(results, meta)


def summarize(results: list[dict], meta: dict) -> dict:
    executed = [r for r in results if r["outcome"] in ("PASS", "FAIL")]
    fails = [r for r in results if r["outcome"] == "FAIL"]
    by_sev = {s: {o: sum(1 for r in results if r["severity"] == s and r["outcome"] == o)
                  for o in ("PASS", "FAIL", "BLOCKED", "ERROR")} for s in SEVERITY_ORDER}
    detections = [r for r in results if r.get("detection") is not None]
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "target": {"model_mode": meta.get("model_mode"), "test_mode": meta.get("test_mode")},
        "totals": {"scenarios": len(results), "executed": len(executed), "pass": len(executed) - len(fails),
                   "fail": len(fails), "blocked": sum(r["outcome"] == "BLOCKED" for r in results),
                   "error": sum(r["outcome"] == "ERROR" for r in results)},
        "attack_success_rate": {"numerator": len(fails), "denominator": len(executed),
                                "value": round(len(fails) / len(executed), 3) if executed else None},
        "critical_failures": [r["id"] for r in fails if r["severity"] == "critical"],
        "by_severity": by_sev,
        "detection": {"scenarios_with_detector": len(detections),
                      "detected": sum(1 for r in detections if r["detection"])},
        "results": results,
        "note": "Self-authored scenarios against synthetic data. Results describe these tests only, not production security.",
    }


def write_reports(report: dict) -> Path:
    REPORTS.mkdir(exist_ok=True)
    stamp = report["generated_at"].replace(":", "").replace("-", "")
    (REPORTS / f"run-{stamp}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (REPORTS / "latest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# SENTINEL HR run", "", f"Generated: {report['generated_at']} · model mode: {report['target']['model_mode']}", "",
             "| Total | Executed | Pass | Fail | Blocked | Error | Attack success rate |", "|---|---|---|---|---|---|---|",
             "| {scenarios} | {executed} | {pass} | {fail} | {blocked} | {error} | ".format(**report["totals"])
             + f"{report['attack_success_rate']['numerator']}/{report['attack_success_rate']['denominator']} |",
             "", f"Critical failures: {', '.join(report['critical_failures']) or 'none'}", "",
             "| ID | Severity | Outcome | Detection | Scenario |", "|---|---|---|---|---|"]
    for r in report["results"]:
        det = "" if r.get("detection") is None else ("yes" if r["detection"] else "no")
        lines.append(f"| {r['id']} | {r['severity']} | {r['outcome']} | {det} | {r['name']} |")
    lines += ["", report["note"]]
    (REPORTS / "latest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return REPORTS / "latest.md"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", help="URL of a running Vouch in test mode")
    ap.add_argument("--spawn", action="store_true", help="start an isolated Vouch in test mode")
    ap.add_argument("--only", help="comma-separated scenario IDs")
    args = ap.parse_args()
    if not args.base and not args.spawn:
        ap.error("use --spawn or --base")
    proc = None
    try:
        if args.spawn:
            proc, base, _ = spawn()
            print(f"Isolated Vouch started at {base} (test mode, stub model, temporary database)")
        else:
            base = args.base.rstrip("/")
        only = set(args.only.split(",")) if args.only else None
        report = run(base, only)
        md = write_reports(report)
        t = report["totals"]
        print(f"\nExecuted {t['executed']}/{t['scenarios']}: {t['pass']} pass, {t['fail']} fail, "
              f"{t['blocked']} blocked, {t['error']} error. Critical failures: {report['critical_failures'] or 'none'}")
        print(f"Report: {md}")
        sys.exit(1 if report["critical_failures"] or t["error"] else 0)
    finally:
        if proc:
            proc.terminate()


if __name__ == "__main__":
    main()
