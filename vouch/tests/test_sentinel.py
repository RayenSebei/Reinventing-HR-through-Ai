"""Runs the full SENTINEL scenario set against an isolated Vouch instance."""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_all_sentinel_scenarios_pass():
    r = subprocess.run([sys.executable, str(REPO / "sentinel_hr" / "runner.py"), "--spawn"],
                       capture_output=True, text=True, timeout=600)
    print(r.stdout[-3000:])
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "0 fail, 0 blocked, 0 error" in r.stdout
