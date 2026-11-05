import json

import httpx
import pytest

from spendfirewall import Firewall, FirewallBlocked, headers, is_firewall_block


def test_headers():
    assert headers("a", "s") == {"X-Agent-Id": "a", "X-Session-Id": "s"}


def test_env_config(monkeypatch):
    monkeypatch.setenv("SPENDFIREWALL_URL", "http://gw:8080/v1")
    monkeypatch.setenv("SPENDFIREWALL_API_KEY", "sf-x")
    monkeypatch.setenv("SPENDFIREWALL_AGENT_ID", "bot")
    fw = Firewall()
    assert fw.base_url == "http://gw:8080/v1" and fw.agent_id == "bot"
    with fw.session(customer_id="c1") as s:
        assert s.headers["X-Agent-Id"] == "bot" and s.headers["X-Customer-Id"] == "c1"
        assert s.headers["X-Session-Id"].startswith("s-")


def _transport(status: int, body: dict, seen: list):
    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(status, json=body, headers={"x-should-retry": "false"})
    return httpx.MockTransport(handler)


def test_openai_client_sends_headers_and_raises_blocked():
    pytest.importorskip("openai")
    seen: list = []
    fw = Firewall(url="http://gw", api_key="sf-k", agent_id="bot")
    body = {"error": {"type": "budget_exceeded", "message": "Session budget would be exceeded"}}
    with fw.session("s-1") as s:
        client = s.openai(http_client=httpx.Client(transport=_transport(402, body, seen)))
        with pytest.raises(FirewallBlocked) as ei:
            client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": "hi"}])
    assert ei.value.type == "budget_exceeded" and ei.value.status == 402
    assert len(seen) == 1  # not retried
    req = seen[0]
    assert str(req.url) == "http://gw/v1/chat/completions"
    assert req.headers["x-session-id"] == "s-1" and req.headers["x-agent-id"] == "bot"
    assert req.headers["authorization"] == "Bearer sf-k"
    assert is_firewall_block(ei.value)


def test_openai_non_firewall_errors_pass_through():
    openai = pytest.importorskip("openai")
    fw = Firewall(url="http://gw", api_key="k")
    with fw.session() as s:
        client = s.openai(max_retries=0, http_client=httpx.Client(transport=_transport(400, {"error": {"type": "invalid_request_error", "message": "bad"}}, [])))
        with pytest.raises(openai.BadRequestError):
            client.chat.completions.create(model="x", messages=[])


def test_admin_client():
    seen: list = []
    fw = Firewall(url="http://gw", api_key="sf-admin")
    admin = fw.admin()
    admin.http = httpx.Client(transport=_transport(201, {"id": "k1"}, seen))
    admin.kill("session", "s-9", "loop")
    assert seen[0].url.path == "/v1/admin/kill"
    assert json.loads(seen[0].content) == {"scope": "session", "scope_id": "s-9", "reason": "loop"}
