"""Field probing for UI forms: equivalence classes, a length boundary search, and per-class outcomes.

A field probe is an episode: reset, the actions that reach the form (``prefix``), fill the field with one class's
value, then the submit action. The outcome is the subset of the resulting observation that decides acceptance:
route, headings, alerts and invalid controls. Classes found at the length boundary are returned so they can be
added to the learning alphabet (in the web spike, a max-length difference was only detectable once such classes
were inputs).
"""

from __future__ import annotations

import json
import re
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

OUTCOME_KEYS = ("path", "headings", "alerts", "status", "invalid", "text", "network")


def layer_of(result: dict[str, Any]) -> str:
    """Where a refusal happened: no API request at all -> client; an API 4xx -> server; else unknown."""
    if result.get("value") in ("DISABLED", "NA") or not result.get("network"):
        return "client"
    statuses = [int(x.rsplit(" ", 1)[1]) for x in result["network"] if x.rsplit(" ", 1)[1].isdigit()]
    if any(400 <= s < 500 for s in statuses):
        return "server"
    return "unknown"


def slug(text: str) -> str:
    """URL-slug form of a value (as apps derive routes from titles and names)."""
    import unicodedata

    flat = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", flat.lower()).strip("-")


def _echo_patterns(echo: str | None) -> list[re.Pattern]:
    """The typed value and its slug, matched as whole words (needles shorter than 3 characters are not masked:
    replacing a one-letter value would rewrite unrelated text)."""
    if not echo or not echo.strip():
        return []
    needles = {echo.strip(), slug(echo.strip())}
    return [re.compile(rf"(?<![\w]){re.escape(n)}(?![\w])") for n in sorted(needles, key=len, reverse=True)
            if len(n) >= 3]


def acceptance(accepted_if: dict[str, Any] | None):
    """The observer's own definition of 'accepted' for a field, or None (then: same outcome as the known-good value).

    ``{"subset": {...}}``: the outcome contains this (subset at every level, e.g. one control's flags);
    ``{"text_contains": "..."}``: some visible text line contains the string. Both may be given.
    """
    if not accepted_if:
        return None
    from teardown.engine.mapper import _subset

    want, needle = accepted_if.get("subset"), accepted_if.get("text_contains")

    def accept(result: dict[str, Any]) -> bool:
        if result.get("value") in ("DISABLED", "NA"):
            return False
        if want is not None and not _subset(want, result):
            return False
        return needle is None or any(needle in t for t in result.get("text", []) if isinstance(t, str))

    return accept


def outcome(symbol: Any, echo: str | None = None, keys: tuple[str, ...] = OUTCOME_KEYS) -> dict[str, Any]:
    """Acceptance-deciding part of a web.aria symbol (keys absent from the symbol stay absent).

    ``echo`` is the value the probe typed: where the page shows it back (a greeting, a profile link), it is replaced
    by ``<input>`` so that echoing the input is not mistaken for a different outcome.
    """
    if not isinstance(symbol, dict):
        return {"value": symbol}
    out = {k: symbol[k] for k in keys if k in symbol}
    # server-side refusals often show only as a dialog that stays open or a field marked aria-invalid. Only real
    # symbol keys go into the outcome (probe rows store it and verification matches it against live symbols):
    # the marked fields as a `controls` subset, plus the symbol's own `flagged` list when it has one.
    if symbol.get("dialogs"):
        out["dialogs"] = symbol["dialogs"]
    marked = {k: f for k, f in (symbol.get("controls") or {}).items() if "invalid" in f}
    if marked:
        out["controls"] = marked
    if symbol.get("flagged"):
        out["flagged"] = symbol["flagged"]
    patterns = _echo_patterns(echo)
    if patterns:
        def mask(x: Any) -> Any:
            if not isinstance(x, str):
                return x
            for p in patterns:
                x = p.sub("<input>", x)
            return x

        out = {k: [mask(x) for x in v] if isinstance(v, list) else mask(v) if k == "path" else v
               for k, v in out.items()}
    if "alerts" not in out:
        out["alerts"] = []  # absence of alerts is part of the outcome; web.aria omits the key when empty
    return out


def _same_shape(result: dict[str, Any], reference: dict[str, Any]) -> bool:
    """Web: a value is accepted when the submit ends like the known-good one: the same route template, the same
    status message (with the typed value masked), no alert or invalid field the reference did not have. Other
    text may differ (an accepted value echoes itself: a new title, a computed total)."""
    from teardown.engine.discovery import route_template

    if route_template(result.get("path") or "") != route_template(reference.get("path") or ""):
        return False
    if result.get("alerts") and not reference.get("alerts"):
        return False
    if (result.get("status") or reference.get("status")) and result.get("status") != reference.get("status"):
        return False  # a different status message ("Saved <input>" vs "Name is too long")
    if result.get("invalid") and not reference.get("invalid"):
        return False
    if _marked(result) - _marked(reference):
        return False  # a field the app marked aria-invalid
    if set(result.get("dialogs") or []) - set(reference.get("dialogs") or []):
        return False  # the dialog stayed open
    return not (_client_errors(result) - _client_errors(reference))  # an API 4xx the good value did not get


