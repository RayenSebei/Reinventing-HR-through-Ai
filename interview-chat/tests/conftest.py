import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from starlette.testclient import TestClient  # noqa: E402

from interview_bot import api, db  # noqa: E402
from interview_bot.config import settings  # noqa: E402
from interview_bot.security import candidate_limiter, login_limiter  # noqa: E402

PASSWORD = "demo-pass-2026"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "test.db"))
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "demo_password", PASSWORD)
    candidate_limiter.reset()
    login_limiter.reset()
    app = api.create_app(seed=True)
    with TestClient(app) as c:
        yield c


def login(client, username):
    r = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def candidate_id_by_file(fragment: str) -> int:
    row = db.one("SELECT id FROM candidates WHERE cv_filename LIKE ?", (f"%{fragment}%",))
    return row["id"]


def invite_and_get_token(client, cid, proposer="sarra", approver="karim"):
    r = client.post(f"/api/candidates/{cid}/invite", headers=login(client, proposer))
    assert r.status_code == 201, r.text
    p = r.json()
    r = client.post(f"/api/proposals/{p['id']}/approve", headers=login(client, approver), json={"payload_hash": p["payload_hash"]})
    assert r.status_code == 200, r.text
    body = db.one("SELECT body FROM outbox ORDER BY id DESC LIMIT 1")["body"]
    return re.search(r"#t=([\w-]+)", body).group(1)
