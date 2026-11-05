"""Management API used by the dashboard, the extensions and the SDKs."""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import and_, case, func, select, update

from app.api.deps import admin_ctx
from app.core.errors import FirewallError
from app.core.pricing import micro, usd
from app.services.tenants import TenantContext, generate_key, hash_key
from app.storage.db import AlertLog, ApiKey, KillSwitch, Policy, Tenant, UsageEvent
from app.storage.redis_store import budget_key

router = APIRouter(prefix="/v1/admin", tags=["admin"])

Scope = Literal["tenant", "agent", "session", "customer"]
KillScope = Literal["agent", "session", "customer"]
Window = Literal["total", "minute", "hour", "day", "month"]


# ---------- schemas ----------
class SettingsIn(BaseModel):
    name: str | None = None
    fail_mode: Literal["open", "closed"] | None = None
    loop_max_repeats: int | None = Field(None, ge=0, le=10_000)
    loop_window_seconds: int | None = Field(None, ge=1, le=86_400)
    require_identity: bool | None = None
    slack_webhook_url: HttpUrl | None | Literal[""] = None
    alert_email: str | None = None


class PolicyIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scope: Scope
    scope_id: str | None = Field(None, max_length=128)
    window: Window
    limit_usd: float = Field(gt=0)
    enabled: bool = True


class PolicyPatch(BaseModel):
    name: str | None = None
    limit_usd: float | None = Field(None, gt=0)
    enabled: bool | None = None
    window: Window | None = None


class PolicyFile(BaseModel):
    """Policy-as-code document (spendfirewall.yaml), see shared/policy-schema."""

    version: Literal[1] = 1
    settings: SettingsIn | None = None
    budgets: list[PolicyIn] = []


class KillIn(BaseModel):
    scope: KillScope
    scope_id: str = Field(min_length=1, max_length=128)
    reason: str = ""


class KeyIn(BaseModel):
    name: str = ""
    role: Literal["proxy", "admin"] = "proxy"


def policy_out(p: Policy) -> dict[str, Any]:
    return {
        "id": p.id,
        "name": p.name,
        "scope": p.scope,
        "scope_id": p.scope_id,
        "window": p.window,
        "limit_usd": usd(p.limit_micro),
        "enabled": p.enabled,
        "created_at": p.created_at,
    }


def tenant_out(t: Tenant) -> dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "fail_mode": t.fail_mode,
        "loop_max_repeats": t.loop_max_repeats,
        "loop_window_seconds": t.loop_window_seconds,
        "require_identity": t.require_identity,
        "slack_webhook_url": t.slack_webhook_url,
        "alert_email": t.alert_email,
    }


def _sm(request: Request):  # noqa: ANN202
    return request.app.state.sessionmaker


# ---------- tenant ----------
@router.get("/me")
async def me(request: Request, ctx: TenantContext = Depends(admin_ctx)) -> dict[str, Any]:
    async with _sm(request)() as s:
        t = await s.get(Tenant, ctx.tenant.id)
    return {"tenant": tenant_out(t), "role": ctx.role}


