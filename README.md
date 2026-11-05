# Spend Firewall

Stop runaway AI agents **before** they burn money. Spend Firewall is a drop-in,
OpenAI-compatible gateway that enforces hard budgets, loop detection and
per-session kill switches on every LLM call.

Change your base URL, tag requests with `X-Agent-Id` / `X-Session-Id` /
`X-Customer-Id`, and every call is checked against your policies before it
reaches OpenAI, Anthropic or Gemini.

## Surfaces

| Surface | What it does |
|---|---|
| **Gateway** (`gateway/`) | The enforcement engine. Python + FastAPI, Redis, Postgres. |
| **Web dashboard** (`dashboard/`) | Spend by agent/session/model, policies, alerts, kill switch. |
| **Browser extension** (`extensions/browser/`) | Live spend badge, budget alerts and one-click kill switch from any tab. |
| **VS Code extension** (`extensions/vscode/`) | Wires your workspace to the gateway, shows live session spend in the status bar, edits policies with validation. |
| **SDKs** (`sdks/`) | Thin helpers that set the base URL and tagging headers for Python and JS agents. |

## Docs

- [Roadmap](docs/ROADMAP.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Tech stack decision](docs/TECH_STACK.md)

## Repository layout

```
gateway/            Python FastAPI gateway (the hot path)
  app/api/          OpenAI-compatible routes + management API
  app/core/         config, cost estimation, request identity
  app/policies/     policy engine: budgets, loops, kill switch
  app/providers/    upstream adapters: OpenAI, Anthropic, Gemini
  app/storage/      Redis counters (Lua) + Postgres models
  tests/            pytest, incl. race-condition tests
dashboard/          React + Vite + TypeScript web app
extensions/browser/ Chrome/Edge/Firefox extension (Manifest V3, TypeScript)
extensions/vscode/  VS Code extension (TypeScript)
sdks/python/        Python helper package
sdks/js/            JS/TS helper package
shared/pricing/     model price table (single source of truth)
shared/policy-schema/ JSON Schema for policy YAML (used by gateway + VS Code)
infra/              Docker Compose, Redis/Postgres config
loadtests/          Locust load tests (p50/p99 latency)
examples/           demo agents, incl. a simulated runaway loop
```
