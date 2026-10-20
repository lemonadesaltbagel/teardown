"""Filesystem workspace: an immutable object store plus the mutable claim/unknown ledgers.

Layout under the workspace root::

    objects/<prefix>/<id>.json   content-addressed records (verified on read)
    packs/<prefix>.jsonl         high-volume records (evidence, traces), appended; payloads deduplicated in
    packs/blobs.jsonl            ... a content-addressed blob pack
    ledger/claims.json           claim states, keyed by claim id
    ledger/unknowns.json         unknown states, keyed by unknown id
    corpus/strings.jsonl         every string value observed in behavior evidence (gate reference corpus)
    audit.jsonl                  hash-chained audit log (see teardown.audit)

The dirty side owns a workspace. The clean side never gets a path to it.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import TypeVar

from teardown.core.ids import canonical_json, sha256_hex
from teardown.core.model import Claim, ContentAddressed, Evidence, Unknown

T = TypeVar("T", bound=ContentAddressed)

PACKED_PREFIXES = {"ev", "tr"}


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class Workspace:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        for sub in ("objects", "packs", "ledger", "corpus"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)
        self._packs: dict[str, _Pack] = {}
        self._blobs = _Pack(self.root / "packs" / "blobs.jsonl")
        self._corpus_seen: set[str] | None = None

    # -- immutable objects -------------------------------------------------------------------------------------
    def put(self, record: ContentAddressed) -> str:
        if record.PREFIX in PACKED_PREFIXES:
            pack = self._pack(record.PREFIX)
            if record.id not in pack:
                data = record.model_dump(mode="json")
                if isinstance(record, Evidence):
                    blob = canonical_json(data.pop("payload"))
                    data["payload"] = None
                    ref = sha256_hex(blob)
                    if ref not in self._blobs:
                        self._blobs.append(ref, blob.decode())
                    data["payload_ref"] = ref
                pack.append(record.id, json.dumps(data, ensure_ascii=False))
        else:
            path = self._object_path(record.id)
            if not path.exists():
                _atomic_write(path, record.model_dump_json())
        if isinstance(record, Evidence) and record.tier == "behavior":
            self._add_to_corpus(record)
        return record.id

    def get(self, record_id: str, cls: type[T]) -> T:
        prefix = self._prefix(record_id)
        if prefix in PACKED_PREFIXES:
            line = self._pack(prefix).get(record_id)
            if line is None:
                raise KeyError(record_id)
            data = json.loads(line)
            ref = data.pop("payload_ref", None)
            if ref is not None:
                blob = self._blobs.get(ref)
                if blob is None or sha256_hex(blob.encode()) != ref:
                    raise KeyError(f"payload blob {ref} missing or corrupt")
                data["payload"] = json.loads(blob)
            return cls.model_validate(data)
        path = self._object_path(record_id)
        if not path.exists():
            raise KeyError(record_id)
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def has(self, record_id: str) -> bool:
        prefix = self._prefix(record_id)
        if prefix in PACKED_PREFIXES:
            return record_id in self._pack(prefix)
        return self._object_path(record_id).exists()

    def iter_objects(self, prefix: str, cls: type[T]) -> Iterator[T]:
        if prefix in PACKED_PREFIXES:
            for record_id in self._pack(prefix).ids():
                yield self.get(record_id, cls)
            return
        folder = self.root / "objects" / prefix
        if folder.exists():
            for path in sorted(folder.glob("*.json")):
                yield cls.model_validate_json(path.read_text(encoding="utf-8"))

    def _pack(self, prefix: str) -> _Pack:
        if prefix not in self._packs:
            self._packs[prefix] = _Pack(self.root / "packs" / f"{prefix}.jsonl")
        return self._packs[prefix]

    @staticmethod
    def _prefix(record_id: str) -> str:
        prefix, _, rest = record_id.partition("_")
        if not prefix or not rest or "/" in record_id or ".." in record_id:
            raise ValueError(f"malformed record id: {record_id!r}")
        return prefix

    def _object_path(self, record_id: str) -> Path:
        return self.root / "objects" / self._prefix(record_id) / f"{record_id}.json"

    # -- reference corpus for the gate -------------------------------------------------------------------------
    def _add_to_corpus(self, evidence: Evidence) -> None:
        if self._corpus_seen is None:
            self._corpus_seen = set(self.corpus())
        new = sorted({s for s in _strings(evidence.payload) if s.strip()} - self._corpus_seen)
        if not new:
            return
        self._corpus_seen.update(new)
        with (self.root / "corpus" / "strings.jsonl").open("a", encoding="utf-8") as fh:
            for s in new:
                fh.write(json.dumps({"evidence": evidence.id, "text": s}, ensure_ascii=False) + "\n")

    def corpus(self) -> list[str]:
        path = self.root / "corpus" / "strings.jsonl"
        if not path.exists():
            return []
        seen: dict[str, None] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            seen.setdefault(json.loads(line)["text"], None)
        return list(seen)

    # -- mutable ledgers ---------------------------------------------------------------------------------------
    def load_claims(self) -> dict[str, Claim]:
        return {k: Claim.model_validate(v) for k, v in self._read_ledger("claims").items()}

    def save_claims(self, claims: dict[str, Claim]) -> None:
        self._write_ledger("claims", {k: v.model_dump(mode="json") for k, v in claims.items()})

    def load_unknowns(self) -> dict[str, Unknown]:
        return {k: Unknown.model_validate(v) for k, v in self._read_ledger("unknowns").items()}

    def save_unknowns(self, unknowns: dict[str, Unknown]) -> None:
        self._write_ledger("unknowns", {k: v.model_dump(mode="json") for k, v in unknowns.items()})

    def _read_ledger(self, name: str) -> dict:
        path = self.root / "ledger" / f"{name}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def _write_ledger(self, name: str, data: dict) -> None:
        _atomic_write(self.root / "ledger" / f"{name}.json", json.dumps(data, indent=1, sort_keys=True))


def _strings(value) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _strings(k)
            yield from _strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v)


class _Pack:
    """Append-only JSONL pack: one ``{"id": ..., "data": ...}`` line per record, indexed in memory on first use."""

    def __init__(self, path: Path):
        self.path = path
        self._index: dict[str, int] | None = None
        self._fh = None

    def _load(self) -> dict[str, int]:
        if self._index is None:
            self._index = {}
            if self.path.exists():
                with self.path.open("rb") as fh:
                    offset = 0
                    for raw in fh:
                        self._index[json.loads(raw)["id"]] = offset
                        offset += len(raw)
        return self._index

    def __contains__(self, record_id: str) -> bool:
        return record_id in self._load()

    def ids(self) -> list[str]:
        return list(self._load())

    def append(self, record_id: str, data: str) -> None:
        index = self._load()
        if self._fh is None:
            self._fh = self.path.open("ab")
        line = (json.dumps({"id": record_id, "data": data}, ensure_ascii=False) + "\n").encode()
        index[record_id] = self._fh.tell()
        self._fh.write(line)
        self._fh.flush()

    def get(self, record_id: str) -> str | None:
        offset = self._load().get(record_id)
        if offset is None:
            return None
        with self.path.open("rb") as fh:
            fh.seek(offset)
            return json.loads(fh.readline())["data"]
