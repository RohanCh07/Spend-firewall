import asyncio

from tests.conftest import Harness


def _q(i: int) -> list:
    return [{"role": "user", "content": f"q{i}"}]


async def test_session_budget_blocks_with_clear_error(h: Harness):
    await h.policy("session", 0.0005)  # 500 micro-USD; each call costs 44
    codes = [(await h.chat(max_tokens=20, messages=_q(i))).status_code for i in range(15)]
    assert codes[0] == 200 and 402 in codes
    r = await h.chat(max_tokens=20)
    err = r.json()["error"]
    assert r.status_code == 402 and err["type"] == "budget_exceeded" and err["scope"] == "session"
    assert r.headers["x-should-retry"] == "false"
    b = (await h.admin("GET", "/budgets", params={"scope_id": "s1"})).json()[0]
    assert b["spent_usd"] <= 0.0005
    # another session has its own budget
    assert (await h.chat(session="s2", max_tokens=20)).status_code == 200


async def test_counter_holds_actual_not_reservation(h: Harness):
    await h.policy("agent", 10)
    await h.chat()  # reserves ~2007 micro (1000 max tokens), actual 44
    b = (await h.admin("GET", "/budgets", params={"scope_id": "a1"})).json()[0]
    assert b["spent_usd"] == 0.000044


async def test_100_parallel_requests_never_overspend(h: Harness):
    limit_micro = 1000
    await h.policy("session", limit_micro / 1e6)
    h.upstream.delay = 0.01  # keep requests in flight concurrently
    rs = await asyncio.gather(*[h.chat(session="race", max_tokens=20, messages=_q(i)) for i in range(100)])
    ok = [r for r in rs if r.status_code == 200]
    blocked = [r for r in rs if r.status_code == 402]
    assert len(ok) + len(blocked) == 100 and blocked and ok
    spent = sum(float(r.headers["x-firewall-cost-usd"]) for r in ok)
    assert spent <= limit_micro / 1e6
    b = (await h.admin("GET", "/budgets", params={"scope_id": "race"})).json()[0]
    assert b["spent_usd"] <= limit_micro / 1e6
    assert abs(b["spent_usd"] - spent) < 1e-9


async def test_daily_tenant_budget(h: Harness):
    await h.policy("tenant", 0.0001, window="day")  # 100 micro: two calls of 44 fit (reserving 47 each)
    assert (await h.chat(session="x", max_tokens=20)).status_code == 200
    assert (await h.chat(session="y", max_tokens=20)).status_code == 200
    assert (await h.chat(session="z", max_tokens=20)).status_code == 402


async def test_policy_for_one_specific_agent(h: Harness):
    await h.policy("agent", 0.00005, scope_id="expensive-bot")
    assert (await h.chat(agent="expensive-bot", max_tokens=20)).status_code == 200
    assert (await h.chat(agent="expensive-bot", max_tokens=20)).status_code == 402
    assert (await h.chat(agent="other", max_tokens=20)).status_code == 200


async def test_kill_one_session_leaves_others_alone(h: Harness):
    assert (await h.chat(session="bad")).status_code == 200
    r = await h.admin("POST", "/kill", json={"scope": "session", "scope_id": "bad", "reason": "runaway"})
    assert r.status_code == 201
    r = await h.chat(session="bad")
    assert r.status_code == 403 and r.json()["error"]["type"] == "session_killed"
    assert (await h.chat(session="good")).status_code == 200  # same key, unaffected
    assert [k["scope_id"] for k in (await h.admin("GET", "/kills")).json()] == ["bad"]
    assert (await h.admin("DELETE", "/kill/session/bad")).status_code == 204
    assert (await h.chat(session="bad")).status_code == 200


async def test_kill_agent(h: Harness):
    await h.admin("POST", "/kill", json={"scope": "agent", "scope_id": "a1"})
    r = await h.chat(session="any")
    assert r.status_code == 403 and r.json()["error"]["type"] == "agent_killed"


async def test_loop_detection_blocks_repeats(h: Harness):
    codes = [(await h.chat(session="loopy")).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]
    r = await h.chat(session="loopy")
    assert r.json()["error"]["type"] == "loop_detected" and r.headers["x-should-retry"] == "false"
    # different content in the same session is fine
    assert (await h.chat(session="loopy", messages=[{"role": "user", "content": "new question"}])).status_code == 200


async def test_runaway_agent_with_growing_history_is_stopped(h: Harness):
    """Realistic loop: history grows each turn, but the agent keeps making the same tool call."""
    await h.policy("session", 5.0)
    history = [{"role": "system", "content": "You are an agent"}, {"role": "user", "content": "find the file"}]
    statuses = []
    for i in range(20):
        r = await h.chat(session="runaway", messages=list(history))
        statuses.append(r.status_code)
        if r.status_code != 200:
            break
        history += [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": f"call_{i}", "type": "function", "function": {"name": "search", "arguments": '{"q": "file"}'}}],
            },
            {"role": "tool", "tool_call_id": f"call_{i}", "content": "no results"},
        ]
    assert statuses[-1] == 429
    assert len(statuses) <= 7  # stopped within a handful of calls


async def test_require_identity(h: Harness):
    await h.admin("PATCH", "/settings", json={"require_identity": True})
    r = await h.chat(session=None)
    assert r.status_code == 400 and r.json()["error"]["type"] == "identity_required"
