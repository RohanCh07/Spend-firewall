"""A fake OpenAI-compatible provider for demos and load tests. Costs nothing.

    uvicorn server:app --port 9000

Env: MOCK_LATENCY_MS (default 50), MOCK_COMPLETION_TOKENS (default 30).
"""

import asyncio
import json
import math
import os
import time

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

LATENCY = float(os.environ.get("MOCK_LATENCY_MS", "50")) / 1000
COMPLETION = int(os.environ.get("MOCK_COMPLETION_TOKENS", "30"))
app = FastAPI(title="Mock LLM provider")


def _usage(body: dict) -> dict:
    cap = body.get("max_completion_tokens") or body.get("max_tokens") or COMPLETION
    out = min(COMPLETION, cap)
    pt = sum(math.ceil(len(str(m.get("content") or "")) / 4) + 3 for m in body.get("messages", []))
    return {"prompt_tokens": pt, "completion_tokens": out, "total_tokens": pt + out}


@app.post("/v1/chat/completions")
async def chat(request: Request):
    body = await request.json()
    await asyncio.sleep(LATENCY)
    if body.get("stream"):
        async def gen():
            for i in range(10):
                await asyncio.sleep(LATENCY / 10)
                chunk = {"id": "mock", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": f"w{i} "}}]}
                yield f"data: {json.dumps(chunk)}\n\n"
            if (body.get("stream_options") or {}).get("include_usage"):
                yield f"data: {json.dumps({'id': 'mock', 'choices': [], 'usage': _usage(body)})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")
    return {
        "id": "mock", "object": "chat.completion", "created": int(time.time()), "model": body.get("model"),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "Mock reply."}, "finish_reason": "stop"}],
        "usage": _usage(body),
    }
