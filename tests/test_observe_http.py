"""The observe MCP server over HTTP: token required, Host header checked, tools reachable."""

from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

from teardown.project import Project


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _list_tools(url: str, token: str) -> list[str]:
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

    async def go():
        async with (create_mcp_http_client(headers={"Authorization": f"Bearer {token}"}) as http,
                    streamable_http_client(url, http_client=http) as streams,
                    ClientSession(streams[0], streams[1]) as session):
            await session.initialize()
            return [t.name for t in (await session.list_tools()).tools]

    return asyncio.run(go())


def test_observe_over_http_requires_the_token_and_serves_the_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")  # a system proxy must not intercept loopback
    project = tmp_path / "p"
    Project(project).open_target("fake:signup-a", purpose="research")
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-m", "teardown.cli", "observe", "--project", str(project),
                             "--port", str(port), "--token", "s3cret"], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}/mcp"
    try:
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        try:
            urllib.request.urlopen(urllib.request.Request(url, method="POST", data=b"{}"), timeout=5)
            raise AssertionError("no token was accepted")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        tools = _list_tools(url, "s3cret")
        assert {"open_target", "run_sequence", "check_rules", "compile_spec", "release_spec"} <= set(tools)
        assert "approve_findings" not in tools
        bad_host = urllib.request.Request(url, method="POST", data=b"{}", headers={
            "Authorization": "Bearer s3cret", "Host": "evil.example:1", "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"})
        try:
            urllib.request.urlopen(bad_host, timeout=5)
            raise AssertionError("foreign Host header was accepted")
        except urllib.error.HTTPError as exc:
            assert exc.code in (400, 403, 421)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
