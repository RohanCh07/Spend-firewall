# Roadmap

**Status (2026-11-05):** Phases 0 to 7 are built and tested. Remaining unchecked items are store publishing, framework-specific integrations and native provider adapters.

Phases are ordered so that every phase ends with something demoable. The
gateway comes first because every other surface is a view on top of it.

## Phase 0: Foundations (week 1)
- [x] Monorepo scaffold, Docker Compose (gateway, Redis, Postgres)
- [x] Gateway skeleton: `/health`, config, structured logging
- [x] CI: lint (ruff), pytest on SQLite + Postgres, JS builds/tests on every PR
- [x] `shared/pricing/models.json` with OpenAI, Anthropic, Gemini prices

**Done when:** `docker compose up` gives a healthy gateway.

## Phase 1: Pass-through proxy (week 2)
- [x] `POST /v1/chat/completions` OpenAI-compatible, non-streaming
- [x] Firewall API keys, tenant resolution, tagging headers
- [x] Cost calculation from actual `usage` in the response
- [x] Usage events written to Postgres

**Done when:** the OpenAI SDK with `base_url` pointed at the gateway works unchanged and every call has a recorded cost.

## Phase 2: Enforcement core (weeks 3–4)
- [x] Pre-call cost estimation (chars/token heuristic that over-estimates + `max_tokens`, injected when missing)
- [x] Redis Lua reserve-then-reconcile for session / agent / customer / daily budgets
- [x] Hard block with OpenAI-style `budget_exceeded` error
- [x] Per-session and per-agent kill switch
- [x] Loop detection (repeat hash in sliding window)
- [x] Fail-open / fail-closed decision implemented and tested
- [x] Race test: 100 parallel calls never overspend
- [x] `examples/runaway-agent` stopped within seconds

**Done when:** every "Done looks like" item in the brief passes except latency.

## Phase 3: Management API + web dashboard (weeks 5–6)
- [x] `/v1/admin` API: policies CRUD, sessions, kill, usage queries
- [x] Dashboard: overview, spend by agent/session/model, top spenders, blocked calls
- [x] Sessions table with Kill button, policy editor
- [x] Alerts: Slack + email at 50/80/100%, deduplicated

**Done when:** a non-developer can set a budget and kill a session from the browser.

## Phase 4: Streaming + performance (week 7)
- [x] SSE streaming pass-through with token counting
- [x] Mid-stream cutoff when a session hits its limit
- [x] Locust load tests, p50/p99 report; target < 10 ms p50 overhead

## Phase 5: VS Code extension (week 8)
- [x] Sign in with API key, "Connect workspace" writes `.env`
- [x] Status bar spend, sessions sidebar, Kill action
- [x] Policy YAML validation from `shared/policy-schema`, "Push policy" command
- [ ] Publish to VS Code Marketplace (and Open VSX)

## Phase 6: Browser extension (week 9)
- [x] MV3 extension for Chrome/Edge, Firefox build
- [x] Badge with today's spend, popup with live sessions + Kill
- [x] Budget notifications
- [ ] Publish to Chrome Web Store

## Phase 7: SDKs + providers (week 10)
- [x] Python + JS helpers (set base URL, headers, session context manager)
- [x] Anthropic and Gemini via their OpenAI-compatible endpoints
- [ ] Native (non-OpenAI-format) adapters, provider failover
- [ ] Integrations: LangGraph, CrewAI, OpenAI Agents SDK

## Later
- Auto-downgrade to cheaper model instead of blocking
- Anomaly detection vs an agent's normal spend
- Tool-call limits per session
- Policy-as-code (YAML in repo, synced by CI)
- Teams, roles, billing, INR pricing, India-hosted region
- Distiller upsell
