# Load test results

## 2026-11-05, dev container (single box, everything co-located)

Setup: 4 uvicorn workers, Redis 7, Postgres 16, mock provider (50 ms latency, 1 worker),
Locust 200 users on the same machine. Two budget policies active on every call
(per-session total + tenant daily), loop detection on.

| Metric | Value |
|---|---|
| Requests | 23,530 in 30 s (~780 req/s), 0 failures |
| **Firewall pre-upstream overhead p50** | **3.8 ms** (target < 10 ms) |
| Overhead p95 / p99 | 13.5 ms / 24.8 ms |

Single-request (no load) overhead measured in-process: p50 0.31 ms, p99 1.26 ms.

The p95/p99 tail under load is CPU contention: Locust, the mock and the gateway
share the same cores. Re-run on separate machines before quoting tail numbers.
