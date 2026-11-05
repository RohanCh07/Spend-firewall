# Architecture

## The request path (hot path)

```
Agent ──(base_url = firewall, headers: X-Agent-Id, X-Session-Id, X-Customer-Id)──►
  Gateway
   1. Authenticate the firewall API key, resolve tenant
   2. Identify agent / session / customer from headers
   3. Kill switch? session or agent killed → 403 `session_killed`
   4. Loop check: hash(model + messages tail) seen N times in window → 429 `loop_detected`
   5. Estimate max cost = input tokens × price + max_tokens × output price
   6. Redis Lua: atomically check every budget scope and RESERVE the estimate
        over budget → 402 `budget_exceeded` (or DOWNGRADE to cheaper model, later)
   7. Forward to provider (httpx, streaming or not)
   8. Read actual usage, RECONCILE: release reservation, add real cost
   9. Emit usage event → worker writes Postgres, checks alert thresholds
```

Every block returns an OpenAI-style error body so agent frameworks handle it
cleanly:

```json
{"error": {"type": "budget_exceeded", "message": "Session s-42 hit its $5.00 budget", "scope": "session", "limit_usd": 5.0, "spent_usd": 4.98}}
```

## Why reserve-then-reconcile

Two parallel calls can both "fit" the remaining budget and together overspend.
The Lua script checks and increments in one atomic step, reserving the
*worst-case* cost. After the response, the real cost replaces the reservation.
This is what makes "100 parallel requests never overspend" true.

## Budget scopes

`session`, `agent`, `customer`, `tenant/day`. Each is a Redis key with a TTL for
time windows (e.g. `budget:{tenant}:agent:{id}:day:{yyyymmdd}`). Policies live
in Postgres and are cached in-process with a short TTL.

## Failure modes

| Failure | Default | Configurable |
|---|---|---|
| Redis down | **Fail closed** for tenants with hard budgets, fail open with local in-memory limits for others | per tenant |
| Provider error | Release reservation, pass error through | |
| Gateway down | Agents get connection errors; SDK can optionally fall back to direct provider (off by default) | per SDK |

## Surfaces on top of the gateway

All surfaces use the **management API** (`/v1/admin/...`), never Redis directly.

- **Web dashboard**: full control. Spend charts, sessions table, policies,
  alerts, API keys, kill switch.
- **Browser extension**: a companion, not an interceptor (agents run on servers,
  not in the browser). Toolbar badge with today's spend, popup listing live
  sessions with a Kill button, desktop notifications at 50/80/100% budget,
  link into the dashboard. Signs in with a firewall API key.
- **VS Code extension**: for developers building agents.
  - Command "Connect workspace": writes `OPENAI_BASE_URL` and tagging headers
    into `.env`, so local runs go through the firewall.
  - Status bar: live spend of sessions started from this workspace.
  - Sidebar tree: sessions → calls, with cost per call; Kill session action.
  - `spendfirewall.yaml` policy files get autocomplete/validation from
    `shared/policy-schema`, plus a "Push policy" command.
  - Alert toasts when a dev session trips a budget or loop.

## Data model (Postgres, first cut)

- `tenants`, `api_keys`
- `policies` (scope, scope_id, window, limit_usd, action, priority)
- `usage_events` (ts, tenant, agent, session, customer, model, in_tokens, out_tokens, cost_usd, decision)
- `kill_switches` (scope, scope_id, killed_at, killed_by)
- `alerts` (policy_id, threshold, fired_at) for dedupe
