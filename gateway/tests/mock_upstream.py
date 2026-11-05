"""An in-process fake OpenAI used by tests (no network, no cost)."""

import asyncio
import json
import math

import httpx


class MockUpstream:
    def __init__(self, completion_tokens: int = 20, delay: float = 0.0, stream_chunks: int = 5, chunk_delay: float = 0.0):
        self.completion_tokens = completion_tokens
        self.delay = delay
        self.stream_chunks = stream_chunks
        self.chunk_delay = chunk_delay
        self.calls: list[dict] = []
        self.fail_status: int | None = None

    def usage(self, body: dict) -> dict:
        cap = body.get("max_completion_tokens") or body.get("max_tokens") or 10**9
        out = min(self.completion_tokens, cap)
        # ~4 chars/token + 3 per message, like real tokenizers (our estimate is deliberately higher)
        pt = sum(math.ceil(len(str(m.get("content") or "")) / 4) + 3 for m in body.get("messages", []))
        return {"prompt_tokens": pt, "completion_tokens": out, "total_tokens": pt + out}

    async def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.calls.append(body)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail_status:
            return httpx.Response(self.fail_status, json={"error": {"message": "upstream broke"}})
        if body.get("stream"):
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=_Stream(self, body))
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "model": body["model"],
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                "usage": self.usage(body),
            },
        )

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


class _Stream(httpx.AsyncByteStream):
    def __init__(self, up: MockUpstream, body: dict):
        self.up, self.body = up, body

    async def __aiter__(self):
        for i in range(self.up.stream_chunks):
            if self.up.chunk_delay:
                await asyncio.sleep(self.up.chunk_delay)
            chunk = {"id": "c", "object": "chat.completion.chunk", "choices": [{"index": 0, "delta": {"content": f"tok{i} "}}]}
            yield f"data: {json.dumps(chunk)}\n\n".encode()
        if (self.body.get("stream_options") or {}).get("include_usage"):
            yield f"data: {json.dumps({'id': 'c', 'choices': [], 'usage': self.up.usage(self.body)})}\n\n".encode()
        yield b"data: [DONE]\n\n"
