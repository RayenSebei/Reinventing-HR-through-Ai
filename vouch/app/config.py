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

for d in (DATA_DIR, ORIGINALS_DIR, REPLAY_DIR):
    d.mkdir(parents=True, exist_ok=True)
