"""Runtime settings, read from environment variables (see README)."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # vouch/
REPO = ROOT.parent                                      # repository root
DATA_DIR = Path(os.environ.get("VOUCH_DATA_DIR", ROOT / "data"))
DB_PATH = Path(os.environ.get("VOUCH_DB", DATA_DIR / "vouch.db"))
ORIGINALS_DIR = DATA_DIR / "originals"
REPLAY_DIR = DATA_DIR / "replay"

# Signing key for login tokens. A random key per process is safe for a demo;
# set VOUCH_JWT_SECRET to keep sessions across restarts.
JWT_SECRET = os.environ.get("VOUCH_JWT_SECRET") or secrets.token_hex(32)
TOKEN_MINUTES = int(os.environ.get("VOUCH_TOKEN_MINUTES", "480"))

# Approval lifetime (minutes).
APPROVAL_MINUTES = int(os.environ.get("VOUCH_APPROVAL_MINUTES", "15"))

# Test mode enables /api/_test/* (fixture reset). Never enable in production.
TEST_MODE = os.environ.get("VOUCH_TEST_MODE") == "1"
DEMO_MODE = os.environ.get("VOUCH_DEMO_MODE") == "1"

# AI model: "lexicon" (no AI, deterministic), "openai" (any OpenAI-compatible
# chat-completions endpoint), "ollama" (local), "replay" (recorded answers),
# "stub" (test-only scripted answers).
MODEL_MODE = os.environ.get("VOUCH_MODEL", "lexicon")
OPENAI_BASE_URL = os.environ.get("VOUCH_OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_API_KEY = os.environ.get("VOUCH_OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("VOUCH_OPENAI_MODEL", "")
OLLAMA_URL = os.environ.get("VOUCH_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("VOUCH_OLLAMA_MODEL", "qwen3:8b")
MODEL_TIMEOUT = float(os.environ.get("VOUCH_MODEL_TIMEOUT", "60"))

# n8n delivery (optional). When set, the gateway POSTs approved actions here,
# signed with HMAC-SHA256 using N8N_HMAC_SECRET.
N8N_WEBHOOK_URL = os.environ.get("VOUCH_N8N_WEBHOOK_URL", "")
N8N_HMAC_SECRET = os.environ.get("VOUCH_N8N_HMAC_SECRET", "")

# Upload limits.
MAX_UPLOAD_BYTES = int(os.environ.get("VOUCH_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
MAX_PAGES = int(os.environ.get("VOUCH_MAX_PAGES", "10"))
MAX_LIST_LIMIT = 100

# Data retention statement shown in /api/meta and the README.
RETENTION_DAYS = int(os.environ.get("VOUCH_RETENTION_DAYS", "180"))

# Candidate chat interview. The browser countdown is informational; the server
# enforces this limit independently. Set PUBLIC_BASE_URL to the externally
# reachable origin when generating invitation links.
PUBLIC_BASE_URL = os.environ.get("VOUCH_PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
INTERVIEW_MINUTES = int(os.environ.get("VOUCH_INTERVIEW_MINUTES", "20"))
INTERVIEW_INVITE_HOURS = int(os.environ.get("VOUCH_INTERVIEW_INVITE_HOURS", "72"))
INTERVIEW_MAX_ANSWER_CHARS = int(os.environ.get("VOUCH_INTERVIEW_MAX_ANSWER_CHARS", "2000"))
INTERVIEW_RATE_PER_MINUTE = int(os.environ.get("VOUCH_INTERVIEW_RATE_PER_MINUTE", "60"))

for d in (DATA_DIR, ORIGINALS_DIR, REPLAY_DIR):
    d.mkdir(parents=True, exist_ok=True)


def _ledger_key() -> str:
    key = os.environ.get("VOUCH_LEDGER_KEY")
    if key:
        if len(key.encode("utf-8")) < 32:
            raise RuntimeError("VOUCH_LEDGER_KEY must contain at least 32 bytes.")
        return key
    path = DATA_DIR / ".ledger-key"
    try:
        key = secrets.token_hex(32)
        with path.open("x", encoding="ascii") as f:
            f.write(key)
        path.chmod(0o600)
        return key
    except FileExistsError:
        key = path.read_text(encoding="ascii").strip()
        if len(key) < 64:
            raise RuntimeError("The stored ledger key is invalid.")
        return key


LEDGER_KEY = _ledger_key()
