"""Shared fixture for the HR-assistant tests: the seeded demo (shortlist, interviews, meetings)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("VOUCH_DATA_DIR", tempfile.mkdtemp(prefix="vouch-assist-tests-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app import config, db  # noqa: E402
from app.main import app  # noqa: E402
from app.security import issue_token  # noqa: E402

CASE = "CASE-DEMO"


def H(uid="U-REC"):
    return {"Authorization": "Bearer " + issue_token(uid)}


@pytest.fixture
def demo(monkeypatch):
    from app.seed import seed_demo
    monkeypatch.setattr(config, "OUTBOUND_MODE", "sink", raising=False)
    monkeypatch.setattr(config, "N8N_WEBHOOK_URL", "")
    monkeypatch.setenv("VOUCH_DEMO_MODE", "1")
    seed_demo()
    with TestClient(app) as c:
        yield c


def shortlisted(c):
    return [x for x in c.get("/api/candidates?case_id=CASE-DEMO&limit=100", headers=H()).json()["items"] if x["shortlisted"]]
