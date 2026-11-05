import os
import shutil
import socket
import subprocess
import time
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from asgi_lifespan import LifespanManager

from app.config import Settings
from app.main import create_app
from app.services.tenants import create_tenant_with_key
from app.storage.db import Base, make_engine
from tests.mock_upstream import MockUpstream

ADMIN_KEY = "sf-test-admin-key"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    if url := os.environ.get("TEST_REDIS_URL"):
        yield url
        return
    if not shutil.which("redis-server"):
        pytest.skip("redis-server not installed and TEST_REDIS_URL not set")
    port = _free_port()
    proc = subprocess.Popen(["redis-server", "--port", str(port), "--save", "", "--appendonly", "no"], stdout=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.05)
    yield f"redis://127.0.0.1:{port}/0"
    proc.terminate()


@pytest.fixture
def upstream() -> MockUpstream:
    return MockUpstream()


@pytest.fixture
def settings(redis_url: str, tmp_path) -> Settings:
    return Settings(
        redis_url=redis_url,
        database_url=f"sqlite+aiosqlite:///{tmp_path}/t.db",
        bootstrap_admin_key=ADMIN_KEY,
        openai_api_key="sk-upstream",
        cache_ttl_seconds=0.0,
        loop_max_repeats=5,
        loop_window_seconds=60,
        default_max_output_tokens=1000,
    )


class Harness:
    def __init__(self, app, client: httpx.AsyncClient, upstream: MockUpstream):
        self.app, self.client, self.upstream = app, client, upstream

    @property
    def state(self):
        return self.app.state

    async def chat(
        self, session: str | None = "s1", agent: str | None = "a1", key: str = ADMIN_KEY, messages: list | None = None, model: str = "mock-model", **extra
    ) -> httpx.Response:
        headers = {"authorization": f"Bearer {key}"}
        if session:
            headers["x-session-id"] = session
        if agent:
            headers["x-agent-id"] = agent
        body = {"model": model, "messages": messages or [{"role": "user", "content": "hi"}], **extra}
        return await self.client.post("/v1/chat/completions", json=body, headers=headers)

    async def admin(self, method: str, path: str, **kw) -> httpx.Response:
        return await self.client.request(method, f"/v1/admin{path}", headers={"authorization": f"Bearer {ADMIN_KEY}"}, **kw)

    async def policy(self, scope: str, limit_usd: float, window: str = "total", scope_id: str | None = None, name=None):
        r = await self.admin(
            "POST",
            "/policies",
            json={"name": name or f"{scope}-{window}-{limit_usd}", "scope": scope, "window": window, "limit_usd": limit_usd, "scope_id": scope_id},
        )
        assert r.status_code == 201, r.text
        return r.json()

    async def flush(self) -> None:
        await self.state.recorder.flush()


@pytest.fixture
async def h(settings: Settings, upstream: MockUpstream) -> AsyncIterator[Harness]:
    app = create_app(settings, upstream.transport())
    async with LifespanManager(app) as mgr:
        await app.state.redis.flushdb()
        transport = httpx.ASGITransport(app=mgr.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://fw") as client:
            yield Harness(app, client, upstream)


@pytest.fixture
async def proxy_key(h: Harness) -> str:
    r = await h.admin("POST", "/keys", json={"role": "proxy"})
    return r.json()["key"]


__all__ = ["create_tenant_with_key"]
