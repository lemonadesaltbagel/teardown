"""teardown-clean: the only MCP server the clean-side implementer gets.

It reads gate-released specs and ticket answers, and forwards verification requests to the dirty-side verifier,
which returns abstract verdicts only. It has no tools that reach the target, the evidence store or the web.

Phase 0 runs the verifier in-process; Phase 3 moves it behind a network boundary so the clean process has no
filesystem path to dirty data at all. The tool surface stays the same.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from teardown.gate.gate import load_release

INSTRUCTIONS = (
    "You are implementing a feature from a behavioral specification. Build only from get_spec; do not search for "
    "or recall any existing product. Ask clarifying questions with ask_question. Check your implementation with "
    "verify_against_original, which reports which behaviors match, without revealing the original's internals."
)


class CleanRoom:
    def __init__(self, releases_dir: Path, tickets_dir: Path, verify: Callable[[str], dict[str, Any]]):
        self.releases_dir = Path(releases_dir)
        self.tickets_dir = Path(tickets_dir)
        self._verify = verify

    def get_spec(self, release_id: str | None = None) -> dict[str, Any]:
        rel = load_release(self.releases_dir, release_id)
        return {"release": rel.id, "codename": rel.codename, "previous": rel.previous, "spec": rel.spec}

    def list_unknowns(self) -> list[dict[str, Any]]:
        return load_release(self.releases_dir).spec["unknowns"]

    def ask_question(self, question: str) -> dict[str, Any]:
        ticket = {"id": f"tkt_{uuid.uuid4().hex[:16]}", "question": question, "status": "open", "answer": None}
        self.tickets_dir.mkdir(parents=True, exist_ok=True)
        (self.tickets_dir / f"{ticket['id']}.json").write_text(json.dumps(ticket, indent=1), encoding="utf-8")
        return {"ticket": ticket["id"], "status": "open"}

    def get_ticket(self, ticket_id: str) -> dict[str, Any]:
        if not ticket_id.startswith("tkt_") or "/" in ticket_id:
            raise ValueError("malformed ticket id")
        ticket = json.loads((self.tickets_dir / f"{ticket_id}.json").read_text(encoding="utf-8"))
        return {"ticket": ticket["id"], "status": ticket["status"], "answer": ticket.get("answer")}

    def verify_against_original(self, clone_target: str) -> dict[str, Any]:
        return self._verify(clone_target)


def build_clean_server(room: CleanRoom) -> MCPServer:
    server = MCPServer(name="teardown-clean", instructions=INSTRUCTIONS)

    @server.tool(description="Get the released behavioral specification (latest unless a release id is given).")
    def get_spec(release_id: str | None = None) -> dict[str, Any]:
        return room.get_spec(release_id)

    @server.tool(description="List the open questions the observer could not answer (missing coverage).")
    def list_unknowns() -> list[dict[str, Any]]:
        return room.list_unknowns()

    @server.tool(description="Ask the observer a behavioral question. Answers are gate-checked before you see them.")
    def ask_question(question: str) -> dict[str, Any]:
        return room.ask_question(question)

    @server.tool(description="Check whether a question you asked has been answered.")
    def get_ticket(ticket_id: str) -> dict[str, Any]:
        return room.get_ticket(ticket_id)

    @server.tool(
        description="Run the spec's conformance suite against your implementation and the original. Returns "
        "pass/fail/inconclusive per test with expected and observed abstract symbols only."
    )
    def verify_against_original(clone_target: str) -> dict[str, Any]:
        return room.verify_against_original(clone_target)

    return server
