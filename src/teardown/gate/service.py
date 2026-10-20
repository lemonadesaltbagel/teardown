"""The gate's verifier as a small HTTP service, so the clean side never needs a path into the dirty workspace.

Endpoints (JSON):

    GET  /spec            latest released spec (what get_spec returns)
    POST /verify          {"clone": target spec, "adapter": {...}?} -> abstract verdict
    POST /tickets         {"question": str} -> {"ticket": id}
    GET  /tickets/<id>    ticket status and gate-checked answer

Bind it to an address only the clean runtime can reach. An optional bearer token is required on every request.
Phase 3 deployments run this inside the dirty zone and give the clean container only its URL.
"""

from __future__ import annotations

import hmac
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from teardown.mcp.clean_server import CleanRoom


def serve(room: CleanRoom, host: str = "127.0.0.1", port: int = 0, token: str | None = None) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _authorized(self) -> bool:
            if not token:
                return True
            given = self.headers.get("Authorization", "")
            return hmac.compare_digest(given, f"Bearer {token}")

        def _send(self, code: int, body: Any) -> None:
            data = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(length) or b"{}")

        def do_GET(self):  # noqa: N802 - http.server API
            if not self._authorized():
                return self._send(401, {"error": "unauthorized"})
            try:
                if self.path == "/spec":
                    return self._send(200, room.get_spec())
                if self.path.startswith("/tickets/"):
                    return self._send(200, room.get_ticket(self.path.rsplit("/", 1)[1]))
                return self._send(404, {"error": "not found"})
            except (KeyError, ValueError, FileNotFoundError) as exc:
                return self._send(400, {"error": str(exc)})

        def do_POST(self):  # noqa: N802 - http.server API
            if not self._authorized():
                return self._send(401, {"error": "unauthorized"})
            try:
                body = self._body()
                if self.path == "/verify":
                    return self._send(200, room.verify_against_original(body["clone"], body.get("adapter")))
                if self.path == "/tickets":
                    return self._send(200, room.ask_question(body["question"]))
                return self._send(404, {"error": "not found"})
            except PermissionError as exc:  # budget exceeded, strict-mode refusals
                return self._send(403, {"error": str(exc)})
            except (KeyError, ValueError) as exc:
                return self._send(400, {"error": str(exc)})

    server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class RemoteCleanRoom:
    """Clean-side client with the same interface as :class:`CleanRoom`, backed by the gate service."""

    def __init__(self, url: str, token: str | None = None, timeout_s: float = 3600):
        self.url, self.token, self.timeout_s = url.rstrip("/"), token, timeout_s

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method,
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": f"Bearer {self.token}"} if self.token else {})})
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310 - configured gate URL
            return json.loads(resp.read())

    def get_spec(self, release_id: str | None = None) -> dict[str, Any]:
        return self._call("GET", "/spec")

    def list_unknowns(self) -> list[dict[str, Any]]:
        return self.get_spec()["spec"]["unknowns"]

    def ask_question(self, question: str) -> dict[str, Any]:
        return self._call("POST", "/tickets", {"question": question})

    def get_ticket(self, ticket_id: str) -> dict[str, Any]:
        return self._call("GET", f"/tickets/{ticket_id}")

    def verify_against_original(self, clone_target: str, adapter: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._call("POST", "/verify", {"clone": clone_target, "adapter": adapter})
