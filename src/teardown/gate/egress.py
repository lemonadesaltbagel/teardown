"""Allowlisting egress proxy for the clean zone (stdlib only).

The clean workspace sits on an internal network with no route out; this proxy is its only peer that also has one.
It forwards HTTP CONNECT tunnels (HTTPS) and plain HTTP requests to listed ``host:port`` pairs only — typically
the model API, the gate, and (for web targets) the backend API the implementer may call — and refuses everything
else. Every attempt is logged as one JSON line: time, client, method, destination, allowed.

    teardown egress-proxy --allow api.anthropic.com:443 --allow host.docker.internal:8765 --log egress.jsonl
"""

from __future__ import annotations

import json
import select
import socket
import socketserver
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit


class EgressPolicy:
    def __init__(self, allow: list[str], log_path: str | Path | None = None):
        self.allow = {self._norm(a) for a in allow}
        self.log_path = Path(log_path) if log_path else None
        self._lock = threading.Lock()

    @staticmethod
    def _norm(hostport: str) -> tuple[str, int]:
        host, _, port = hostport.rpartition(":")
        if not host or not port.isdigit():
            raise ValueError(f"allow entries are host:port, got {hostport!r}")
        return host.lower().strip("[]"), int(port)

    def permits(self, host: str, port: int) -> bool:
        return (host.lower().strip("[]"), port) in self.allow

    def record(self, client: str, method: str, host: str, port: int, allowed: bool, note: str = "") -> None:
        entry = {"time": round(time.time(), 3), "client": client, "method": method, "host": host, "port": port,
                 "allowed": allowed, **({"note": note} if note else {})}
        line = json.dumps(entry, sort_keys=True)
        with self._lock:
            print(line, flush=True)
            if self.log_path:
                with self.log_path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")


def _pipe(a: socket.socket, b: socket.socket, idle_s: float = 300) -> None:
    sockets = [a, b]
    while True:
        ready, _, broken = select.select(sockets, [], sockets, idle_s)
        if broken or not ready:
            return
        for s in ready:
            data = s.recv(65536)
            if not data:
                return
            (b if s is a else a).sendall(data)


def make_handler(policy: EgressPolicy):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):  # the policy log is the record
            pass

        def _deny(self, host: str, port: int) -> None:
            policy.record(self.client_address[0], self.command, host, port, False)
            body = f"teardown egress: {host}:{port} is not allowed from the clean zone\n".encode()
            self.send_response(403)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

        def do_CONNECT(self):  # noqa: N802 - http.server API
            host, _, port = self.path.rpartition(":")
            port_n = int(port) if port.isdigit() else 443
            if not policy.permits(host, port_n):
                return self._deny(host, port_n)
            try:
                upstream = socket.create_connection((host, port_n), timeout=15)
            except OSError as exc:
                policy.record(self.client_address[0], "CONNECT", host, port_n, True, note=f"connect failed: {exc}")
                self.send_error(502)
                return
            policy.record(self.client_address[0], "CONNECT", host, port_n, True)
            self.send_response(200, "Connection established")
            self.end_headers()
            try:
                _pipe(self.connection, upstream)
            finally:
                upstream.close()
                self.close_connection = True

        def _forward(self):
            url = urlsplit(self.path)
            if not url.scheme or not url.hostname:
                return self._deny(self.headers.get("Host", "?"), 0)
            port = url.port or (443 if url.scheme == "https" else 80)
            if url.scheme != "http" or not policy.permits(url.hostname, port):
                return self._deny(url.hostname, port)
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            path = url.path or "/"
            if url.query:
                path += "?" + url.query
            headers = {k: v for k, v in self.headers.items()
                       if k.lower() not in ("proxy-connection", "proxy-authorization", "connection", "keep-alive")}
            import http.client

            conn = http.client.HTTPConnection(url.hostname, port, timeout=3600)
            try:
                conn.request(self.command, path, body=body or None, headers=headers)
                resp = conn.getresponse()
                data = resp.read()
            except OSError as exc:
                policy.record(self.client_address[0], self.command, url.hostname, port, True,
                              note=f"upstream failed: {exc}")
                self.send_error(502)
                return
            finally:
                conn.close()
            policy.record(self.client_address[0], self.command, url.hostname, port, True)
            self.send_response(resp.status, resp.reason)
            for k, v in resp.getheaders():
                if k.lower() not in ("transfer-encoding", "connection", "content-length"):
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
            self.close_connection = True

        do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _forward  # noqa: N815

    return Handler


class _Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(policy: EgressPolicy, host: str = "0.0.0.0", port: int = 3128) -> _Server:  # noqa: S104 - proxy listens on its own network
    server = _Server((host, port), make_handler(policy))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