def _marked(result: dict[str, Any]) -> set[str]:
    """Fields an outcome shows as marked aria-invalid."""
    return {k for k, f in (result.get("controls") or {}).items() if "invalid" in f} | set(result.get("flagged") or [])


def _client_errors(result: dict[str, Any]) -> set[str]:
    """API calls answered 4xx: 'POST /api/x 422' -> 'POST /api/x'."""
    out = set()
    for entry in result.get("network") or []:
        call, _, status = entry.rpartition(" ")
        if status.isdigit() and 400 <= int(status) < 500:
            out.add(call)
    return out


def judge(reference: dict[str, Any] | None, accept=None, *, live: bool = False):
    """(refused, describe) for one field: accepted means the observer's ``accept`` predicate holds, or else 'same
    outcome as the known-good value'. ``live`` (read right after typing, no submit): nothing is accepted or
    refused; the classes grouped in one claim show the same screen."""

    def refused(result: dict[str, Any]) -> bool:
        if result.get("value") in ("DISABLED", "NA"):
            return True
        if accept is not None:
            return not accept(result)
        if reference is not None and "path" in reference:  # web: judge by outcome shape, not exact equality
            return not _same_shape(result, reference)
        if reference is not None:
            return result != reference
        return bool(result.get("alerts") or result.get("invalid"))

    def describe(result: dict[str, Any]) -> str:
        if live:
            return "shows the same screen right after typing (as recorded in the check)"
        if result.get("value") == "DISABLED":
            return "is refused before submission (submit is disabled)"
        if result.get("value") == "NA":
            return "is refused before submission (submit is not offered)"
        if not refused(result):
            return ("is accepted" if accept is not None else
                    "is accepted (same outcome as the known-good value)" if reference is not None else
                    "shows no alert or invalid field")
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
    evidences: list[str] = field(default_factory=list)  # one per step


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
                out.append((i, SequenceResult(p, evidence[-1] if evidence else "", outputs[-1], outputs,
                                              list(evidence))))
        finally:
            session.close()
        return out

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = [r for part in pool.map(work, chunks) for r in part]
    return [r for _, r in sorted(results, key=lambda x: x[0])]


def accepted(symbol: str, reference: dict[str, Any], accept=None, keys: tuple[str, ...] = OUTCOME_KEYS,
             echo: str | None = None) -> bool:
    """A value is accepted when ``accept`` holds for its outcome; else (web) when the submit ends like the
    known-good one (``_same_shape``); else when the outcomes are equal. The typed value is masked (``echo``)."""
    result = outcome(describe_symbol(symbol), echo, keys=keys)
    if accept is not None:
        return accept(result)
    if "path" in reference:
        return _same_shape(result, reference)
    return result == reference


def length_boundary(probe_once: Callable[[str], str], kind: str, reference: dict[str, Any], *,
                    hi: int = 4096, accept=None, keys: tuple[str, ...] = OUTCOME_KEYS) -> int | None:
    """Largest accepted length; see ``length_bounds``."""
    return length_bounds(probe_once, kind, reference, hi=hi, accept=accept, keys=keys)[1]


def length_bounds(probe_once: Callable[[str], str], kind: str, reference: dict[str, Any], *,
                  hi: int = 4096, accept=None, keys: tuple[str, ...] = OUTCOME_KEYS) -> tuple[int | None, int | None]:
    """(smallest, largest) accepted length, by exponential then binary search. The smallest is None when the
    shortest length tried is accepted; the largest is None when nothing up to ``hi`` is refused (no limit
    observed). Both are None when no length up to ``hi`` is accepted."""
    import functools

    accepted_ = functools.partial(accepted, accept=accept, keys=keys)

    def ok(n: int) -> bool:
        return accepted_(probe_once(v := value_for_length(kind, n)), reference, echo=v)

    # start where echo masking applies (3+ characters): a shorter typed value shown back would not be masked
    lo = 3 if kind != "email" else len("a@example.com")
    shortest = None
    if not ok(lo):  # a minimum length: find the first accepted length above it
        n = lo
        while n < hi and not ok(n * 2):
            n *= 2
        if n >= hi:
            return None, None
        bad, good = n, min(n * 2, hi)
        while good - bad > 1:
            mid = (good + bad) // 2
            if ok(mid):
                good = mid
            else:
                bad = mid
        shortest = lo = good
    n = lo
    while n < hi and ok(n * 2):
        n *= 2
    if n >= hi:
        return shortest, None
    good, bad = n, min(n * 2, hi)
    while bad - good > 1:
        mid = (good + bad) // 2
        if ok(mid):
            good = mid
        else:
            bad = mid
    return shortest, good


def outcome_json(symbol: str, echo: str | None = None) -> str:
    return json.dumps(outcome(describe_symbol(symbol), echo), sort_keys=True, ensure_ascii=False)
