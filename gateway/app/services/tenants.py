"""Auth + tenant/policy lookup with a short in-process cache.

The hot path must not hit Postgres on every call, so key->tenant and
tenant->policies are cached for `cache_ttl_seconds`. Admin writes invalidate
the local cache; other workers converge within the TTL.
"""

import hashlib
import secrets
import time
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.storage.db import ApiKey, Policy, Tenant

KEY_PREFIX = "sf-"


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


@dataclass(frozen=True)
class PolicySnap:
    id: str
    name: str
    scope: str
    scope_id: str | None
    window: str
    limit_micro: int


@dataclass(frozen=True)
class TenantSnap:
    id: str
    name: str
    fail_mode: str
    loop_max_repeats: int
    loop_window_seconds: int
    require_identity: bool
    slack_webhook_url: str | None
    alert_email: str | None


@dataclass
class TenantContext:
    tenant: TenantSnap
    policies: list[PolicySnap]
    role: str = "proxy"


@dataclass
class _Entry:
    value: object
    expires: float


@dataclass
class TenantService:
    sessionmaker: async_sessionmaker
    ttl: float = 5.0
    _keys: dict[str, _Entry] = field(default_factory=dict)
    _tenants: dict[str, _Entry] = field(default_factory=dict)

    def invalidate(self, tenant_id: str | None = None) -> None:
        if tenant_id is None:
            self._tenants.clear()
            self._keys.clear()
        else:
            self._tenants.pop(tenant_id, None)

    async def authenticate(self, raw_key: str | None) -> TenantContext | None:
        if not raw_key:
            return None
        h = hash_key(raw_key)
        now = time.monotonic()
        e = self._keys.get(h)
        if e is None or e.expires < now:
            async with self.sessionmaker() as s:
                k = (await s.execute(select(ApiKey).where(ApiKey.key_hash == h, ApiKey.revoked.is_(False)))).scalar_one_or_none()
            e = _Entry((k.tenant_id, k.role) if k else None, now + self.ttl)
            self._keys[h] = e
        if e.value is None:
            return None
        tenant_id, role = e.value  # type: ignore[misc]
        ctx = await self.context(tenant_id)
        if ctx is None:
            return None
        return TenantContext(ctx.tenant, ctx.policies, role)

    async def context(self, tenant_id: str) -> TenantContext | None:
        now = time.monotonic()
        e = self._tenants.get(tenant_id)
        if e is None or e.expires < now:
            async with self.sessionmaker() as s:
                t = await s.get(Tenant, tenant_id)
                if t is None:
                    return None
                ps = (await s.execute(select(Policy).where(Policy.tenant_id == tenant_id, Policy.enabled.is_(True)))).scalars().all()
            ctx = TenantContext(
                TenantSnap(t.id, t.name, t.fail_mode, t.loop_max_repeats, t.loop_window_seconds, t.require_identity, t.slack_webhook_url, t.alert_email),
                [PolicySnap(p.id, p.name, p.scope, p.scope_id, p.window, p.limit_micro) for p in ps],
            )
            e = _Entry(ctx, now + self.ttl)
            self._tenants[tenant_id] = e
        return e.value  # type: ignore[return-value]


async def bootstrap_tenant(s: AsyncSession, name: str, raw_key: str, **settings: object) -> bool:
    """Create a tenant + admin key unless the key already exists. Runs inside init_db's lock."""
    if (await s.execute(select(ApiKey).where(ApiKey.key_hash == hash_key(raw_key)))).first():
        return False
    t = Tenant(name=name, **settings)
    s.add(t)
    await s.flush()
    s.add(ApiKey(tenant_id=t.id, name="bootstrap admin key", key_hash=hash_key(raw_key), prefix=raw_key[:10], role="admin"))
    return True


async def create_tenant_with_key(
    sessionmaker: async_sessionmaker, name: str, raw_key: str | None = None, role: str = "admin", **settings: object
) -> tuple[Tenant, str]:
    raw_key = raw_key or generate_key()
    async with sessionmaker() as s:
        t = Tenant(name=name, **settings)
        s.add(t)
        await s.flush()
        s.add(ApiKey(tenant_id=t.id, name=f"{role} key", key_hash=hash_key(raw_key), prefix=raw_key[:10], role=role))
        await s.commit()
    return t, raw_key
