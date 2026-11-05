"""OpenAI-compatible endpoints: the enforcement hot path."""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.api.deps import proxy_ctx
from app.core.errors import FirewallError
from app.core.identity import Identity, identity_from
from app.core.pricing import ModelPrice, cost_micro, usd
from app.core.tokens import CHARS_PER_TOKEN, estimate_input_tokens, requested_max_output
from app.policies.engine import Reservation
from app.providers.router import Upstream, route
from app.services.tenants import TenantContext

log = logging.getLogger("spendfirewall.proxy")
router = APIRouter()
KILL_CHECK_INTERVAL = 0.5  # seconds between kill-switch checks during a stream


@router.get("/v1/models")
async def list_models(request: Request, ctx: TenantContext = Depends(proxy_ctx)) -> dict[str, Any]:
    models = request.app.state.pricing.models
    return {"object": "list", "data": [{"id": m, "object": "model", "owned_by": p.provider} for m, p in models.items()]}


def _record(
    request: Request,
    ctx: TenantContext,
    ident: Identity,
    model: str,
    provider: str | None,
    decision: str,
    status: int,
    t0: float,
    overhead_ms: float = 0.0,
    in_tok: int = 0,
    out_tok: int = 0,
    cost: int = 0,
    stream: bool = False,
) -> None:
    request.app.state.recorder.usage(
        tenant_id=ctx.tenant.id,
        agent_id=ident.agent_id,
        session_id=ident.session_id,
        customer_id=ident.customer_id,
        model=model,
        provider=provider,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_micro=cost,
        decision=decision,
        status_code=status,
        latency_ms=int((time.perf_counter() - t0) * 1000),
        overhead_ms=round(overhead_ms, 3),
        stream=stream,
    )


@router.post("/v1/chat/completions")
async def chat_completions(request: Request, ctx: TenantContext = Depends(proxy_ctx)) -> Response:
    t0 = time.perf_counter()
    st = request.app.state
    ident = identity_from(request)
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise FirewallError(400, "invalid_request", "Body must be JSON") from None
    if not isinstance(body, dict) or not isinstance(body.get("model"), str):
        raise FirewallError(400, "invalid_request", "`model` is required")
    model: str = body["model"]
    stream = bool(body.get("stream"))

    price: ModelPrice | None = st.pricing.lookup(model)
    if price is None and st.settings.unknown_model_action == "block":
        _record(request, ctx, ident, model, None, "unknown_model", 400, t0)
        raise FirewallError(400, "unknown_model_price", f"No price for model '{model}'; add it to the price table")
    upstream = route(st.settings, model, price)

    # Make the reservation a true upper bound: cap output if the caller didn't.
    max_out = requested_max_output(body)
    if max_out is None:
        max_out = st.settings.default_max_output_tokens
        body[upstream.max_tokens_field] = max_out
    est_in = estimate_input_tokens(body)
    amount = cost_micro(price, est_in, max_out) if price else 0

    try:
        res: Reservation = await st.engine.admit(ctx, ident, body, amount)
    except FirewallError as e:
        blocked = getattr(e, "blocked_slot", None)
        if blocked:
            await st.alerter.check(ctx.tenant, [blocked[0]], [blocked[1]], blocked_index=0)
        _record(request, ctx, ident, model, upstream.provider, e.type, e.status, t0, overhead_ms=(time.perf_counter() - t0) * 1000)
        raise
    overhead_ms = (time.perf_counter() - t0) * 1000

    headers = {"content-type": "application/json"}
    if upstream.api_key:
        headers["authorization"] = f"Bearer {upstream.api_key}"
    url = f"{upstream.base_url}/chat/completions"

    if stream:
        body.setdefault("stream_options", {})["include_usage"] = True
        return await _stream(request, ctx, ident, body, url, headers, upstream, price, res, est_in, t0, overhead_ms)

    try:
        r = await st.http.post(url, json=body, headers=headers)
    except httpx.HTTPError as e:
        await st.engine.settle(res, 0)
        _record(request, ctx, ident, model, upstream.provider, "upstream_error", 502, t0, overhead_ms)
        raise FirewallError(502, "upstream_error", f"Provider request failed: {e.__class__.__name__}", retry=True) from e

    try:
        data = r.json()
    except ValueError:
        data = None
    usage = (data.get("usage") or {}) if isinstance(data, dict) else {}
    if r.status_code >= 400:
        actual, in_tok, out_tok = 0, 0, 0
    elif usage:
        in_tok, out_tok = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
        actual = cost_micro(price, in_tok, out_tok) if price else 0
    else:  # success without usage: keep the conservative reservation
        in_tok, out_tok, actual = est_in, max_out, amount
    await _settle_and_alert(request, ctx, res, actual)
    _record(
        request,
        ctx,
        ident,
        model,
        upstream.provider,
        "allowed" if r.status_code < 400 else "upstream_error",
        r.status_code,
        t0,
        overhead_ms,
        in_tok,
        out_tok,
        actual,
    )

    out_headers = {"x-firewall-cost-usd": f"{usd(actual):.6f}", "x-firewall-overhead-ms": f"{overhead_ms:.2f}"}
    if not res.enforced:
        out_headers["x-firewall-decision"] = "fail_open"
    if data is None:
        return Response(r.content, status_code=r.status_code, headers=out_headers, media_type=r.headers.get("content-type"))
    return JSONResponse(data, status_code=r.status_code, headers=out_headers)


