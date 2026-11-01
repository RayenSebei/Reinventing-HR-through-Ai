"""Review finding (P0): after `cp .env.example .env` the signing key was the public placeholder
"change-me", so anyone could forge staff tokens. A known placeholder or a short key must stop the app."""
import pytest

from interview_bot import config


@pytest.mark.parametrize("value", ["change-me", "changeme", "CHANGE_ME", "secret", "your-secret-key", "x" * 31])
def test_placeholder_or_short_secret_is_refused(value):
    with pytest.raises(SystemExit) as e:
        config.check_secret_key(value)
    assert "IB_SECRET_KEY" in str(e.value)


def test_unset_secret_means_random_per_start():
    a, b = config.resolve_secret_key(None), config.resolve_secret_key("")
    assert len(a) >= 32 and a != b


def test_long_random_secret_is_accepted():
    key = "k" * 16 + "9fJ2-pQx81LmZ0aT4rW6uYc3"
    assert config.resolve_secret_key(key) == key


def test_env_example_ships_no_usable_key():
    text = (config.BASE_DIR / ".env.example").read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if l.startswith("IB_SECRET_KEY="))
    assert line.strip() == "IB_SECRET_KEY="
