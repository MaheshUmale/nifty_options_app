"""
Centralized configuration loader.
Reads config/settings.yaml and env vars (overrides).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Project root (one level above src/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "settings.yaml"
ENV_PATH = PROJECT_ROOT / ".env"

# Load env first (silently skip if missing)
load_dotenv(ENV_PATH, override=False)


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep-merge override into base (override wins)."""
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: Path | None = None) -> dict[str, Any]:
    path = path or CONFIG_PATH
    with open(path) as f:
        cfg = yaml.safe_load(f)

    # Env overrides for selected top-level keys
    env_overrides = {
        "app": {
            "mode": os.getenv("APP_MODE", cfg["app"]["mode"]),
            "log_level": os.getenv("LOG_LEVEL", cfg["app"]["log_level"]),
        },
        "risk": {
            "max_position_notional": float(
                os.getenv("MAX_POSITION_SIZE", cfg["risk"]["max_position_notional"])
            ),
            "max_daily_loss": float(
                os.getenv("MAX_DAILY_LOSS", cfg["risk"]["max_daily_loss"])
            ),
            "max_drawdown_pct": float(
                os.getenv("MAX_DRAWDOWN_PCT", cfg["risk"]["max_drawdown_pct"])
            ),
        },
    }
    cfg = _deep_merge(cfg, env_overrides)
    cfg["_project_root"] = str(PROJECT_ROOT)
    return cfg


# Singleton-style access
_settings: dict[str, Any] | None = None


def get_settings() -> dict[str, Any]:
    global _settings
    if _settings is None:
        _settings = load_config()
    return _settings


# -----------------------------
# Upstox (TEMP hardcoded token override)
# -----------------------------
# NOTE: Temporary for debugging live mode. Remove/secure later.
HARDCODED_UPSTOX_ACCESS_TOKEN =  'eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI3NkFGMzUiLCJqdGkiOiI2YTIyNWE0OTUyY2JhMjdlNTNiNWNhZDYiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc4MDYzNjIzMywiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzgwNjk2ODAwfQ.Ta_pBqybIL6RB0SrU_GPJPCwkJwTN3d7KbLBniTVems'


def get_upstox_access_token() -> str | None:
    """Return a valid Upstox access token.

    The function first checks for an ``UPSTOX_ACCESS_TOKEN`` environment
    variable (the preferred source for a fresh token). If the variable is not
    present or is empty, it falls back to the temporary hard‑coded token that
    exists in this module (used during debugging). This fallback ensures that
    the live dashboard can still make authenticated requests during
    development without manual token management, preventing the 401 errors the
    user is experiencing.

    Priority:
      1) OS env var ``UPSTOX_ACCESS_TOKEN`` (stripped)
      2) ``HARDCODED_UPSTOX_ACCESS_TOKEN`` defined above
    """
    token = os.getenv("UPSTOX_ACCESS_TOKEN")
    if token:
        return token.strip()
    # Fallback to the temporary hard‑coded token for debugging/development.
    return HARDCODED_UPSTOX_ACCESS_TOKEN


if __name__ == "__main__":
    # Quick smoke test
    import json
    print(json.dumps(load_config(), indent=2, default=str))
