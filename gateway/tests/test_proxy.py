from app.config import Settings
from app.core.pricing import PriceTable
from tests.conftest import Harness


async def test_health_and_ready(h: Harness):
    assert (await h.client.get("/health")).json() == {"status": "ok"}
    assert (await h.client.get("/ready")).json() == {"redis": True}


async def test_passthrough_records_actual_cost(h: Harness):
    r = await h.chat()
    assert r.status_code == 200, r.text
    assert r.json()["choices"][0]["message"]["content"] == "ok"
    # mock-model: $1/1M in, $2/1M out. "hi" -> 4 prompt tokens, 20 completion -> 4 + 40 micro-USD
    assert r.headers["x-firewall-cost-usd"] == "0.000044"
    assert float(r.headers["x-firewall-overhead-ms"]) >= 0
    # upstream got the gateway's provider key, not the caller's firewall key
    await h.flush()
    ev = (await h.admin("GET", "/events")).json()
    assert ev[0]["decision"] == "allowed" and ev[0]["cost_usd"] == 0.000044 and ev[0]["session_id"] == "s1"


async def test_injects_max_tokens_when_missing(h: Harness):
    await h.chat()
    assert h.upstream.calls[-1]["max_completion_tokens"] == 1000
    await h.chat(max_tokens=50)
    assert h.upstream.calls[-1]["max_tokens"] == 50 and "max_completion_tokens" not in h.upstream.calls[-1]


async def test_rejects_bad_key(h: Harness):
    r = await h.chat(key="nope")
    assert r.status_code == 401 and r.json()["error"]["type"] == "invalid_api_key"


async def test_unknown_model_blocked(h: Harness):
    r = await h.chat(model="totally-new-model")
    assert r.status_code == 400 and r.json()["error"]["type"] == "unknown_model_price"


async def test_proxy_key_cannot_use_admin(h: Harness, proxy_key: str):
    assert (await h.chat(key=proxy_key)).status_code == 200
    r = await h.client.get("/v1/admin/me", headers={"authorization": f"Bearer {proxy_key}"})
    assert r.status_code == 403


async def test_upstream_error_releases_reservation(h: Harness):
    await h.policy("session", 1.0)
    h.upstream.fail_status = 500
    r = await h.chat()
    assert r.status_code == 500
    b = (await h.admin("GET", "/budgets", params={"scope_id": "s1"})).json()
    assert b[0]["spent_usd"] == 0


async def test_models_list(h: Harness):
    r = await h.client.get("/v1/models", headers={"authorization": "Bearer sf-test-admin-key"})
    assert any(m["id"] == "gpt-4o" for m in r.json()["data"])


def test_price_prefix_lookup():
    t = PriceTable.load(Settings().pricing_path)
    assert t.lookup("gpt-4o-2024-08-06").model == "gpt-4o"
    assert t.lookup("gpt-4o-mini-2024-07-18").model == "gpt-4o-mini"
    assert t.lookup("claude-sonnet-4-5-20250929").provider == "anthropic"
    assert t.lookup("nope") is None
