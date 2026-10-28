"""The API-only front for targets that serve their UI and API on one port (found on Flipt: the clean room's isolation
check caught that allowing the API also let the implementer fetch the original's frontend)."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from teardown.api_proxy import serve


class Backend(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body: bytes, kind: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/api/"):
            return self._send(json.dumps({"path": self.path}).encode(), "application/json")
        return self._send(b"<script src='/assets/app.js'></script>", "text/html")

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers["Content-Length"]))
        return self._send(body, "application/json")


def test_the_api_passes_and_the_frontend_does_not():
    backend = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
    threading.Thread(target=backend.serve_forever, daemon=True).start()
    proxy = serve(0, f"http://127.0.0.1:{backend.server_port}", ["/api"])
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{proxy.server_port}"
    try:
        assert json.load(urllib.request.urlopen(f"{base}/api/items?page=2")) == {"path": "/api/items?page=2"}
        posted = urllib.request.Request(f"{base}/api/items", data=b'{"name": "x"}', method="POST",
                                        headers={"Content-Type": "application/json"})
        assert json.load(urllib.request.urlopen(posted)) == {"name": "x"}
        for ui in ("/", "/assets/app.js", "/apiary"):  # the frontend, and a prefix that is not a path segment
            with pytest.raises(urllib.error.HTTPError) as refused:
                urllib.request.urlopen(base + ui)
            assert refused.value.code == 404
    finally:
        proxy.shutdown()
        backend.shutdown()
    with pytest.raises(ValueError):
        serve(0, "http://127.0.0.1:9", ["api"])
