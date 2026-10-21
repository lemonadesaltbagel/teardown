from __future__ import annotations

import json

import pytest

from teardown.drivers.web.driver import EXAMPLES, LocalSite
from teardown.gate.egress import EgressPolicy, serve


@pytest.fixture()
def site():
    s = LocalSite(EXAMPLES)
    yield s
    s.close()


def _via(proxy_port: int, url: str) -> int:
    """Status of a plain-HTTP request sent through the proxy (raw socket: urllib bypasses proxies for loopback)."""
    import socket

    with socket.create_connection(("127.0.0.1", proxy_port), timeout=10) as s:
        s.sendall(f"GET {url} HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n".encode())
        return int(s.recv(100).split(b" ")[1])


def test_egress_forwards_only_allowed_destinations_and_logs_every_attempt(site, tmp_path):
    port = int(site.url("").rsplit(":", 1)[1].strip("/"))
    log = tmp_path / "egress.jsonl"
    server = serve(EgressPolicy([f"127.0.0.1:{port}"], log), "127.0.0.1", 0)
    try:
        proxy = server.server_address[1]
        assert _via(proxy, f"http://127.0.0.1:{port}/quotes.json") == 200
        assert _via(proxy, f"http://localhost:{port}/quotes.json") == 403  # same server, other name: not listed
        assert _via(proxy, "http://127.0.0.1:9/") == 403  # listed host, unlisted port
        entries = [json.loads(line) for line in log.read_text().splitlines()]
        assert [(e["host"], e["allowed"]) for e in entries] == [("127.0.0.1", True), ("localhost", False),
                                                               ("127.0.0.1", False)]
    finally:
        server.shutdown()


def test_egress_tunnels_connect_only_to_allowed_hosts(tmp_path):
    import socket

    server = serve(EgressPolicy(["127.0.0.1:1"]), "127.0.0.1", 0)
    try:
        with socket.create_connection(("127.0.0.1", server.server_address[1]), timeout=5) as s:
            s.sendall(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n")
            assert s.recv(200).split(b" ")[1] == b"403"
    finally:
        server.shutdown()

    with pytest.raises(ValueError):
        EgressPolicy(["no-port"])
