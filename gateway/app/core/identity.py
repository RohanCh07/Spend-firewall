from dataclasses import dataclass

from fastapi import Request

HEADER_AGENT = "x-agent-id"
HEADER_SESSION = "x-session-id"
HEADER_CUSTOMER = "x-customer-id"
MAX_ID_LEN = 128


@dataclass(frozen=True)
class Identity:
    agent_id: str | None
    session_id: str | None
    customer_id: str | None

    def get(self, scope: str) -> str | None:
        return {"agent": self.agent_id, "session": self.session_id, "customer": self.customer_id}.get(scope)


def _clean(v: str | None) -> str | None:
    if not v:
        return None
    v = v.strip()[:MAX_ID_LEN]
    return v or None


def identity_from(request: Request) -> Identity:
    h = request.headers
    return Identity(_clean(h.get(HEADER_AGENT)), _clean(h.get(HEADER_SESSION)), _clean(h.get(HEADER_CUSTOMER)))
