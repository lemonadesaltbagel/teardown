"""Field probing for UI forms: equivalence classes, a length boundary search, and per-class outcomes.

A field probe is an episode: reset, the actions that reach the form (``prefix``), fill the field with one class's
value, then the submit action. The outcome is the subset of the resulting observation that decides acceptance:
route, headings, alerts and invalid controls. Classes found at the length boundary are returned so they can be
added to the learning alphabet (in the web spike, a max-length difference was only detectable once such classes
were inputs).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from teardown.drivers.session import ObservationSession
from teardown.engine.mapper import describe_symbol

TEXT = {
    "empty": "", "space": " ", "padded": "  word  ", "single_char": "a", "typical": "hello world",
    "digits": "12345", "unicode": "héllo ✓", "emoji": "\U0001f600", "html": "<b>x</b>",
    "sql_like": "' OR 1=1 --", "newline": "a\nb", "len_100": "a" * 100, "len_1000": "a" * 1000,
}
EMAIL = {
    "empty": "", "valid": "jane.doe@example.com", "no_at": "jane.example.com", "at_only": "@",
    "no_local": "@example.com", "no_domain": "jane@", "double_at": "jane@@example.com",
    "inner_space": "jane doe@example.com", "padded": "  jane@example.com  ", "plus_tag": "jane+tag@example.com",
    "unicode_local": "jäne@example.com", "uppercase": "JANE@EXAMPLE.COM", "no_tld": "jane@example",
    "len_100": "a" * 88 + "@example.com",
}
PASSWORD = {
    "empty": "", "short": "abc", "seven_with_digit": "abcdef1", "eight_no_digit": "abcdefgh",
    "eight_with_digit": "abcdefg1", "digits_only": "12345678", "spaces": "pass word 12", "unicode": "pässwörd1",
    "len_100": "a1" * 50,
}
NUMBER = {"empty": "", "zero": "0", "one": "1", "negative": "-1", "decimal": "1.5", "huge": "99999999999999999999",
          "text": "abc", "exponent": "1e3", "padded": " 7 "}
CLASSES = {"text": TEXT, "email": EMAIL, "password": PASSWORD, "number": NUMBER}

OUTCOME_KEYS = ("path", "headings", "alerts", "invalid", "text", "network")


def layer_of(result: dict[str, Any]) -> str:
    """Where a refusal happened: no API request at all -> client; an API 4xx -> server; else unknown."""
    if result.get("value") in ("DISABLED", "NA") or not result.get("network"):
        return "client"
    statuses = [int(x.rsplit(" ", 1)[1]) for x in result["network"] if x.rsplit(" ", 1)[1].isdigit()]
    if any(400 <= s < 500 for s in statuses):
        return "server"
    return "unknown"


def outcome(symbol: Any, echo: str | None = None) -> dict[str, Any]:
    """Acceptance-deciding part of a web.aria symbol (keys absent from the symbol stay absent).

    ``echo`` is the value the probe typed: where the page shows it back (a greeting, a profile link), it is replaced
    by ``<input>`` so that echoing the input is not mistaken for a different outcome.
    """
    if not isinstance(symbol, dict):
        return {"value": symbol}
    out = {k: symbol[k] for k in OUTCOME_KEYS if k in symbol}
    if echo and echo.strip():
        needle = echo.strip()
        out = {k: [x.replace(needle, "<input>") if isinstance(x, str) else x for x in v] if isinstance(v, list) else v
               for k, v in out.items()}
    if "alerts" not in out:
        out["alerts"] = []  # absence of alerts is part of the outcome; web.aria omits the key when empty
    return out


def judge(reference: dict[str, Any] | None):
    """(refused, describe) for one field: accepted means 'same outcome as the known-good value'."""

    def refused(result: dict[str, Any]) -> bool:
        if result.get("value") in ("DISABLED", "NA"):
            return True
        if reference is not None:
            return result != reference
        return bool(result.get("alerts") or result.get("invalid"))

    def describe(result: dict[str, Any]) -> str:
        if result.get("value") == "DISABLED":
            return "is refused before submission (submit is disabled)"
        if result.get("value") == "NA":
            return "is refused before submission (submit is not offered)"
        if not refused(result):
            return "is accepted (same outcome as the known-good value)"
        detail = []
        if result.get("alerts"):
            detail.append(f"{len(result['alerts'])} alert(s)")
        if result.get("invalid"):
            detail.append(f"invalid controls {result['invalid']}")
        if reference is not None and result.get("path") == reference.get("path") and not detail:
            detail.append("a different page state")
        elif reference is not None and result.get("path") != reference.get("path"):
            detail.append(f"stays on {result.get('path')}")
        return "is refused (" + ", ".join(detail or ["a different outcome"]) + ")"

    return refused, describe


def describe(result: dict[str, Any]) -> str:
    return judge(None)[1](result)


def value_for_length(kind: str, n: int) -> str:
    if kind == "email":
        return "a" * max(1, n - len("@example.com")) + "@example.com"
    if kind == "password":
        return ("a1" * n)[:n]
    if kind == "number":
        return "9" * n
    return "a" * n


@dataclass
class SequenceProbe:
    id: str
    inputs: list[str]
    tags: list[str] = field(default_factory=list)


@dataclass
class SequenceResult:
    probe: SequenceProbe
    evidence: str
    symbol: str
    outputs: list[str]


def run_sequences(open_session: Callable[[], ObservationSession], probes: list[SequenceProbe], *,
                  workers: int = 4) -> list[SequenceResult]:
    indexed = list(enumerate(probes))
    workers = max(1, min(workers, len(probes) or 1))
    chunks = [indexed[i::workers] for i in range(workers)]

    def work(chunk):
        session = open_session()
        out = []
        try:
            for i, p in chunk:
                outputs, evidence, _ = session.run(p.inputs, use_cache=False)
                out.append((i, SequenceResult(p, evidence[-1] if evidence else "", outputs[-1], outputs)))
        finally:
            session.close()
        return out

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = [r for part in pool.map(work, chunks) for r in part]
    return [r for _, r in sorted(results, key=lambda x: x[0])]


def accepted(symbol: str, reference: dict[str, Any]) -> bool:
    """A value is accepted when the post-submit outcome equals the reference (known-good) outcome."""
    return outcome(describe_symbol(symbol)) == reference


def length_boundary(probe_once: Callable[[str], str], kind: str, reference: dict[str, Any], *,
                    hi: int = 4096) -> int | None:
    """Largest accepted length (exponential then binary search). None if even a short value is refused, or if
    nothing up to ``hi`` is refused (no limit observed)."""
    lo = 1 if kind != "email" else len("a@example.com")
    if not accepted(probe_once(value_for_length(kind, lo)), reference):
        return None
    n = lo
    while n < hi and accepted(probe_once(value_for_length(kind, n * 2)), reference):
        n *= 2
    if n >= hi:
        return None
    good, bad = n, min(n * 2, hi)
    while bad - good > 1:
        mid = (good + bad) // 2
        if accepted(probe_once(value_for_length(kind, mid)), reference):
            good = mid
        else:
            bad = mid
    return good


def outcome_json(symbol: str, echo: str | None = None) -> str:
    return json.dumps(outcome(describe_symbol(symbol), echo), sort_keys=True, ensure_ascii=False)
