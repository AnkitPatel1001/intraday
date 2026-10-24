"""Application configuration from environment variables."""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass, field
from functools import lru_cache


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _env_float(key: str, default: float) -> float:
    try:
        return float(_env(key, str(default)))
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


def _env_bool(key: str, default: bool) -> bool:
    v = _env(key, "").lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")


def _parse_origins(raw: str, default: list[str]) -> list[str]:
    """Parse BACKEND_CORS_ORIGINS as JSON list. Falls back to default on garbage."""
    try:
        parsed = json.loads(raw)
    except ValueError:
        return list(default)
    if not isinstance(parsed, list):
        return list(default)
    origins = [o.strip() for o in parsed if isinstance(o, str) and o.strip()]
    return origins or list(default)


@dataclass
class Settings:
    # App
    app_env: str = field(default_factory=lambda: _env("APP_ENV", "development"))
    app_debug: bool = field(default_factory=lambda: _env_bool("APP_DEBUG", False))
    app_secret_key: str = field(
        default_factory=lambda: _env("APP_SECRET_KEY", "") or secrets.token_hex(32)
    )

    # Data
    data_provider: str = field(default_factory=lambda: _env("DATA_PROVIDER", "demo"))
    yahoo_enabled: bool = field(default_factory=lambda: _env_bool("YAHOO_ENABLED", True))

    # Backend
    backend_host: str = field(default_factory=lambda: _env("BACKEND_HOST", "0.0.0.0"))
    backend_port: int = field(default_factory=lambda: _env_int("BACKEND_PORT", 8000))
    cors_origins: list[str] = field(
        default_factory=lambda: _parse_origins(
            _env("BACKEND_CORS_ORIGINS", '["http://localhost:3000"]'),
            ["http://localhost:3000"],
        )
    )

    # Risk defaults (INR)
    default_capital: float = field(default_factory=lambda: _env_float("DEFAULT_CAPITAL", 500000))
    default_risk_per_trade_pct: float = field(
        default_factory=lambda: _env_float("DEFAULT_RISK_PER_TRADE_PCT", 1.0)
    )
    default_max_daily_loss_pct: float = field(
        default_factory=lambda: _env_float("DEFAULT_MAX_DAILY_LOSS_PCT", 3.0)
    )
    default_max_positions: int = field(
        default_factory=lambda: _env_int("DEFAULT_MAX_POSITIONS", 5)
    )
    default_min_risk_reward: float = field(
        default_factory=lambda: _env_float("DEFAULT_MIN_RISK_REWARD", 1.5)
    )

    # Security
    auth_enabled: bool = field(default_factory=lambda: _env_bool("AUTH_ENABLED", True))
    rate_limit_per_minute: int = field(
        default_factory=lambda: _env_int("RATE_LIMIT_REQUESTS_PER_MINUTE", 60)
    )
    session_timeout_hours: int = field(
        default_factory=lambda: _env_int("SESSION_TIMEOUT_HOURS", 24)
    )

    # Paper trading
    paper_trading_default: bool = True  # ALWAYS True. Live requires explicit override.

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
