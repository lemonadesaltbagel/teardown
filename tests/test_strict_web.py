"""The strict gate end to end on a web target, as one developer runs it.

The observer works only through the observe MCP server over HTTP, as the confined observer does. It cannot
approve or release on its own. The person at the gate reviews and approves with `teardown approve` in a real
pseudo-terminal, typing the codename shown in the prompt. Then the release goes out, the kit is exported and
the audit log records who approved what.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import select
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright")

from teardown.drivers.web.driver import EXAMPLES, LocalSite  # noqa: E402
from teardown.project import Project  # noqa: E402

MANUAL = ("Press the load button to fetch the latest quotes from the server and show them in a list.\n\n"
          "If the server fails, the page tells you so and leaves the list empty until you try again.")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "teardown.cli", *argv], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=300)


def _at_terminal(*argv: str, typed: str | None = None) -> tuple[int, str]:
    """Run a CLI command in a pseudo-terminal and answer its codename prompt as a person would: read the
    codename from the prompt and type it (or ``typed`` instead)."""
    master, slave = os.openpty()
    proc = subprocess.Popen([sys.executable, "-m", "teardown.cli", *argv], stdin=slave, stdout=slave,
                            stderr=slave, close_fds=True)
    os.close(slave)
    out = b""
    answered = False
    deadline = time.time() + 300
    while time.time() < deadline:
        ready, _, _ = select.select([master], [], [], 0.5)
        if ready:
            try:
                chunk = os.read(master, 4096)
            except OSError:  # the terminal closes when the command exits
                break
            if not chunk:
                break
            out += chunk
        if not answered and (m := re.search(rb"Type the codename '([^']+)' to confirm: ", out)):
            os.write(master, ((typed or m.group(1).decode()) + "\n").encode())
            answered = True
        if proc.poll() is not None and not ready:
            break
    os.close(master)
    return proc.wait(timeout=30), out.decode(errors="replace")


class Observer:
    """The confined observer's view: MCP tools over HTTP with a bearer token, nothing else."""

    def __init__(self, url: str, token: str):
        self.url, self.token = url, token

    def __call__(self, tool: str, **args):
        from mcp.client.session import ClientSession
        from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

        async def go():
            async with (create_mcp_http_client(headers={"Authorization": f"Bearer {self.token}"}) as http,
                        streamable_http_client(self.url, http_client=http) as streams,
                        ClientSession(streams[0], streams[1]) as session):
                await session.initialize()
                if tool == "list_tools":
                    return [t.name for t in (await session.list_tools()).tools]
                result = await session.call_tool(tool, args)
                return result.is_error, "".join(getattr(c, "text", "") for c in result.content)

        if tool == "list_tools":
            return asyncio.run(go())
        failed, text = asyncio.run(go())
        if failed:  # raised out here: inside the client's task group it would arrive as an exception group
            raise RuntimeError(text)
        return json.loads(text) if text[:1] in "[{" else text


