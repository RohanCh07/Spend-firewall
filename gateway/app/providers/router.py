"""Pick the upstream for a model and forward requests.

All three providers expose OpenAI-compatible chat endpoints, so one adapter
covers them; only base URL, key and the max-tokens field name differ.
"""

from dataclasses import dataclass

from app.config import Settings
from app.core.pricing import ModelPrice


@dataclass(frozen=True)
class Upstream:
    provider: str
    base_url: str
    api_key: str | None
    max_tokens_field: str


def provider_for(model: str, price: ModelPrice | None) -> str:
    if price is not None:
        return price.provider
    m = model.lower()
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith("gemini"):
        return "gemini"
    return "openai"


def route(settings: Settings, model: str, price: ModelPrice | None) -> Upstream:
    provider = provider_for(model, price)
    if provider == "anthropic":
        base, key, field = settings.anthropic_base_url, settings.anthropic_api_key, "max_tokens"
    elif provider == "gemini":
        base, key, field = settings.gemini_base_url, settings.gemini_api_key, "max_tokens"
    else:
        base, key, field = settings.openai_base_url, settings.openai_api_key, "max_completion_tokens"
    if settings.upstream_override_base_url:
        base = settings.upstream_override_base_url
    return Upstream(provider, base.rstrip("/"), key, field)
