from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

import httpx

from .errors import FirewallBlocked, to_blocked


def new_session_id(prefix: str = "s") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def headers(agent_id: str | None = None, session_id: str | None = None, customer_id: str | None = None) -> dict[str, str]:
    """Tagging headers for any HTTP client or SDK that accepts `default_headers` / `extra_headers`."""
    h = {}
    if agent_id:
        h["X-Agent-Id"] = agent_id
    if session_id:
        h["X-Session-Id"] = session_id
    if customer_id:
        h["X-Customer-Id"] = customer_id
    return h


class Firewall:
    def __init__(self, url: str | None = None, api_key: str | None = None, agent_id: str | None = None):
        self.url = (url or os.environ.get("SPENDFIREWALL_URL") or "http://localhost:8080").rstrip("/").removesuffix("/v1")
        self.api_key = api_key or os.environ.get("SPENDFIREWALL_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("Set SPENDFIREWALL_API_KEY or pass api_key")
        self.agent_id = agent_id or os.environ.get("SPENDFIREWALL_AGENT_ID")

    @property
    def base_url(self) -> str:
        return f"{self.url}/v1"

    @contextmanager
    def session(self, session_id: str | None = None, customer_id: str | None = None,
                agent_id: str | None = None) -> Iterator[FirewallSession]:
        yield FirewallSession(self, session_id or new_session_id(), customer_id, agent_id or self.agent_id)

    def admin(self, admin_key: str | None = None) -> AdminClient:
        return AdminClient(self.url, admin_key or self.api_key)


class FirewallSession:
    def __init__(self, fw: Firewall, session_id: str, customer_id: str | None, agent_id: str | None):
        self.fw = fw
        self.session_id = session_id
        self.customer_id = customer_id
        self.agent_id = agent_id

    @property
    def headers(self) -> dict[str, str]:
        return headers(self.agent_id, self.session_id, self.customer_id)

    def openai(self, **kwargs: Any) -> Any:
        """An `openai.OpenAI` client for this session. Firewall blocks raise `FirewallBlocked`."""
        import openai

        class _Client(openai.OpenAI):
            def _make_status_error(self, err_msg: str, *, body: object, response: httpx.Response) -> Any:  # type: ignore[override]
                err = super()._make_status_error(err_msg, body=body, response=response)
                return to_blocked(err) or err

        kwargs.setdefault("max_retries", 2)
        return _Client(base_url=self.fw.base_url, api_key=self.fw.api_key,
                       default_headers={**self.headers, **kwargs.pop("default_headers", {})}, **kwargs)

    def async_openai(self, **kwargs: Any) -> Any:
        import openai

        class _Client(openai.AsyncOpenAI):
            def _make_status_error(self, err_msg: str, *, body: object, response: httpx.Response) -> Any:  # type: ignore[override]
                err = super()._make_status_error(err_msg, body=body, response=response)
                return to_blocked(err) or err

        return _Client(base_url=self.fw.base_url, api_key=self.fw.api_key,
                       default_headers={**self.headers, **kwargs.pop("default_headers", {})}, **kwargs)


class AdminClient:
    """Small sync client for /v1/admin (admin key required)."""

    def __init__(self, url: str, admin_key: str, http: httpx.Client | None = None):
        self.url = url.rstrip("/").removesuffix("/v1")
        self.http = http or httpx.Client(timeout=10)
        self.h = {"authorization": f"Bearer {admin_key}"}

    def _req(self, method: str, path: str, **kw: Any) -> Any:
        r = self.http.request(method, f"{self.url}/v1/admin{path}", headers=self.h, **kw)
        if r.status_code == 204:
            return None
        data = r.json()
        if r.status_code >= 400:
            e = data.get("error", {}) if isinstance(data, dict) else {}
            raise FirewallBlocked(e.get("type", "http_error"), e.get("message", str(data)), r.status_code, e)
        return data

    def kill(self, scope: str, scope_id: str, reason: str = "") -> Any:
        return self._req("POST", "/kill", json={"scope": scope, "scope_id": scope_id, "reason": reason})

    def unkill(self, scope: str, scope_id: str) -> None:
        self._req("DELETE", f"/kill/{scope}/{scope_id}")

    def sessions(self, **params: Any) -> Any:
        return self._req("GET", "/sessions", params=params)

    def summary(self, hours: float = 24) -> Any:
        return self._req("GET", "/usage/summary", params={"hours": hours})

    def policies(self) -> Any:
        return self._req("GET", "/policies")

    def create_policy(self, name: str, scope: str, window: str, limit_usd: float, scope_id: str | None = None) -> Any:
        return self._req("POST", "/policies", json={"name": name, "scope": scope, "window": window,
                                                    "limit_usd": limit_usd, "scope_id": scope_id})

    def sync_policies(self, policy_file: dict[str, Any]) -> Any:
        return self._req("PUT", "/policies", json=policy_file)

    def budgets(self, scope_id: str | None = None) -> Any:
        return self._req("GET", "/budgets", params={"scope_id": scope_id} if scope_id else None)
