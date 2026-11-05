"""The policy engine: decides ALLOW / BLOCK before a call goes upstream.

Order: identity requirements -> kill switch -> loop detection -> budgets.
All Redis work is one atomic Lua call (see storage/redis_store.py).
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from redis.exceptions import RedisError

from app.core.errors import FirewallError
from app.core.identity import Identity
from app.core.pricing import usd
from app.services.tenants import PolicySnap, TenantContext
from app.storage.redis_store import WINDOW_TTL, BudgetSlot, RedisStore, budget_key, kill_key, loop_key

log = logging.getLogger("spendfirewall.engine")
KILL_SCOPES = ("agent", "session", "customer")
_ws = re.compile(r"\s+")


@dataclass
class Reservation:
    amount: int
    slots: list[tuple[PolicySnap, BudgetSlot]] = field(default_factory=list)
    kill_keys: list[str] = field(default_factory=list)
    enforced: bool = True

    @property
    def keys(self) -> list[str]:
        return [s.key for _, s in self.slots]


def _norm(v: Any) -> str:
    if isinstance(v, list):
        v = " ".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in v)
    return _ws.sub(" ", str(v or "")).strip().lower()


def loop_fingerprint(body: dict[str, Any], tail: int = 2) -> str:
    """Hash of model + the last `tail` messages, ignoring volatile ids.

    Agents append history every turn, so the full prompt never repeats; the
    *tail* (last tool call + its result, or the last user turn) does.
    """
    parts: list[Any] = [body.get("model")]
    for m in (body.get("messages") or [])[-tail:]:
        calls = [(c.get("function", {}).get("name"), _norm(c.get("function", {}).get("arguments"))) for c in (m.get("tool_calls") or [])]
        parts.append((m.get("role"), _norm(m.get("content")), calls))
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:32]


def applicable_slots(ctx: TenantContext, ident: Identity, now: float | None = None) -> list[tuple[PolicySnap, BudgetSlot]]:
    out = []
    for p in ctx.policies:
        sid = ctx.tenant.id if p.scope == "tenant" else ident.get(p.scope)
        if sid is None or (p.scope_id is not None and p.scope_id != sid):
            continue
        out.append((p, BudgetSlot(budget_key(ctx.tenant.id, p.id, sid, p.window, now), p.limit_micro, WINDOW_TTL[p.window], sid)))
    return out


def kill_keys_for(ctx: TenantContext, ident: Identity) -> list[str]:
    return [kill_key(ctx.tenant.id, s, ident.get(s)) for s in KILL_SCOPES if ident.get(s)]  # type: ignore[arg-type]


class PolicyEngine:
    def __init__(self, store: RedisStore):
        self.store = store

    async def admit(self, ctx: TenantContext, ident: Identity, body: dict[str, Any], amount: int) -> Reservation:
        t = ctx.tenant
        if t.require_identity and not (ident.agent_id and ident.session_id):
            raise FirewallError(400, "identity_required", "This tenant requires X-Agent-Id and X-Session-Id headers")

        kills = kill_keys_for(ctx, ident)
        loop = None
        if ident.session_id and t.loop_max_repeats > 0:
            loop = (loop_key(t.id, ident.session_id, loop_fingerprint(body)), t.loop_max_repeats, t.loop_window_seconds)
        slots = applicable_slots(ctx, ident)

        try:
            r = await self.store.admit(kills, loop, [s for _, s in slots], amount)
        except (RedisError, OSError) as e:
            if t.fail_mode == "open":
                log.warning("redis unavailable, failing OPEN for tenant %s: %s", t.id, e)
                return Reservation(amount, [], kills, enforced=False)
            log.error("redis unavailable, failing CLOSED for tenant %s: %s", t.id, e)
            raise FirewallError(503, "firewall_unavailable", "Spend firewall state store is unavailable; failing closed", retry=True) from e

        if r.code == 1:
            scope = [s for s in KILL_SCOPES if ident.get(s)][r.index]
            raise FirewallError(
                403,
                "session_killed" if scope == "session" else f"{scope}_killed",
                f"This {scope} was stopped by a kill switch",
                scope=scope,
                scope_id=ident.get(scope),
            )
        if r.code == 2:
            raise FirewallError(
                429,
                "loop_detected",
                f"Same request repeated {r.value} times in {t.loop_window_seconds}s; blocked as a loop",
                repeats=r.value,
                window_seconds=t.loop_window_seconds,
            )
        if r.code == 3:
            p, _ = slots[r.index]
            err = FirewallError(
                402,
                "budget_exceeded",
                f"{p.scope.capitalize()} budget '{p.name}' (${usd(p.limit_micro):.2f}/{p.window}) would be exceeded",
                policy_id=p.id,
                policy=p.name,
                scope=p.scope,
                window=p.window,
                limit_usd=usd(p.limit_micro),
                spent_usd=usd(r.value),
                request_estimate_usd=usd(amount),
            )
            err.blocked_slot = (slots[r.index], r.value)  # type: ignore[attr-defined]
            raise err
        return Reservation(amount, slots, kills)

    async def settle(self, res: Reservation, actual: int) -> list[int]:
        """Replace the reservation with the real cost. Returns new counter values."""
        if not res.enforced or not res.slots:
            return []
        try:
            return await self.store.reconcile(res.keys, actual - res.amount)
        except (RedisError, OSError) as e:
            log.error("reconcile failed (counters keep the reservation, i.e. over-count): %s", e)
            return []
