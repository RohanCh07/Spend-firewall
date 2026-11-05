# Dashboard

React + Vite + TypeScript. Talks to the gateway's `/v1/admin` API through
`AdminClient` from `sdks/js`.

Pages: **Overview** (spend, calls, blocked, overhead, spend per hour, by model /
agent / session), **Sessions** (live sessions, budget meter, Kill / Revive),
**Policies** (budgets with live meters), **Activity** (alerts + recent calls,
blocked filter), **Settings** (fail mode, loop detection, alert channels, API keys).

```bash
pnpm install
pnpm --filter spendfirewall build      # the shared client
pnpm --filter spendfirewall-dashboard dev
# open http://localhost:5173, enter the gateway URL and an admin key
```
