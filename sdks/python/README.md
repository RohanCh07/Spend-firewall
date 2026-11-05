# spendfirewall (Python)

```bash
pip install "spendfirewall[openai]"
export SPENDFIREWALL_URL=http://localhost:8080 SPENDFIREWALL_API_KEY=sf-... SPENDFIREWALL_AGENT_ID=research-bot
```

```python
from spendfirewall import Firewall, FirewallBlocked

fw = Firewall()
with fw.session(customer_id="acme") as s:      # one X-Session-Id per agent run
    client = s.openai()                         # openai.OpenAI pointed at the gateway
    try:
        while True:
            client.chat.completions.create(model="gpt-4o-mini", messages=history)
            ...
    except FirewallBlocked as e:                # budget_exceeded / loop_detected / session_killed
        print("stopped by firewall:", e.type)
```

Other frameworks (LangGraph, CrewAI, OpenAI Agents SDK, LiteLLM): pass
`base_url=fw.base_url`, `api_key=fw.api_key` and `default_headers=s.headers`
to whatever OpenAI-compatible client they take. `AdminClient` (`fw.admin(key)`)
can kill sessions, read budgets and sync policy files from scripts.
