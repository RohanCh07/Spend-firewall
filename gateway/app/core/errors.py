from typing import Any

from fastapi.responses import JSONResponse


class FirewallError(Exception):
    """A decision or failure returned to the agent as an OpenAI-style error.

    `x-should-retry: false` tells the OpenAI SDKs not to auto-retry, so a blocked
    agent doesn't hammer the gateway.
    """

    def __init__(self, status: int, type_: str, message: str, retry: bool = False, **extra: Any):
        super().__init__(message)
        self.status = status
        self.type = type_
        self.message = message
        self.retry = retry
        self.extra = extra

    def response(self) -> JSONResponse:
        body = {"error": {"type": self.type, "code": self.type, "message": self.message, **self.extra}}
        headers = {"x-should-retry": "true" if self.retry else "false", "x-firewall-decision": self.type}
        return JSONResponse(body, status_code=self.status, headers=headers)


def unauthorized(msg: str = "Missing or invalid firewall API key") -> FirewallError:
    return FirewallError(401, "invalid_api_key", msg)
