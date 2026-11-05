from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_PRICING = Path(__file__).resolve().parents[2] / "shared" / "pricing" / "models.json"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "sqlite+aiosqlite:///./spendfirewall.db"
    pricing_path: Path = _REPO_PRICING

    # Bootstrap: on first start, create a "default" tenant with this admin key.
    bootstrap_admin_key: str | None = None

    # Defaults for new tenants
    fail_mode: Literal["open", "closed"] = "closed"
    loop_max_repeats: int = 5
    loop_window_seconds: int = 60

    # When a request has no max_tokens we inject this cap, so the reservation
    # is a true upper bound and a budget can never be overspent.
    default_max_output_tokens: int = 4096
    unknown_model_action: Literal["block", "allow"] = "block"

    # Upstream providers (all spoken to via their OpenAI-compatible endpoints)
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    # Send every provider to one URL (mock provider, local LLM, etc.)
    upstream_override_base_url: str | None = None
    upstream_timeout_seconds: float = 600.0

    # Alerts
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "alerts@spendfirewall.local"

    # Caches on the hot path
    cache_ttl_seconds: float = 5.0
    cors_origins: str = "*"


@lru_cache
def get_settings() -> Settings:
    return Settings()
