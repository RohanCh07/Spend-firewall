import asyncio
import json

from tests.conftest import ADMIN_KEY, Harness


def _events(text: str) -> list:
    return [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]


async def test_stream_passthrough_and_cost(h: Harness):
    await h.policy("session", 1.0)
    r = await h.chat(stream=True)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    evs = _events(r.text)
    assert evs[-1] == "[DONE]" and any("tok0" in e for e in evs)
    assert h.upstream.calls[-1]["stream_options"] == {"include_usage": True}
    await h.flush()
    ev = (await h.admin("GET", "/events")).json()[0]
    assert ev["stream"] and ev["cost_usd"] == 0.000044
    b = (await h.admin("GET", "/budgets", params={"scope_id": "s1"})).json()[0]
    assert b["spent_usd"] == 0.000044


async def test_kill_switch_cuts_live_stream(h: Harness):
    h.upstream.stream_chunks, h.upstream.chunk_delay = 40, 0.05  # ~2s stream

    async def consume() -> list:
        out = []
        async with h.client.stream(
            "POST",
            "/v1/chat/completions",
            headers={"authorization": f"Bearer {ADMIN_KEY}", "x-session-id": "live"},
            json={"model": "mock-model", "stream": True, "messages": [{"role": "user", "content": "go"}]},
        ) as r:
            async for line in r.aiter_lines():
                if line.startswith("data:"):
                    out.append(line[5:].strip())
        return out

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.4)
    await h.admin("POST", "/kill", json={"scope": "session", "scope_id": "live"})
    evs = await asyncio.wait_for(task, 5)
    assert evs[-1] == "[DONE]"
    assert json.loads(evs[-2])["error"]["type"] == "session_killed"
    assert len(evs) < 40
    await h.flush()
    ev = (await h.admin("GET", "/events")).json()[0]
    assert ev["decision"] == "killed_mid_stream" and ev["cost_usd"] > 0
