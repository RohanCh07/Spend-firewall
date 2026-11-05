"""Load test the gateway. Measures end-to-end latency and reads the gateway's
own overhead from the `x-firewall-overhead-ms` header.

    locust -f loadtests/locustfile.py --host http://localhost:8080 --headless -u 200 -r 50 -t 60s

Env: SF_KEY (admin/proxy key), SF_MODEL (default mock-model).
Compare against hitting the mock provider directly to see the firewall's cost.
"""

import os
import random
import uuid

from locust import HttpUser, between, events, task

KEY = os.environ.get("SF_KEY", "sf-change-me-admin-key")
MODEL = os.environ.get("SF_MODEL", "mock-model")
overheads: list[float] = []


class Agent(HttpUser):
    wait_time = between(0.0, 0.05)

    def on_start(self) -> None:
        self.session = uuid.uuid4().hex[:12]
        self.headers = {"authorization": f"Bearer {KEY}", "x-agent-id": f"agent-{random.randint(1, 20)}",
                        "x-session-id": self.session}

    @task
    def chat(self) -> None:
        body = {"model": MODEL, "max_tokens": 50,
                "messages": [{"role": "user", "content": f"question {uuid.uuid4().hex}"}]}
        with self.client.post("/v1/chat/completions", json=body, headers=self.headers, catch_response=True,
                              name="chat") as r:
            if r.status_code == 200:
                overheads.append(float(r.headers.get("x-firewall-overhead-ms", 0)))
                r.success()
            elif r.status_code in (402, 429):
                r.success()  # a block is a correct answer
            else:
                r.failure(f"{r.status_code}")


@events.test_stop.add_listener
def report(**_: object) -> None:
    if overheads:
        o = sorted(overheads)
        pct = lambda p: o[min(len(o) - 1, int(len(o) * p))]  # noqa: E731
        print(f"\nfirewall overhead (pre-upstream): p50={pct(0.5):.2f}ms p95={pct(0.95):.2f}ms p99={pct(0.99):.2f}ms n={len(o)}")
