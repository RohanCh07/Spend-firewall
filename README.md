# Spend Firewall

Stop runaway AI agents **before** they burn money. Spend Firewall is a drop-in,
OpenAI-compatible gateway that enforces hard budgets, loop detection and
per-session kill switches on every LLM call.

Change your base URL, tag requests with `X-Agent-Id` / `X-Session-Id` /
`X-Customer-Id`, and every call is checked against your policies before it
reaches OpenAI, Anthropic or Gemini.

## What's proven (see tests and `loadtests/RESULTS.md`)

- A simulated runaway loop is stopped after 6 calls, in 0.4 s.
- 100 parallel requests never overspend a budget (atomic Redis Lua reserve-then-reconcile).
- Firewall overhead: 0.3 ms p50 unloaded, 3.8 ms p50 at ~780 req/s (target < 10 ms).
- Killing one session leaves other sessions on the same key unaffected, and cuts a live stream within ~0.5 s.
- Redis down → fail closed (503) or fail open, per tenant, both tested.

## Quickstart

```bash
cp .env.example .env            # set BOOTSTRAP_ADMIN_KEY and your provider keys
docker compose -f infra/docker-compose.yml up --build
# gateway on :8080, Postgres, Redis and a free mock provider on :9000
```

Point any OpenAI client at it:

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8080/v1", api_key="sf-change-me-admin-key",
                default_headers={"X-Agent-Id": "research-bot", "X-Session-Id": "run-42"})
```

Add a budget and watch it bite:

```bash
curl -X POST localhost:8080/v1/admin/policies -H "authorization: Bearer sf-change-me-admin-key" \
  -H content-type:application/json -d '{"name":"per-session","scope":"session","window":"total","limit_usd":2}'
```

To try it with no provider bill, set `UPSTREAM_OVERRIDE_BASE_URL=http://mock-provider:9000/v1`
in `.env`, use model `mock-model`, and run `python examples/runaway-agent/runaway.py --key sf-change-me-admin-key`.

## How a call is decided

1. Authenticate the firewall key → tenant (cached in-process).
2. One Redis Lua call, atomically: kill switch? loop (same tail of the conversation repeated N times)? would any budget be exceeded by the worst-case cost? If all clear, reserve that worst case.
3. Forward to the provider (`max_tokens` is injected if missing, so the worst case is real).
4. Replace the reservation with the actual cost from `usage`; fire 50/80/100% alerts once per window.
5. Write the usage event to Postgres in the background.

Blocks come back as OpenAI-style errors (`budget_exceeded` 402, `session_killed` 403,
`loop_detected` 429) with `x-should-retry: false`, so SDKs don't retry them.

## Surfaces

| Surface | What it does |
|---|---|
| **Gateway** (`gateway/`) | The enforcement engine and `/v1/admin` API. Python + FastAPI, Redis, Postgres. |
| **Web dashboard** (`dashboard/`) | Spend over time and by model/agent/session, live sessions with Kill, budgets with live meters, alerts, settings and keys. |
| **Browser extension** (`extensions/browser/`) | Toolbar badge with today's spend, live sessions with Kill, desktop budget alerts. Chrome, Edge, Firefox. |
| **VS Code extension** (`extensions/vscode/`) | Connects a workspace via `.env`, status-bar spend, sessions tree with Kill, `spendfirewall.yaml` validation and push, alerts. |
| **SDKs** (`sdks/python`, `sdks/js`) | Session helpers for OpenAI clients, `FirewallBlocked` errors, typed admin client. |

## Develop

```bash
# gateway (needs redis-server on PATH, or TEST_REDIS_URL)
cd gateway && pip install -e ".[dev]" && pytest

# JS packages
pnpm install && pnpm build && pnpm test
pnpm --filter spendfirewall-dashboard dev
```

## Docs

- [Roadmap](docs/ROADMAP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Tech stack decision](docs/TECH_STACK.md)
- [Policy file schema](shared/policy-schema/)

## Repository layout

```
gateway/              Python FastAPI gateway (the hot path) + tests
  app/api/            OpenAI-compatible routes + /v1/admin management API
  app/core/           config, identity headers, pricing, token estimation, errors
  app/policies/       policy engine: kill switch, loop detection, budgets
  app/providers/      upstream routing: OpenAI, Anthropic, Gemini
  app/services/       tenants/auth cache, usage recorder, alerts
  app/storage/        Redis Lua scripts + Postgres models
dashboard/            React + Vite + TypeScript web app
extensions/browser/   Manifest V3 extension (TypeScript)
extensions/vscode/    VS Code extension (TypeScript)
sdks/python/          Python SDK
sdks/js/              JS/TS SDK (also used by the dashboard and extensions)
shared/pricing/       model price table (single source of truth)
shared/policy-schema/ JSON Schema for spendfirewall.yaml + example
infra/                Docker Compose
loadtests/            Locust load test + results
examples/             mock provider, runaway agent demo
```
