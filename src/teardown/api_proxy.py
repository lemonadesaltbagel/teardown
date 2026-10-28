"""An API-only front for a target that serves its UI and its API on the same port.

The clean side may call the original's backend API, but must never fetch the original's frontend (its scripts are
implementation). This proxy forwards only the given path prefixes (``/api``, ``/auth``, ...) to the backend and
answers 404 for everything else, so the kit's API address cannot serve the original's UI.

Run:  teardown api-proxy --listen 18090 --backend http://127.0.0.1:18080 --allow /api /auth /meta
then give the clean side ``--api http://127.0.0.1:18090`` (export-clean and cleanroom up).
"""

from __future__ import annotations

import argparse
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
       "transfer-encoding", "upgrade", "host", "content-length"}


def make_handler(backend: str, allow: list[str]):
    target = urlsplit(backend)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _forward(self) -> None:
            path = self.path.split("?", 1)[0]
            if not any(path == p or path.startswith(p.rstrip("/") + "/") for p in allow):
                body = b"not an API path"
                self.send_response(404)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            length = int(self.headers.get("Content-Length") or 0)
            data = self.rfile.read(length) if length else None
            conn = http.client.HTTPConnection(target.hostname, target.port or 80, timeout=60)
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
            conn.request(self.command, self.path, body=data, headers=headers)
            resp = conn.getresponse()
            payload = resp.read()
            self.send_response(resp.status, resp.reason)
            for k, v in resp.getheaders():
                if k.lower() not in HOP:
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)
            conn.close()

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_HEAD = _forward

        def log_message(self, *args) -> None:  # quiet
            pass

    return Handler


def serve(listen: int, backend: str, allow: list[str]) -> ThreadingHTTPServer:
    """Start the proxy on 127.0.0.1:``listen`` (0: any free port) and return the server (call serve_forever)."""
    if not allow or not all(p.startswith("/") for p in allow):
        raise ValueError("--allow needs the API path prefixes, e.g. /api /auth")
    return ThreadingHTTPServer(("127.0.0.1", listen), make_handler(backend, allow))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", type=int, required=True)
    ap.add_argument("--backend", required=True)
    ap.add_argument("--allow", nargs="+", required=True)
    args = ap.parse_args(argv)
    serve(args.listen, args.backend, args.allow).serve_forever()


if __name__ == "__main__":
    main()