async def _settle_and_alert(request: Request, ctx: TenantContext, res: Reservation, actual: int) -> None:
    st = request.app.state
    values = await st.engine.settle(res, actual)
    if values:
        await st.alerter.check(ctx.tenant, res.slots, values)


async def _stream(
    request: Request,
    ctx: TenantContext,
    ident: Identity,
    body: dict[str, Any],
    url: str,
    headers: dict[str, str],
    upstream: Upstream,
    price: ModelPrice | None,
    res: Reservation,
    est_in: int,
    t0: float,
    overhead_ms: float,
) -> Response:
    st = request.app.state
    model = body["model"]
    req = st.http.build_request("POST", url, json=body, headers=headers)
    try:
        r = await st.http.send(req, stream=True)
    except httpx.HTTPError as e:
        await st.engine.settle(res, 0)
        _record(request, ctx, ident, model, upstream.provider, "upstream_error", 502, t0, overhead_ms, stream=True)
        raise FirewallError(502, "upstream_error", f"Provider request failed: {e.__class__.__name__}", retry=True) from e

    if r.status_code >= 400:
        content = await r.aread()
        await r.aclose()
        await st.engine.settle(res, 0)
        _record(request, ctx, ident, model, upstream.provider, "upstream_error", r.status_code, t0, overhead_ms, stream=True)
        return Response(content, status_code=r.status_code, media_type=r.headers.get("content-type"))

    async def gen() -> AsyncIterator[bytes]:
        usage: dict[str, Any] = {}
        out_chars = 0
        decision = "allowed"
        last_check = time.monotonic()
        try:
            async for line in r.aiter_lines():
                if line.startswith("data:"):
                    payload = line[5:].strip()
                    if payload and payload != "[DONE]":
                        try:
                            chunk = json.loads(payload)
                            if chunk.get("usage"):
                                usage = chunk["usage"]
                            for ch in chunk.get("choices") or []:
                                d = ch.get("delta") or {}
                                out_chars += len(d.get("content") or "")
                                if d.get("tool_calls"):
                                    out_chars += len(json.dumps(d["tool_calls"]))
                        except (ValueError, AttributeError):
                            pass
                # Mid-stream kill switch: stop a live stream within ~0.5s of a kill.
                if res.kill_keys and time.monotonic() - last_check > KILL_CHECK_INTERVAL:
                    last_check = time.monotonic()
                    try:
                        killed = await st.store.is_killed(res.kill_keys)
                    except Exception:  # noqa: BLE001
                        killed = False
                    if killed:
                        decision = "killed_mid_stream"
                        err = {"error": {"type": "session_killed", "code": "session_killed", "message": "Stream stopped by a kill switch"}}
                        yield f"data: {json.dumps(err)}\n\n".encode()
                        yield b"data: [DONE]\n\n"
                        return
                yield (line + "\n").encode()
        finally:
            await r.aclose()
            if usage:
                in_tok, out_tok = int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
            else:
                in_tok, out_tok = est_in, int(out_chars / CHARS_PER_TOKEN) + 1
            actual = cost_micro(price, in_tok, out_tok) if price else 0
            await asyncio.shield(_settle_and_alert(request, ctx, res, actual))
            _record(request, ctx, ident, model, upstream.provider, decision, 200, t0, overhead_ms, in_tok, out_tok, actual, stream=True)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"x-firewall-overhead-ms": f"{overhead_ms:.2f}", "cache-control": "no-cache"})
