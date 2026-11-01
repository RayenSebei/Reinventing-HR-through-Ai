"""All settings come from environment variables (see .env.example).

Nothing secret is hard-coded. In demo mode a random secret is generated at start,
which means tokens do not survive a restart (that is intended).
"""
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader so we do not need python-dotenv."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")


_PLACEHOLDER_KEYS = {"change-me", "changeme", "change_me", "secret", "your-secret-key", "your_secret_key",
                     "replace-me", "test", "demo", "password"}


def check_secret_key(value: str) -> str:
    """Refuse a known placeholder or a short key: with it, anyone can forge staff tokens."""
    if value.strip().lower() in _PLACEHOLDER_KEYS or len(value) < 32:
        raise SystemExit("IB_SECRET_KEY is a placeholder or shorter than 32 characters, so tokens could be forged. "
                         "Leave it empty (a random key is made at each start) or set a long random value: "
                         "python -c \"import secrets;print(secrets.token_urlsafe(48))\"")
    return value


def resolve_secret_key(value: str | None) -> str:
    return check_secret_key(value) if value else secrets.token_urlsafe(48)


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    db_path: str = field(default_factory=lambda: os.environ.get("IB_DB_PATH", str(BASE_DIR / "interview_bot.db")))
    secret_key: str = field(default_factory=lambda: resolve_secret_key(os.environ.get("IB_SECRET_KEY")))
    public_base_url: str = field(default_factory=lambda: os.environ.get("IB_PUBLIC_BASE_URL", "http://localhost:8000"))

    # LLM: "mock" (offline, deterministic), "openai" (any OpenAI-compatible API:
    # OpenAI, Groq, Mistral, Ollama, LM Studio...), or "anthropic".
    llm_provider: str = field(default_factory=lambda: os.environ.get("IB_LLM_PROVIDER", "mock"))
    llm_model: str = field(default_factory=lambda: os.environ.get("IB_LLM_MODEL", ""))
    llm_api_key: str = field(default_factory=lambda: os.environ.get("IB_LLM_API_KEY", ""))
    llm_base_url: str = field(default_factory=lambda: os.environ.get("IB_LLM_BASE_URL", "https://api.openai.com/v1"))
    llm_timeout_s: int = field(default_factory=lambda: _int("IB_LLM_TIMEOUT_S", 40))
    # Replay cache: identical LLM inputs return the stored output (stable scores + demo survives no network).
    llm_cache: bool = field(default_factory=lambda: os.environ.get("IB_LLM_CACHE", "1") == "1")

    staff_token_ttl_s: int = field(default_factory=lambda: _int("IB_STAFF_TOKEN_TTL_S", 8 * 3600))
    invite_ttl_hours: int = field(default_factory=lambda: _int("IB_INVITE_TTL_HOURS", 72))
    max_upload_bytes: int = field(default_factory=lambda: _int("IB_MAX_UPLOAD_BYTES", 2 * 1024 * 1024))
    max_answer_chars: int = field(default_factory=lambda: _int("IB_MAX_ANSWER_CHARS", 2000))
    max_candidate_messages: int = field(default_factory=lambda: _int("IB_MAX_CANDIDATE_MESSAGES", 30))
    rate_limit_per_minute: int = field(default_factory=lambda: _int("IB_RATE_LIMIT_PER_MINUTE", 20))
    retention_days: int = field(default_factory=lambda: _int("IB_RETENTION_DAYS", 90))
    # Seed demo users/job/candidates on first start. Never enable in production.
    demo_seed: bool = field(default_factory=lambda: os.environ.get("IB_DEMO_SEED", "1") == "1")
    demo_password: str = field(default_factory=lambda: os.environ.get("IB_DEMO_PASSWORD", "demo-pass-2026"))

    # Interview timer: total time the candidate has once the interview starts. When it runs out,
    # the interview ends and the answers given so far are kept for HR. 0 = no limit.
    interview_time_limit_min: int = field(default_factory=lambda: _int("IB_INTERVIEW_TIME_LIMIT_MIN", 20))


settings = Settings()

PROMPT_VERSION = "interview-v1.0"
RUBRIC_VERSION = "rubric-v1.0"
