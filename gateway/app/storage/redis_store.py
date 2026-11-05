"""Hot-path state in Redis: kill switches, loop counters, budget counters.

All admission checks run in ONE Lua script = one network round trip, and Redis
runs scripts atomically, so parallel requests can't both "fit" a budget.
Money is integer micro-USD so INCRBY math is exact.
"""

import time
from dataclasses import dataclass
from datetime import UTC, datetime

from redis.asyncio import Redis

ADMIT_LUA = """
local n_kill = tonumber(ARGV[1])
local loop_on = tonumber(ARGV[2])
local loop_max = tonumber(ARGV[3])
local loop_window = tonumber(ARGV[4])
local amount = tonumber(ARGV[5])

for i = 1, n_kill do
  if redis.call('EXISTS', KEYS[i]) == 1 then return {1, i, 0} end
end

local first_budget = n_kill + 1
if loop_on == 1 then
  local lk = KEYS[n_kill + 1]
  local c = redis.call('INCR', lk)
  if c == 1 then redis.call('EXPIRE', lk, loop_window) end
  if c > loop_max then return {2, 0, c} end
  first_budget = n_kill + 2
end

local nb = #KEYS - first_budget + 1
for j = 1, nb do
  local k = KEYS[first_budget + j - 1]
  local limit = tonumber(ARGV[5 + 2 * j - 1])
  local cur = tonumber(redis.call('GET', k) or '0')
  if cur + amount > limit then return {3, j, cur} end
end
for j = 1, nb do
  local k = KEYS[first_budget + j - 1]
  local ttl = tonumber(ARGV[5 + 2 * j])
  redis.call('INCRBY', k, amount)
  if ttl > 0 and redis.call('TTL', k) < 0 then redis.call('EXPIRE', k, ttl) end
end
return {0, 0, 0}
"""

# Replace a reservation with the real cost (delta may be negative). Returns new values.
RECONCILE_LUA = """
local delta = tonumber(ARGV[1])
local out = {}
for i, k in ipairs(KEYS) do
  if redis.call('EXISTS', k) == 1 then
    local v = redis.call('INCRBY', k, delta)
    if v < 0 then redis.call('SET', k, 0, 'KEEPTTL'); v = 0 end
    out[i] = v
  else
    out[i] = 0
  end
end
return out
"""

WINDOW_TTL = {"total": 30 * 86400, "minute": 120, "hour": 7200, "day": 2 * 86400, "month": 32 * 86400}


def window_bucket(window: str, ts: float | None = None) -> str:
    ts = time.time() if ts is None else ts
    if window == "total":
        return "all"
    if window == "minute":
        return str(int(ts // 60))
    if window == "hour":
        return str(int(ts // 3600))
    d = datetime.fromtimestamp(ts, UTC)
    if window == "day":
        return d.strftime("%Y%m%d")
    if window == "month":
        return d.strftime("%Y%m")
    raise ValueError(f"unknown window {window}")


def budget_key(tenant_id: str, policy_id: str, scope_id: str, window: str, ts: float | None = None) -> str:
    return f"sf:b:{tenant_id}:{policy_id}:{scope_id}:{window_bucket(window, ts)}"


def kill_key(tenant_id: str, scope: str, scope_id: str) -> str:
    return f"sf:kill:{tenant_id}:{scope}:{scope_id}"


def loop_key(tenant_id: str, session_id: str, fingerprint: str) -> str:
    return f"sf:loop:{tenant_id}:{session_id}:{fingerprint}"


@dataclass
class BudgetSlot:
    key: str
    limit_micro: int
    ttl: int
    scope_id: str = ""


@dataclass
class AdmitResult:
    code: int  # 0 ok, 1 killed, 2 loop, 3 budget
    index: int = 0  # which kill key / budget slot (0-based)
    value: int = 0  # loop count or current spend


class RedisStore:
    def __init__(self, redis: Redis):
        self.redis = redis
        self._admit = redis.register_script(ADMIT_LUA)
        self._reconcile = redis.register_script(RECONCILE_LUA)

    async def admit(
        self,
        kill_keys: list[str],
        loop: tuple[str, int, int] | None,
        budgets: list[BudgetSlot],
        amount: int,
    ) -> AdmitResult:
        keys = list(kill_keys)
        argv: list[int] = [len(kill_keys), 1 if loop else 0, loop[1] if loop else 0, loop[2] if loop else 0, amount]
        if loop:
            keys.append(loop[0])
        for b in budgets:
            keys.append(b.key)
            argv += [b.limit_micro, b.ttl]
        code, idx, val = await self._admit(keys=keys, args=argv)
        return AdmitResult(int(code), max(int(idx) - 1, 0), int(val))

    async def reconcile(self, keys: list[str], delta: int) -> list[int]:
        if not keys:
            return []
        return [int(v) for v in await self._reconcile(keys=keys, args=[delta])]

    async def kill(self, tenant_id: str, scope: str, scope_id: str, reason: str = "") -> None:
        await self.redis.set(kill_key(tenant_id, scope, scope_id), reason or "killed")

    async def unkill(self, tenant_id: str, scope: str, scope_id: str) -> None:
        await self.redis.delete(kill_key(tenant_id, scope, scope_id))

    async def is_killed(self, keys: list[str]) -> bool:
        if not keys:
            return False
        return bool(await self.redis.exists(*keys))

    async def get_counters(self, keys: list[str]) -> list[int]:
        if not keys:
            return []
        return [int(v or 0) for v in await self.redis.mget(keys)]
