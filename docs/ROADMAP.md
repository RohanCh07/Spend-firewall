# Roadmap

Phases are ordered so that every phase ends with something demoable. The
gateway comes first because every other surface is a view on top of it.

## Phase 0: Foundations (week 1)
- [ ] Monorepo scaffold, Docker Compose (gateway, Redis, Postgres)
- [ ] Gateway skeleton: `/health`, config, structured logging
- [ ] CI: lint (ruff), type check (mypy), pytest on every PR
- [ ] `shared/pricing/models.json` with OpenAI, Anthropic, Gemini prices

**Done when:** `docker compose up` gives a healthy gateway.

## Phase 1: Pass-through proxy (week 2)
- [ ] `POST /v1/chat/completions` OpenAI-compatible, non-streaming
- [ ] Firewall API keys, tenant resolution, tagging headers
- [ ] Cost calculation from actual `usage` in the response
- [ ] Usage events written to Postgres

**Done when:** the OpenAI SDK with `base_url` pointed at the gateway works unchanged and every call has a recorded cost.

## Phase 2: Enforcement core (weeks 3–4)
- [ ] Pre-call cost estimation (tokenizer + `max_tokens`)
- [ ] Redis Lua reserve-then-reconcile for session / agent / customer / daily budgets
- [ ] Hard block with OpenAI-style `budget_exceeded` error
- [ ] Per-session and per-agent kill switch
- [ ] Loop detection (repeat hash in sliding window)
- [ ] Fail-open / fail-closed decision implemented and tested
- [ ] Race test: 100 parallel calls never overspend
- [ ] `examples/runaway-agent` stopped within seconds

**Done when:** every "Done looks like" item in the brief passes except latency.

## Phase 3: Management API + web dashboard (weeks 5–6)
- [ ] `/v1/admin` API: policies CRUD, sessions, kill, usage queries
- [ ] Dashboard: overview, spend by agent/session/model, top spenders, blocked calls
- [ ] Sessions table with Kill button, policy editor
- [ ] Alerts: Slack + email at 50/80/100%, deduplicated

**Done when:** a non-developer can set a budget and kill a session from the browser.

## Phase 4: Streaming + performance (week 7)
- [ ] SSE streaming pass-through with token counting
- [ ] Mid-stream cutoff when a session hits its limit
- [ ] Locust load tests, p50/p99 report; target < 10 ms p50 overhead

## Phase 5: VS Code extension (week 8)
- [ ] Sign in with API key, "Connect workspace" writes `.env`
- [ ] Status bar spend, sessions sidebar, Kill action
- [ ] Policy YAML validation from `shared/policy-schema`, "Push policy" command
- [ ] Publish to VS Code Marketplace (and Open VSX)

## Phase 6: Browser extension (week 9)
- [ ] MV3 extension for Chrome/Edge, Firefox build
- [ ] Badge with today's spend, popup with live sessions + Kill
- [ ] Budget notifications
- [ ] Publish to Chrome Web Store

## Phase 7: SDKs + providers (week 10)
- [ ] Python + JS helpers (set base URL, headers, session context manager)
- [ ] Anthropic and Gemini native adapters, provider failover
- [ ] Integrations: LangGraph, CrewAI, OpenAI Agents SDK

## Later
- Auto-downgrade to cheaper model instead of blocking
- Anomaly detection vs an agent's normal spend
- Tool-call limits per session
- Policy-as-code (YAML in repo, synced by CI)
- Teams, roles, billing, INR pricing, India-hosted region
- Distiller upsell
