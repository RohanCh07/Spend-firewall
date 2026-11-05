import httpx
from asgi_lifespan import LifespanManager

from app.config import Settings
from app.main import create_app
from tests.conftest import ADMIN_KEY, _free_port
from tests.mock_upstream import MockUpstream


async def _call_with_redis_down(tmp_path, fail_mode: str) -> httpx.Response:
    dead = f"redis://127.0.0.1:{_free_port()}/0"  # nothing listening
    s = Settings(redis_url=dead, database_url=f"sqlite+aiosqlite:///{tmp_path}/f.db", bootstrap_admin_key=ADMIN_KEY, fail_mode=fail_mode, cache_ttl_seconds=0)
    app = create_app(s, MockUpstream().transport())
    async with LifespanManager(app) as mgr:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mgr.app), base_url="http://fw") as c:
            return await c.post(
                "/v1/chat/completions",
                headers={"authorization": f"Bearer {ADMIN_KEY}", "x-session-id": "s"},
                json={"model": "mock-model", "messages": [{"role": "user", "content": "hi"}]},
            )


async def test_redis_down_fails_closed(tmp_path):
    r = await _call_with_redis_down(tmp_path, "closed")
    assert r.status_code == 503 and r.json()["error"]["type"] == "firewall_unavailable"


async def test_redis_down_fails_open(tmp_path):
    r = await _call_with_redis_down(tmp_path, "open")
    assert r.status_code == 200 and r.headers["x-firewall-decision"] == "fail_open"
