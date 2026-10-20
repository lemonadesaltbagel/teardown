"""Append-only, hash-chained audit log of in-toto v1 statements.

Each line is ``{"seq", "prev", "statement", "digest"}`` where ``digest = sha256(canonical(seq, prev, statement))``.
Editing, removing or reordering any line breaks :meth:`AuditLog.verify`. DSSE signing and external checkpoint
anchoring (RFC 3161 / Rekor) come in Phase 3; the chain format does not change.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from teardown.core.ids import canonical_json, sha256_hex

STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_BASE = "https://teardown.dev/attestation"
GENESIS = "0" * 64


class AuditChainBroken(ValueError):
    pass


def predicate_type(name: str) -> str:
    return f"{PREDICATE_BASE}/{name}/v0.1"


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, predicate: str, subjects: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        """``subjects`` maps a name to its sha256 hex digest (ids are converted by stripping their prefix)."""
        seq, prev = self._tail()
        statement = {
            "_type": STATEMENT_TYPE,
            "subject": [{"name": n, "digest": {"sha256": _hex(d)}} for n, d in sorted(subjects.items())],
            "predicateType": predicate_type(predicate),
            "predicate": body,
        }
        entry = {"seq": seq, "prev": prev, "statement": statement}
        entry["digest"] = sha256_hex(canonical_json(entry))
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        return entry

    def entries(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def verify(self) -> int:
        """Check the whole chain; return the number of entries."""
        prev = GENESIS
        entries = self.entries()
        for i, entry in enumerate(entries):
            body = {k: entry[k] for k in ("seq", "prev", "statement")}
            if entry["seq"] != i or entry["prev"] != prev or sha256_hex(canonical_json(body)) != entry["digest"]:
                raise AuditChainBroken(f"audit chain broken at entry {i}")
            prev = entry["digest"]
        return len(entries)

    def _tail(self) -> tuple[int, str]:
        entries = self.entries()
        return (len(entries), entries[-1]["digest"]) if entries else (0, GENESIS)


def _hex(digest_or_id: str) -> str:
    return digest_or_id.rsplit("_", 1)[-1]
