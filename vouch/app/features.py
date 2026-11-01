"""Feature switches for the HR assistants (FEAT_<NAME>_MODE = off|on, default on)."""
from __future__ import annotations

from . import config
from .errors import ApiError


def require(name: str) -> None:
    if config.feature_mode(name) != "on":
        raise ApiError(404, "FEATURE_OFF", f"This feature is switched off (FEAT_{name.upper()}_MODE).")


def enabled(name: str) -> bool:
    return config.feature_mode(name) == "on"
