import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import select

from app.api import admin, proxy
from app.config import Settings, get_settings
from app.core.errors import FirewallError
from app.core.pricing import PriceTable
from app.policies.engine import PolicyEngine
from app.services.alerts import Alerter
from app.services.recorder import Recorder
from app.services.tenants import TenantService, create_tenant_with_key, hash_key
from app.storage.db import ApiKey, create_all, make_engine, make_sessionmaker
from app.storage.redis_store import RedisStore

log = logging.getLogger("spendfirewall")


def create_app(settings: Settings | None = None, http_transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        st = app.state
        st.settings = settings
        st.pricing = PriceTable.load(settings.pricing_path)
        st.engine_db = make_engine(settings.database_url)
        await create_all(st.engine_db)
        st.sessionmaker = make_sessionmaker(st.engine_db)
        st.redis = Redis.from_url(settings.redis_url, socket_timeout=0.5, socket_connect_timeout=0.5)
        st.store = RedisStore(st.redis)
        st.engine = PolicyEngine(st.store)
        st.tenants = TenantService(st.sessionmaker, settings.cache_ttl_seconds)
        st.http = httpx.AsyncClient(
            transport=http_transport,
            timeout=httpx.Timeout(settings.upstream_timeout_seconds, connect=10),
            limits=httpx.Limits(max_connections=1000, max_keepalive_connections=200),
        )
        st.recorder = Recorder(st.sessionmaker)
        st.recorder.start()
        st.alerter = Alerter(st.redis, st.recorder, st.http, settings)
        if settings.bootstrap_admin_key:
            async with st.sessionmaker() as s:
                exists = (await s.execute(select(ApiKey).where(ApiKey.key_hash == hash_key(settings.bootstrap_admin_key)))).first()
            if not exists:
                await create_tenant_with_key(
                    st.sessionmaker,
                    "default",
                    settings.bootstrap_admin_key,
                    "admin",
                    fail_mode=settings.fail_mode,
                    loop_max_repeats=settings.loop_max_repeats,
                    loop_window_seconds=settings.loop_window_seconds,
                )
                log.info("bootstrapped default tenant")
        yield
        await st.recorder.stop()
        await st.http.aclose()
        await st.redis.aclose()
        await st.engine_db.dispose()

    app = FastAPI(title="Spend Firewall Gateway", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins.split(","),
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-firewall-cost-usd", "x-firewall-overhead-ms", "x-firewall-decision"],
    )

    @app.exception_handler(FirewallError)
    async def _fw_error(_: Request, e: FirewallError) -> JSONResponse:
        return e.response()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    async def ready(request: Request) -> JSONResponse:
        try:
            await request.app.state.redis.ping()
            redis_ok = True
        except Exception:  # noqa: BLE001
            redis_ok = False
        return JSONResponse({"redis": redis_ok}, status_code=200 if redis_ok else 503)

    app.include_router(proxy.router)
    app.include_router(admin.router)
    return app


app = create_app()
