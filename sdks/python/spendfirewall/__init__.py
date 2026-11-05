"""Spend Firewall Python SDK.

    from spendfirewall import Firewall

    fw = Firewall()                      # reads SPENDFIREWALL_URL / _API_KEY / _AGENT_ID from env
    with fw.session() as s:              # one X-Session-Id for this agent run
        client = s.openai()              # an openai.OpenAI pointed at the gateway
        client.chat.completions.create(model="gpt-4o-mini", messages=[...])

Blocks (budget, loop, kill switch) raise `FirewallBlocked` when you use
`s.openai()`, so an agent loop can stop cleanly instead of retrying.
"""

from .client import AdminClient, Firewall, FirewallSession, headers, new_session_id
from .errors import BLOCK_TYPES, FirewallBlocked, is_firewall_block

__all__ = [
    "AdminClient",
    "BLOCK_TYPES",
    "Firewall",
    "FirewallBlocked",
    "FirewallSession",
    "headers",
    "is_firewall_block",
    "new_session_id",
]
__version__ = "0.1.0"
