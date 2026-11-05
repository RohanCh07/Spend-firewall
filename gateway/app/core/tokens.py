"""Cheap pre-call token estimation.

Runs on every request, so it must be fast. ~4 chars/token is a deliberate
over-estimate for English and code, plus per-message overhead. The estimate only
sizes the *reservation*; the real cost from the provider's `usage` replaces it.
"""

import json
from typing import Any

CHARS_PER_TOKEN = 3.5
PER_MESSAGE_OVERHEAD = 4


def _text_of(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # multimodal parts
        return " ".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return json.dumps(content)


def estimate_input_tokens(body: dict[str, Any]) -> int:
    chars = 0
    messages = body.get("messages") or []
    for m in messages:
        chars += len(_text_of(m.get("content")))
        if m.get("tool_calls"):
            chars += len(json.dumps(m["tool_calls"]))
    if body.get("tools"):
        chars += len(json.dumps(body["tools"]))
    return int(chars / CHARS_PER_TOKEN) + PER_MESSAGE_OVERHEAD * len(messages) + 3


def requested_max_output(body: dict[str, Any]) -> int | None:
    for k in ("max_completion_tokens", "max_tokens"):
        v = body.get(k)
        if isinstance(v, int) and v > 0:
            return v
    return None