async def _apply_settings(s: Any, tenant_id: str, body: SettingsIn) -> Tenant:
    t = await s.get(Tenant, tenant_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        if k == "slack_webhook_url":
            v = str(v) if v else None
        setattr(t, k, v)
    return t


@router.patch("/settings")
async def patch_settings(body: SettingsIn, request: Request, ctx: TenantContext = Depends(admin_ctx)) -> dict[str, Any]:
    async with _sm(request)() as s:
        t = await _apply_settings(s, ctx.tenant.id, body)
        await s.commit()
    request.app.state.tenants.invalidate(ctx.tenant.id)
    return tenant_out(t)


# ---------- policies ----------
@router.get("/policies")
async def list_policies(request: Request, ctx: TenantContext = Depends(admin_ctx)) -> list[dict[str, Any]]:
    async with _sm(request)() as s:
        ps = (await s.execute(select(Policy).where(Policy.tenant_id == ctx.tenant.id).order_by(Policy.created_at))).scalars()
        return [policy_out(p) for p in ps]


@router.post("/policies", status_code=201)
async def create_policy(body: PolicyIn, request: Request, ctx: TenantContext = Depends(admin_ctx)) -> dict[str, Any]:
    p = Policy(
        tenant_id=ctx.tenant.id,
        name=body.name,
        scope=body.scope,
        scope_id=body.scope_id,
        window=body.window,
        limit_micro=micro(body.limit_usd),
        enabled=body.enabled,
    )
    async with _sm(request)() as s:
        s.add(p)
        await s.commit()
    request.app.state.tenants.invalidate(ctx.tenant.id)
    return policy_out(p)


@router.put("/policies")
async def sync_policies(body: PolicyFile, request: Request, ctx: TenantContext = Depends(admin_ctx)) -> dict[str, Any]:
    """Apply a policy file: budgets matched by name are updated, new ones created, missing ones disabled."""
    created = updated = disabled = 0
    async with _sm(request)() as s:
        if body.settings:
            await _apply_settings(s, ctx.tenant.id, body.settings)
        existing = {p.name: p for p in (await s.execute(select(Policy).where(Policy.tenant_id == ctx.tenant.id))).scalars()}
        seen = set()
        for b in body.budgets:
            seen.add(b.name)
            p = existing.get(b.name)
            if p is None:
                s.add(
                    Policy(
                        tenant_id=ctx.tenant.id,
                        name=b.name,
                        scope=b.scope,
                        scope_id=b.scope_id,
                        window=b.window,
                        limit_micro=micro(b.limit_usd),
                        enabled=b.enabled,
                    )
                )
                created += 1
            else:
                p.scope, p.scope_id, p.window = b.scope, b.scope_id, b.window
                p.limit_micro, p.enabled = micro(b.limit_usd), b.enabled
                updated += 1
        for name, p in existing.items():
            if name not in seen and p.enabled:
                p.enabled = False
                disabled += 1
        await s.commit()
    request.app.state.tenants.invalidate(ctx.tenant.id)
    return {"created": created, "updated": updated, "disabled": disabled}


@router.patch("/policies/{policy_id}")
async def patch_policy(policy_id: str, body: PolicyPatch, request: Request, ctx: TenantContext = Depends(admin_ctx)) -> dict[str, Any]:
    async with _sm(request)() as s:
        p = await s.get(Policy, policy_id)
        if p is None or p.tenant_id != ctx.tenant.id:
            raise FirewallError(404, "not_found", "Policy not found")
        d = body.model_dump(exclude_unset=True)
        if "limit_usd" in d:
            p.limit_micro = micro(d.pop("limit_usd"))
        for k, v in d.items():
            setattr(p, k, v)
        await s.commit()
    request.app.state.tenants.invalidate(ctx.tenant.id)
    return policy_out(p)


@router.delete("/policies/{policy_id}", status_code=204)
async def delete_policy(policy_id: str, request: Request, ctx: TenantContext = Depends(admin_ctx)) -> None:
    async with _sm(request)() as s:
        p = await s.get(Policy, policy_id)
        if p is None or p.tenant_id != ctx.tenant.id:
            raise FirewallError(404, "not_found", "Policy not found")
        await s.delete(p)
        await s.commit()
    request.app.state.tenants.invalidate(ctx.tenant.id)


@router.get("/budgets")
async def budget_status(request: Request, ctx: TenantContext = Depends(admin_ctx), scope_id: str | None = None) -> list[dict[str, Any]]:
    """Live counter for every policy that resolves to one id (tenant scope, a fixed scope_id, or `scope_id` given)."""
    rows = []
    for p in ctx.policies:
        sid = ctx.tenant.id if p.scope == "tenant" else (p.scope_id or scope_id)
        if sid is None:
            continue
        rows.append((p, sid, budget_key(ctx.tenant.id, p.id, sid, p.window)))
    values = await request.app.state.store.get_counters([k for _, _, k in rows])
    return [
        {
            "policy_id": p.id,
            "name": p.name,
            "scope": p.scope,
            "scope_id": sid,
            "window": p.window,
            "limit_usd": usd(p.limit_micro),
            "spent_usd": usd(v),
            "pct": round(100 * v / p.limit_micro, 1),
        }
        for (p, sid, _), v in zip(rows, values)
    ]


# ---------- kill switch ----------
@router.post("/kill", status_code=201)
async def kill(body: KillIn, request: Request, ctx: TenantContext = Depends(admin_ctx)) -> dict[str, Any]:
    await request.app.state.store.kill(ctx.tenant.id, body.scope, body.scope_id, body.reason)
    async with _sm(request)() as s:
        await s.execute(
            update(KillSwitch)
            .where(KillSwitch.tenant_id == ctx.tenant.id, KillSwitch.scope == body.scope, KillSwitch.scope_id == body.scope_id)
            .values(active=False)
        )
        k = KillSwitch(tenant_id=ctx.tenant.id, scope=body.scope, scope_id=body.scope_id, reason=body.reason)
        s.add(k)
        await s.commit()
    return {"id": k.id, "scope": k.scope, "scope_id": k.scope_id, "active": True}


@router.delete("/kill/{scope}/{scope_id}", status_code=204)
async def unkill(scope: KillScope, scope_id: str, request: Request, ctx: TenantContext = Depends(admin_ctx)) -> None:
    await request.app.state.store.unkill(ctx.tenant.id, scope, scope_id)
    async with _sm(request)() as s:
        await s.execute(
            update(KillSwitch).where(KillSwitch.tenant_id == ctx.tenant.id, KillSwitch.scope == scope, KillSwitch.scope_id == scope_id).values(active=False)
        )
        await s.commit()


@router.get("/kills")
async def list_kills(request: Request, ctx: TenantContext = Depends(admin_ctx)) -> list[dict[str, Any]]:
    async with _sm(request)() as s:
        ks = (
            await s.execute(select(KillSwitch).where(KillSwitch.tenant_id == ctx.tenant.id, KillSwitch.active.is_(True)).order_by(KillSwitch.created_at.desc()))
        ).scalars()
        return [{"id": k.id, "scope": k.scope, "scope_id": k.scope_id, "reason": k.reason, "created_at": k.created_at} for k in ks]


# ---------- usage ----------
def _since(hours: float) -> datetime:
    return datetime.now(UTC) - timedelta(hours=hours)


BLOCKED = UsageEvent.decision.notin_(["allowed", "upstream_error"])


@router.get("/sessions")
async def sessions(
    request: Request,
    ctx: TenantContext = Depends(admin_ctx),
    hours: float = Query(24, gt=0, le=24 * 90),
    agent_id: str | None = None,
    limit: int = Query(100, le=1000),
) -> list[dict[str, Any]]:
    q = (
        select(
            UsageEvent.session_id,
            func.max(UsageEvent.agent_id),
            func.max(UsageEvent.customer_id),
            func.min(UsageEvent.ts),
            func.max(UsageEvent.ts),
            func.count(),
            func.sum(case((BLOCKED, 1), else_=0)),
            func.coalesce(func.sum(UsageEvent.cost_micro), 0),
        )
        .where(UsageEvent.tenant_id == ctx.tenant.id, UsageEvent.ts >= _since(hours), UsageEvent.session_id.is_not(None))
        .group_by(UsageEvent.session_id)
        .order_by(func.max(UsageEvent.ts).desc())
        .limit(limit)
    )
    if agent_id:
        q = q.where(UsageEvent.agent_id == agent_id)
    async with _sm(request)() as s:
        rows = (await s.execute(q)).all()
        killed = {
            k
            for (k,) in (
                await s.execute(
                    select(KillSwitch.scope_id).where(KillSwitch.tenant_id == ctx.tenant.id, KillSwitch.scope == "session", KillSwitch.active.is_(True))
                )
            )
        }
    # Live session-budget usage, one MGET for all sessions x session policies
    spol = [p for p in ctx.policies if p.scope == "session"]
    keys = [budget_key(ctx.tenant.id, p.id, r[0], p.window) for r in rows for p in spol]
    vals = await request.app.state.store.get_counters(keys)
    live_cut = datetime.now(UTC) - timedelta(minutes=5)
    out = []
    for i, r in enumerate(rows):
        pct = None
        if spol:
            pct = max(round(100 * vals[i * len(spol) + j] / p.limit_micro, 1) for j, p in enumerate(spol))
        last = r[4] if r[4].tzinfo else r[4].replace(tzinfo=UTC)
        out.append(
            {
                "session_id": r[0],
                "agent_id": r[1],
                "customer_id": r[2],
                "first_seen": r[3],
                "last_seen": r[4],
                "calls": r[5],
                "blocked": int(r[6] or 0),
                "cost_usd": usd(int(r[7])),
                "budget_pct": pct,
                "killed": r[0] in killed,
                "live": last >= live_cut,
            }
        )
    return out


@router.get("/usage/summary")
async def usage_summary(request: Request, ctx: TenantContext = Depends(admin_ctx), hours: float = Query(24, gt=0, le=24 * 90)) -> dict[str, Any]:
    since = _since(hours)
    base = and_(UsageEvent.tenant_id == ctx.tenant.id, UsageEvent.ts >= since)
    cost = func.coalesce(func.sum(UsageEvent.cost_micro), 0)
    dialect = request.app.state.engine_db.dialect.name
    bucket = (
        func.strftime("%Y-%m-%dT%H:00:00Z", UsageEvent.ts)
        if dialect == "sqlite"
        else func.to_char(func.date_trunc("hour", UsageEvent.ts), 'YYYY-MM-DD"T"HH24:00:00"Z"')
    )
    async with _sm(request)() as s:
        tot = (
            await s.execute(
                select(
                    cost,
                    func.count(),
                    func.sum(case((BLOCKED, 1), else_=0)),
                    func.avg(UsageEvent.overhead_ms),
                    func.count(func.distinct(UsageEvent.session_id)),
                ).where(base)
            )
        ).one()

        async def group(col: Any, n: int = 10) -> list[dict[str, Any]]:
            rs = (await s.execute(select(col, cost, func.count()).where(base).group_by(col).order_by(cost.desc()).limit(n))).all()
            return [{"key": k, "cost_usd": usd(int(c)), "calls": n_} for k, c, n_ in rs]

        by_model = await group(UsageEvent.model)
        by_agent = await group(UsageEvent.agent_id)
        by_customer = await group(UsageEvent.customer_id)
        top_sessions = await group(UsageEvent.session_id)
        decisions = (await s.execute(select(UsageEvent.decision, func.count()).where(base).group_by(UsageEvent.decision))).all()
        ts = (await s.execute(select(bucket, cost, func.count(), func.sum(case((BLOCKED, 1), else_=0))).where(base).group_by(bucket).order_by(bucket))).all()
    return {
        "hours": hours,
        "total_cost_usd": usd(int(tot[0])),
        "calls": tot[1],
        "blocked": int(tot[2] or 0),
        "avg_overhead_ms": round(float(tot[3] or 0), 3),
        "sessions": tot[4],
        "by_model": by_model,
        "by_agent": by_agent,
        "by_customer": by_customer,
        "top_sessions": top_sessions,
        "decisions": {d: n for d, n in decisions},
        "timeseries": [{"hour": h, "cost_usd": usd(int(c)), "calls": n, "blocked": int(b or 0)} for h, c, n, b in ts],
    }


@router.get("/events")
async def events(
    request: Request, ctx: TenantContext = Depends(admin_ctx), limit: int = Query(100, le=1000), blocked_only: bool = False, session_id: str | None = None
) -> list[dict[str, Any]]:
    q = select(UsageEvent).where(UsageEvent.tenant_id == ctx.tenant.id).order_by(UsageEvent.id.desc()).limit(limit)
    if blocked_only:
        q = q.where(BLOCKED)
    if session_id:
        q = q.where(UsageEvent.session_id == session_id)
    async with _sm(request)() as s:
        rows = (await s.execute(q)).scalars().all()
    return [
        {
            "id": e.id,
            "ts": e.ts,
            "agent_id": e.agent_id,
            "session_id": e.session_id,
            "customer_id": e.customer_id,
            "model": e.model,
            "provider": e.provider,
            "input_tokens": e.input_tokens,
            "output_tokens": e.output_tokens,
            "cost_usd": usd(e.cost_micro),
            "decision": e.decision,
            "status_code": e.status_code,
            "latency_ms": e.latency_ms,
            "overhead_ms": e.overhead_ms,
            "stream": e.stream,
        }
        for e in rows
    ]


@router.get("/alerts")
async def alerts(request: Request, ctx: TenantContext = Depends(admin_ctx), limit: int = Query(50, le=500)) -> list[dict[str, Any]]:
    async with _sm(request)() as s:
        rows = (
            await s.execute(
                select(AlertLog, Policy.name)
                .join(Policy, Policy.id == AlertLog.policy_id, isouter=True)
                .where(AlertLog.tenant_id == ctx.tenant.id)
                .order_by(AlertLog.id.desc())
                .limit(limit)
            )
        ).all()
    return [
        {
            "id": a.id,
            "policy_id": a.policy_id,
            "policy": name,
            "scope_id": a.scope_id,
            "threshold": a.threshold,
            "spent_usd": usd(a.spent_micro),
            "limit_usd": usd(a.limit_micro),
            "fired_at": a.fired_at,
        }
        for a, name in rows
    ]


# ---------- keys & pricing ----------
@router.get("/keys")
async def list_keys(request: Request, ctx: TenantContext = Depends(admin_ctx)) -> list[dict[str, Any]]:
    async with _sm(request)() as s:
        ks = (await s.execute(select(ApiKey).where(ApiKey.tenant_id == ctx.tenant.id).order_by(ApiKey.created_at))).scalars()
        return [{"id": k.id, "name": k.name, "prefix": k.prefix, "role": k.role, "revoked": k.revoked, "created_at": k.created_at} for k in ks]


@router.post("/keys", status_code=201)
async def create_key(body: KeyIn, request: Request, ctx: TenantContext = Depends(admin_ctx)) -> dict[str, Any]:
    raw = generate_key()
    async with _sm(request)() as s:
        k = ApiKey(tenant_id=ctx.tenant.id, name=body.name, key_hash=hash_key(raw), prefix=raw[:10], role=body.role)
        s.add(k)
        await s.commit()
    return {"id": k.id, "key": raw, "role": k.role, "name": k.name, "note": "Store this key now; it is not shown again."}


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_key(key_id: str, request: Request, ctx: TenantContext = Depends(admin_ctx)) -> None:
    async with _sm(request)() as s:
        k = await s.get(ApiKey, key_id)
        if k is None or k.tenant_id != ctx.tenant.id:
            raise FirewallError(404, "not_found", "Key not found")
        k.revoked = True
        await s.commit()
    request.app.state.tenants.invalidate()


@router.get("/pricing")
async def pricing(request: Request, ctx: TenantContext = Depends(admin_ctx)) -> list[dict[str, Any]]:
    return [{"model": m, "provider": p.provider, "input_per_1m": p.input, "output_per_1m": p.output} for m, p in request.app.state.pricing.models.items()]
