from tests.conftest import Harness


async def test_policy_crud_and_sync(h: Harness):
    p = await h.policy("session", 2.0, name="per-session")
    assert p["limit_usd"] == 2.0
    r = await h.admin("PATCH", f"/policies/{p['id']}", json={"limit_usd": 3})
    assert r.json()["limit_usd"] == 3.0
    r = await h.admin(
        "PUT",
        "/policies",
        json={
            "version": 1,
            "settings": {"loop_max_repeats": 3},
            "budgets": [
                {"name": "per-session", "scope": "session", "window": "total", "limit_usd": 4},
                {"name": "daily", "scope": "tenant", "window": "day", "limit_usd": 50},
            ],
        },
    )
    assert r.json() == {"created": 1, "updated": 1, "disabled": 0}
    ps = {p["name"]: p for p in (await h.admin("GET", "/policies")).json()}
    assert ps["per-session"]["limit_usd"] == 4 and ps["daily"]["window"] == "day"
    assert (await h.admin("GET", "/me")).json()["tenant"]["loop_max_repeats"] == 3
    r = await h.admin("PUT", "/policies", json={"version": 1, "budgets": []})
    assert r.json()["disabled"] == 2
    assert (await h.admin("DELETE", f"/policies/{p['id']}")).status_code == 204


async def test_rejects_invalid_policy(h: Harness):
    r = await h.admin("POST", "/policies", json={"name": "x", "scope": "planet", "window": "day", "limit_usd": 1})
    assert r.status_code == 422


async def test_usage_summary_and_sessions(h: Harness):
    await h.policy("session", 0.0001)
    for s in ("s1", "s1", "s2"):
        await h.chat(session=s, max_tokens=20)
    await h.chat(session="s1", max_tokens=20)  # 3rd call in s1 -> over 100 micro budget
    await h.flush()
    summ = (await h.admin("GET", "/usage/summary")).json()
    assert summ["calls"] == 4 and summ["blocked"] == 1 and summ["sessions"] == 2
    assert summ["by_model"][0]["key"] == "mock-model"
    assert summ["decisions"]["budget_exceeded"] == 1
    assert summ["timeseries"] and summ["timeseries"][0]["calls"] == 4
    sess = {s["session_id"]: s for s in (await h.admin("GET", "/sessions")).json()}
    assert sess["s1"]["calls"] == 3 and sess["s1"]["blocked"] == 1 and sess["s1"]["live"]
    assert sess["s1"]["budget_pct"] == 88.0
    blocked = (await h.admin("GET", "/events", params={"blocked_only": True})).json()
    assert len(blocked) == 1


async def test_alerts_fire_once_per_threshold(h: Harness):
    await h.policy("session", 0.0001, name="tiny")  # 100 micro; calls cost 44
    for i in range(4):
        await h.chat(max_tokens=20, messages=[{"role": "user", "content": f"q{i}"}])
    await h.flush()
    alerts = (await h.admin("GET", "/alerts")).json()
    assert sorted(a["threshold"] for a in alerts) == [50, 80, 100]
    assert all(a["policy"] == "tiny" for a in alerts)


async def test_keys(h: Harness):
    k = (await h.admin("POST", "/keys", json={"name": "ci", "role": "proxy"})).json()
    assert k["key"].startswith("sf-")
    assert (await h.chat(key=k["key"])).status_code == 200
    assert (await h.admin("DELETE", f"/keys/{k['id']}")).status_code == 204
    assert (await h.chat(key=k["key"])).status_code == 401
