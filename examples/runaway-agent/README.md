# Runaway agent demo

Proves "a simulated runaway loop is stopped within seconds".

```bash
docker compose -f infra/docker-compose.yml up -d   # with UPSTREAM_OVERRIDE_BASE_URL set to the mock provider
pip install openai
python examples/runaway-agent/runaway.py --key sf-change-me-admin-key
# -> BLOCKED after 5 calls, 0.4s, $0.0000xx: loop_detected: Same request repeated 6 times in 60s ...
```
