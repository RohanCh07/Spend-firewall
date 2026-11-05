# Load tests

Target from the brief: the firewall adds **< 10 ms p50**.

```bash
# 1. fake provider + gateway pointed at it
uvicorn server:app --app-dir examples/mock-provider --port 9000 &
UPSTREAM_OVERRIDE_BASE_URL=http://localhost:9000/v1 BOOTSTRAP_ADMIN_KEY=sf-load \
  uvicorn app.main:app --app-dir gateway --port 8080 --workers 4 &
# 2. load
pip install locust
SF_KEY=sf-load locust -f loadtests/locustfile.py --host http://localhost:8080 --headless -u 200 -r 50 -t 60s
```

The report prints the gateway's own pre-upstream overhead percentiles (from the
`x-firewall-overhead-ms` header) next to Locust's end-to-end numbers. Subtract
the mock's configured latency (`MOCK_LATENCY_MS`, 50 ms) from end-to-end to see
the full added cost including reconciliation.
