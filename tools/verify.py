"""TQ-06: one command that runs every suite and prints one table.

Usage (from the repository root, Windows or Linux):
  python -m tools.verify --fast    Vouch tests (incl. fuzzer at CI size), interview-chat tests, n8n lint
  python -m tools.verify --all     --fast + SENTINEL 24 attacks + protection-removal drill
Writes reports/verify_<UTC date>.md and exits non-zero if anything fails.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable


def _pytest_counts(out: str) -> tuple[int, int]:
    p = re.search(r"(\d+) passed", out)
    f = re.search(r"(\d+) failed", out)
    e = re.search(r"(\d+) error", out)
    return (int(p.group(1)) if p else 0), (int(f.group(1)) if f else 0) + (int(e.group(1)) if e else 0)


def suite(name: str, args: list[str], cwd: Path, parse) -> dict:
    env = {**os.environ, "OPENBLAS_NUM_THREADS": "1"}
    t0 = time.time()
    r = subprocess.run(args, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=1800)
    out = r.stdout + r.stderr
    passed, failed = parse(out)
    ok = r.returncode == 0 and failed == 0
    return {"suite": name, "pass": passed, "fail": failed if not ok or failed else 0, "ok": ok,
            "secs": round(time.time() - t0, 1), "tail": out.strip().splitlines()[-1:] or [""]}


def sentinel_counts(out: str) -> tuple[int, int]:
    m = re.search(r"Executed \d+/\d+: (\d+) pass, (\d+) fail, (\d+) blocked, (\d+) error", out)
    return (int(m.group(1)), int(m.group(2)) + int(m.group(3)) + int(m.group(4))) if m else (0, 1)


def drill_counts(out: str) -> tuple[int, int]:
    m = re.search(r"(\d+)/(\d+) removals turned their tests red", out)
    return (int(m.group(1)), int(m.group(2)) - int(m.group(1))) if m else (0, 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--fast", action="store_true")
    g.add_argument("--all", action="store_true")
    a = ap.parse_args()
    rows = [
        suite("vouch (unit, API, HITL, n8n lint, fuzzer)", [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider",
              "--deselect", "tests/test_sentinel.py::test_all_sentinel_scenarios_pass"], REPO / "vouch", _pytest_counts),
        suite("interview-chat", [PY, "-m", "pytest", "-q", "-p", "no:cacheprovider"], REPO / "interview-chat", _pytest_counts),
    ]
    if a.all:
        rows.append(suite("SENTINEL 24 attack scenarios (stub model)", [PY, str(REPO / "sentinel_hr" / "runner.py"), "--spawn"],
                          REPO, sentinel_counts))
        rows.append(suite("protection-removal drill", [PY, "-m", "tools.drill"], REPO, drill_counts))
    width = max(len(r["suite"]) for r in rows)
    lines = [f"{'suite':{width}} | pass | fail | secs | status", "-" * (width + 30)]
    for r in rows:
        lines.append(f"{r['suite']:{width}} | {r['pass']:4} | {r['fail']:4} | {r['secs']:4} | {'OK' if r['ok'] else 'FAIL'}")
    all_ok = all(r["ok"] for r in rows)
    lines.append(f"\nRESULT: {'ALL GREEN' if all_ok else 'FAILURES'}")
    text = "\n".join(lines)
    print(text)
    out = REPO / "reports"
    out.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (out / f"verify_{stamp}.md").write_text(f"# verify {stamp} ({'--all' if a.all else '--fast'})\n\n```\n{text}\n```\n",
                                            encoding="utf-8")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
