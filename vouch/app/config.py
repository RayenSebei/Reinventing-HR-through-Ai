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

def _int(name: str, default: int) -> int:
    """Lenient read; config.validate() reports bad values with a readable message at startup."""
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


# Global outbound kill switch (HL-07). "disabled": nothing leaves, approved actions are held;
# "sink": recorded in the sandbox outbox only (default, safe); "live": delivered via n8n.
OUTBOUND_MODES = ("disabled", "sink", "live")


def outbound_mode_from(env) -> str:
    return (env.get("VOUCH_OUTBOUND_MODE") or "sink").strip().lower()


OUTBOUND_MODE = outbound_mode_from(os.environ)

# Demo mode (WA-02): only then do seeded users get the documented password.
DEMO = os.environ.get("VOUCH_DEMO") == "1"

# Review gate (HI-03): before confirming a shortlist, the confirming recruiter must have opened
# the top N dossiers and every flagged one, through the API.
REVIEW_TOP_N = _int("VOUCH_REVIEW_TOP_N", 3)

# Delivery retries (RB-07): attempts per outbox row, counting the first one.
MAX_DELIVERY_ATTEMPTS = _int("VOUCH_MAX_DELIVERY_ATTEMPTS", 5)

# Upload limits.
MAX_UPLOAD_BYTES = int(os.environ.get("VOUCH_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
MAX_PAGES = int(os.environ.get("VOUCH_MAX_PAGES", "10"))
MAX_LIST_LIMIT = 100

# Data retention statement shown in /api/meta and the README.
RETENTION_DAYS = int(os.environ.get("VOUCH_RETENTION_DAYS", "180"))

for d in (DATA_DIR, ORIGINALS_DIR, REPLAY_DIR):
    d.mkdir(parents=True, exist_ok=True)


def validate(env) -> list[str]:
    """RB-14: return readable problems with a settings mapping (empty list = OK).
    Messages name the variable, never its value, so secrets are not printed."""
    problems = []
    mode = outbound_mode_from(env)
    if mode not in OUTBOUND_MODES:
        problems.append(f"VOUCH_OUTBOUND_MODE must be one of {', '.join(OUTBOUND_MODES)}.")
    if mode == "live":
        if not env.get("VOUCH_N8N_WEBHOOK_URL"):
            problems.append("VOUCH_OUTBOUND_MODE=live needs VOUCH_N8N_WEBHOOK_URL.")
        if len(env.get("VOUCH_N8N_HMAC_SECRET", "")) < 32:
            problems.append("VOUCH_OUTBOUND_MODE=live needs VOUCH_N8N_HMAC_SECRET (at least 32 characters).")
        if env.get("VOUCH_DEMO") == "1":
            problems.append("VOUCH_DEMO=1 (known demo password) is not allowed with VOUCH_OUTBOUND_MODE=live.")
    model = env.get("VOUCH_MODEL", "lexicon")
    if model not in ("lexicon", "openai", "ollama", "replay", "stub"):
        problems.append("VOUCH_MODEL must be lexicon, openai, ollama, replay or stub.")
    if model == "openai" and not (env.get("VOUCH_OPENAI_API_KEY") and env.get("VOUCH_OPENAI_MODEL")):
        problems.append("VOUCH_MODEL=openai needs VOUCH_OPENAI_API_KEY and VOUCH_OPENAI_MODEL.")
    for name, lo in (("VOUCH_REVIEW_TOP_N", 1), ("VOUCH_MAX_DELIVERY_ATTEMPTS", 1), ("VOUCH_APPROVAL_MINUTES", 1),
                     ("VOUCH_TOKEN_MINUTES", 1), ("VOUCH_MAX_UPLOAD_BYTES", 1), ("VOUCH_MAX_PAGES", 1)):
        raw = env.get(name)
        if raw is None:
            continue
        try:
            ok = int(raw) >= lo
        except ValueError:
            ok = False
        if not ok:
            problems.append(f"{name} must be a whole number >= {lo}.")
    return problems
