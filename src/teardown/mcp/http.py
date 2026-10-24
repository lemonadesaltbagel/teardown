"""Serve an MCP server over streamable HTTP with a bearer token (for agents confined in a container).

The agent reaches it through the room's egress proxy as ``host.docker.internal``; DNS-rebinding protection stays on
with exactly the hosts the room uses.
"""

from __future__ import annotations

import hmac
from typing import Any


def bearer_guard(app: Any, token: str):
    """ASGI wrapper: every HTTP request needs ``Authorization: Bearer <token>``."""
    expected = f"Bearer {token}".encode()

    async def guarded(scope, receive, send):
        if scope["type"] == "http":
            auth = dict(scope.get("headers") or []).get(b"authorization", b"")
            if not hmac.compare_digest(auth, expected):
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"text/plain")]})
                await send({"type": "http.response.body", "body": b"unauthorized"})
                return
        await app(scope, receive, send)

    return guarded


def serve_http(server, *, host: str, port: int, token: str, allowed_hosts: list[str]) -> None:
    import uvicorn
    from mcp.server.transport_security import TransportSecuritySettings

    security = TransportSecuritySettings(enable_dns_rebinding_protection=True,
                                         allowed_hosts=[f"{h}:{port}" for h in allowed_hosts],
                                         allowed_origins=[])
    app = server.streamable_http_app(transport_security=security, host=host)
    uvicorn.run(bearer_guard(app, token), host=host, port=port, log_level="warning")