def test_strict_web_loop_one_developer(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    site = LocalSite(EXAMPLES)
    project_dir = tmp_path / "p"
    Project(project_dir)  # the person creates the project; the observer opens the target through MCP
    port = _free_port()
    server = subprocess.Popen([sys.executable, "-m", "teardown.cli", "observe", "--project", str(project_dir),
                               "--port", str(port), "--token", "obs-token"], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    observer = Observer(f"http://127.0.0.1:{port}/mcp", "obs-token")
    try:
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)

        # -- the observer's side ------------------------------------------------------------------------------
        tools = observer("list_tools")
        assert not {t for t in tools if t.startswith("approve_findings") or "coverage_gaps" in t}
        observer("open_target", target="web:" + site.url("fetcher.html"), purpose="research", strict=True,
                 real_names=["Fetcher"])
        observer("ingest_docs", source="manual", text=MANUAL)
        observer("define_actions", actions={
            "load": {"op": "click", "role": "button", "name": "Load quotes"},
            "broken": {"op": "fault", "fault": {"path": "/quotes.json", "mode": "status", "status": 500}},
            "offline": {"op": "fault", "fault": {"path": "/quotes.json", "mode": "abort"}}})
        observer("check_rules", feature="quotes", rules=[
            {"statement": "Loading lists the quotes and shows no alert.", "checks": [
                {"kind": "outcome", "a": {"actions": ["load"]}, "expect": {"alerts": []}}]},
            # copied from the manual: a prose finding only a person may let through
            {"statement": "If the server fails, the page tells you so and leaves the list empty until you try "
                          "again.", "checks": [
                {"kind": "outcome", "a": {"actions": ["broken", "load"]}, "expect": {"alerts": ["Server error 500"]}}]},
            {"statement": "Without a network, loading reports that it is offline.", "checks": [
                {"kind": "outcome", "a": {"actions": ["offline", "load"]}, "expect": {"alerts": ["Offline"]}}]}])
        observer("coverage", feature="quotes")
        draft = observer("compile_spec", feature="quotes")["draft"]
        with pytest.raises(RuntimeError, match="coverage|approv|finding"):  # nothing approved yet
            observer("release_spec", draft_id=draft)
        with pytest.raises(RuntimeError, match="strict"):  # a name passed by the agent is not an approval
            observer("add_quote", text="Server error 500", compat_reason="test-oracle", approved_by="me")
        with pytest.raises(RuntimeError):
            observer("release_spec", draft_id=draft, accept_gaps="the agent says so")

        # -- the person at the gate ---------------------------------------------------------------------------
        assert _cli("approve", "--project", str(project_dir), "--feature", "quotes", "--by", "agent",
                    "--class", "expected-output", "--reason", "test-oracle").returncode == 2  # no terminal
        review = json.loads(_cli("review", "--project", str(project_dir), "--feature", "quotes", "--json").stdout)
        assert review["mode"] == "strict" and review["unapproved"] > 0
        prose = [f["id"] for f in review["prose"] if not f["approved"]]
        assert prose, "the copied manual sentence is a prose finding"

        code, out = _at_terminal("approve", "--project", str(project_dir), "--feature", "quotes", "--by",
                                 "dev@example.com", "--class", "expected-output", "--reason", "test-oracle",
                                 typed="wrong-codename")
        assert code == 1 and "nothing recorded" in out
        for cls in sorted({g["cls"] for g in review["groups"]} - {"prose"}):
            code, out = _at_terminal("approve", "--project", str(project_dir), "--feature", "quotes", "--by",
                                     "dev@example.com", "--class", cls, "--reason", "test-oracle")
            assert code == 0, out
        code, out = _at_terminal("approve", "--project", str(project_dir), "--feature", "quotes", "--by",
                                 "dev@example.com", "--class", "expected-output", "--reason", "test-oracle")
        assert code == 0 and "already approved by dev@example.com" in out  # a repeat says so, not just "0"
        with pytest.raises(RuntimeError):  # prose still blocks
            observer("release_spec", draft_id=observer("compile_spec", feature="quotes")["draft"])
        code, out = _at_terminal("approve", "--project", str(project_dir), "--feature", "quotes", "--by",
                                 "dev@example.com", "--finding", *prose, "--reason", "user-required",
                                 "--note", "paraphrase would lose nothing; accepted for the test")
        assert code == 0, out
        # a rules-only draft: the reviewer must still see the coverage gap that release checks
        assert json.loads(_cli("review", "--project", str(project_dir), "--feature", "quotes", "--json").stdout)[
            "coverage_unacknowledged"] == ["data state: list Quotes: one", "fault GET /quotes.json malformed"]
        code, out = _at_terminal("approve", "--project", str(project_dir), "--feature", "quotes", "--by",
                                 "dev@example.com", "--coverage", "--note", "one-quote and malformed states out of scope")
        assert code == 0, out
        final = json.loads(_cli("review", "--project", str(project_dir), "--feature", "quotes", "--json").stdout)
        assert final["unapproved"] == 0 and not final.get("coverage_unacknowledged")

        # -- release, export, audit ---------------------------------------------------------------------------
        released = observer("release_spec", draft_id=observer("compile_spec", feature="quotes")["draft"])
        assert released["mode"] == "strict"
        kit = tmp_path / "kit"
        assert _cli("export-clean", "--project", str(project_dir), "--out", str(kit)).returncode == 0
        assert "Fetcher" not in "".join(p.read_text(errors="ignore") for p in kit.rglob("*") if p.is_file())
        assert _cli("audit-verify", "--project", str(project_dir)).returncode == 0
        log = (project_dir / "audit.jsonl").read_text()
        assert "dev@example.com" in log and '"agent"' not in log
    finally:
        server.terminate()
        server.wait(timeout=10)
        site.close()
