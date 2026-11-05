from fastapi import Request

from app.core.errors import FirewallError, unauthorized
from app.services.tenants import TenantContext


def bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-api-key")


async def proxy_ctx(request: Request) -> TenantContext:
    ctx = await request.app.state.tenants.authenticate(bearer(request))
    if ctx is None:
        raise unauthorized()
    return ctx


async def admin_ctx(request: Request) -> TenantContext:
    ctx = await proxy_ctx(request)
    if ctx.role != "admin":
        raise FirewallError(403, "forbidden", "This endpoint needs an admin key")
    return ctx
