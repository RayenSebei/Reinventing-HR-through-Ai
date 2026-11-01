"""LLM access layer.

- Providers: "mock" (offline and deterministic, for dev, tests and a demo without
  internet), "openai" (any OpenAI-compatible endpoint: OpenAI, Groq, Mistral,
  Together, Ollama, LM Studio) and "anthropic".
- Temperature is always 0 and prompts are versioned (config.PROMPT_VERSION).
- Replay cache: identical input returns the stored output. This keeps scores
  stable between runs and lets the demo work if the network fails.
- Every call returns JSON validated by the caller. The model never gets tools,
  credentials or database access: it only returns text that our code checks.
"""
import json
import re
import urllib.error
import urllib.request

from . import db
from .config import settings
from .security import sha256


class LLMError(RuntimeError):
    pass


def model_name() -> str:
    if settings.llm_provider == "mock":
        return "mock-deterministic"
    return settings.llm_model or ("gpt-4o-mini" if settings.llm_provider == "openai" else "claude-sonnet-4-5")


def _post(url: str, headers: dict, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=settings.llm_timeout_s) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise LLMError(f"LLM HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise LLMError("LLM unreachable") from exc


def _call_openai(system: str, user: str, max_tokens: int) -> str:
    body = {"model": model_name(), "temperature": 0, "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if "gpt-oss" in model_name():
        body["reasoning_effort"] = "low"
        body["max_tokens"] = max(max_tokens, 3000)
    data = _post(
        settings.llm_base_url.rstrip("/") + "/chat/completions",
        {"Content-Type": "application/json", "Authorization": f"Bearer {settings.llm_api_key}"},
        body,
    )
    return data["choices"][0]["message"]["content"]


def _call_anthropic(system: str, user: str, max_tokens: int) -> str:
    data = _post(
        "https://api.anthropic.com/v1/messages",
        {"Content-Type": "application/json", "x-api-key": settings.llm_api_key,
         "anthropic-version": "2023-06-01"},
        {"model": model_name(), "temperature": 0, "max_tokens": max_tokens, "system": system,
         "messages": [{"role": "user", "content": user}]},
    )
    return "".join(block.get("text", "") for block in data.get("content", []))


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError("LLM did not return JSON")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError("LLM returned invalid JSON") from exc


def complete_json(task: str, system: str, user: str, mock, max_tokens: int = 1200) -> dict:
    """Run one LLM task and return a dict.

    `mock` is a zero-argument function giving the deterministic offline answer.
    It is also used as the safe fallback when the real model fails.
    """
    provider = settings.llm_provider
    if provider == "mock":
        return mock()

    key = sha256("|".join([provider, model_name(), task, system, user]))
    if settings.llm_cache:
        cached = db.one("SELECT output FROM llm_cache WHERE key = ?", (key,))
        if cached:
            return json.loads(cached["output"])

    try:
        raw = _call_openai(system, user, max_tokens) if provider == "openai" else _call_anthropic(system, user, max_tokens)
        result = _extract_json(raw)
    except (LLMError, KeyError, IndexError):
        # Fail safe: deterministic fallback, flagged so HR knows.
        result = mock()
        result["_fallback"] = True
        return result

    if settings.llm_cache:
        conn = db.connect()
        try:
            conn.execute("INSERT OR REPLACE INTO llm_cache (key, output, model, created_at) VALUES (?,?,?,?)",
                         (key, json.dumps(result, ensure_ascii=False), model_name(), db.now()))
        finally:
            conn.close()
    return result
