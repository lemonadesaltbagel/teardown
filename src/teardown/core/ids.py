"""Canonical JSON and content-addressed identifiers.

Every immutable record is identified by ``<prefix>_<sha256 of its canonical semantic projection>``. A record whose
stored id does not match its content is rejected as tampered.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> bytes:
    """Byte-stable JSON: sorted keys, no insignificant whitespace, UTF-8."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_default).encode()


def _default(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    raise TypeError(f"not JSON-serializable: {type(value).__name__}")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def content_id(prefix: str, payload: Any) -> str:
    return f"{prefix}_{sha256_hex(canonical_json(payload))}"
