"""Simulate a runaway agent and watch the firewall stop it.

The "agent" keeps calling the same search tool, gets "no results", and tries
again forever: the classic overnight loop. Run against the gateway with the
mock provider so it costs nothing:

    python runaway.py --base-url http://localhost:8080/v1 --key $BOOTSTRAP_ADMIN_KEY
"""

import argparse
import time
import uuid

from openai import APIStatusError, OpenAI


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://localhost:8080/v1")
    p.add_argument("--key", required=True)
    p.add_argument("--model", default="mock-model")
    p.add_argument("--max-iterations", type=int, default=1000)
    a = p.parse_args()

    session = f"runaway-{uuid.uuid4().hex[:8]}"
    client = OpenAI(base_url=a.base_url, api_key=a.key,
                    default_headers={"X-Agent-Id": "runaway-demo", "X-Session-Id": session})
    history = [{"role": "system", "content": "You are a file-finding agent."},
               {"role": "user", "content": "Find the quarterly report."}]
    spent, t0 = 0.0, time.time()
    print(f"session {session}")
    for i in range(a.max_iterations):
        try:
            raw = client.chat.completions.with_raw_response.create(model=a.model, messages=history, max_tokens=200)
        except APIStatusError as e:
            err = e.response.json().get("error", {})
            print(f"\nBLOCKED after {i} calls, {time.time() - t0:.1f}s, ${spent:.6f}: {err.get('type')}: {err.get('message')}")
            return
        spent += float(raw.headers.get("x-firewall-cost-usd", 0))
        print(f"call {i + 1}: ${spent:.6f}", end="\r")
        history += [
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": f"c{i}", "type": "function", "function": {"name": "search", "arguments": '{"q":"quarterly report"}'}}]},
            {"role": "tool", "tool_call_id": f"c{i}", "content": "no results"},
        ]
    print("\nNot stopped (is the gateway running with loop detection on?)")


if __name__ == "__main__":
    main()
