from __future__ import annotations

from typing import Any

BLOCK_TYPES = frozenset(
    {
        "budget_exceeded",
        "loop_detected",
        "session_killed",
        "agent_killed",
        "customer_killed",
        "identity_required",
        "firewall_unavailable",
    }
)


class FirewallBlocked(Exception):
    """The gateway refused the call. Stop the agent; retrying won't help."""

    def __init__(self, type_: str, message: str, status: int, body: dict[str, Any] | None = None):
        super().__init__(f"{type_}: {message}")
        self.type = type_
        self.message = message
        self.status = status
        self.body = body or {}


def _error_body(err: Any) -> dict[str, Any] | None:
    body = getattr(err, "body", None)
    if isinstance(body, dict):
        return body.get("error", body) if isinstance(body.get("error", body), dict) else None
    return None


def is_firewall_block(err: BaseException) -> bool:
    """True for an `openai.APIStatusError` (or similar) carrying a firewall block type."""
    if isinstance(err, FirewallBlocked):
        return True
    b = _error_body(err)
    return bool(b and b.get("type") in BLOCK_TYPES)


def to_blocked(err: BaseException) -> FirewallBlocked | None:
    if isinstance(err, FirewallBlocked):
        return err
    b = _error_body(err)
    if b and b.get("type") in BLOCK_TYPES:
        return FirewallBlocked(b["type"], b.get("message", ""), getattr(err, "status_code", 0), b)
    return None
