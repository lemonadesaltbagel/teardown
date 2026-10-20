"""The gate: sanitize a spec draft's release projection and decide whether it may cross to the clean side.

Every check runs in every mode. In ``standard`` mode findings are warnings and the release proceeds; in ``strict``
mode any finding blocks the release until a named human approves it. The user owns the legal judgment either way;
the gate's job is to make leaked expression visible and to keep the record.
"""

from __future__ import annotations

import json
import random
import re
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from teardown.core.ids import sha256_hex
from teardown.core.model import ContentAddressed
from teardown.gate.matcher import CorpusMatcher, NearMatcher, tokenize
from teardown.spec.draft import SpecDraft

_WORDS_A = ["amber", "basalt", "cobalt", "delta", "ember", "fjord", "garnet", "harbor", "indigo", "juniper"]
_WORDS_B = ["falcon", "lantern", "meadow", "orchid", "pebble", "quarry", "raven", "summit", "tundra", "willow"]


def make_codename(seed: str) -> str:
    rng = random.Random(sha256_hex(seed.encode()))
    return f"{rng.choice(_WORDS_A)}-{rng.choice(_WORDS_B)}"


class GateMode(StrEnum):
    STANDARD = "standard"
    STRICT = "strict"


class QuoteEntry(BaseModel):
    """A literal allowed to cross the gate, with the reason it is functionally necessary."""

    model_config = ConfigDict(extra="forbid")

    text: str
    compat_reason: str = Field(
        description="protocol | file-format | public-api | error-code | accessibility-name | test-oracle | "
        "user-required"
    )
    approved_by: str


class GateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: GateMode = GateMode.STANDARD
    codename: str
    denylist: list[str] = Field(default_factory=list, description="Real names replaced by the codename.")
    quotes: list[QuoteEntry] = Field(default_factory=list)
    min_tokens: int = Field(default=4, description="Shortest verbatim token run that counts as a leak.")
    near_threshold: float = Field(default=0.5, description="Share of a string's winnowing fingerprints from one "
                                  "corpus passage that counts as near-verbatim (strings of 12+ words).")


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    location: str
    text: str
    matched: str = ""
    tokens: int = 0
    occurrences: int = 1


class GateReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: GateMode
    findings: list[Finding]
    blocked: bool
    approved_by: str | None = None


class SpecRelease(ContentAddressed):
    PREFIX: ClassVar[str] = "rel"

    codename: str
    mode: GateMode
    spec: dict[str, Any]
    report: GateReport
    previous: str | None = None


class ReleaseBlocked(PermissionError):
    def __init__(self, report: GateReport):
        super().__init__(f"strict mode: {len(report.findings)} gate finding(s) need human approval")
        self.report = report


def review(draft: SpecDraft, corpus: list[str], config: GateConfig,
           supplied: list[str] | None = None) -> tuple[dict[str, Any], GateReport]:
    """Return the sanitized projection and the gate report (nothing is written).

    ``supplied`` is text Teardown fed to the target itself (probe inputs); a verbatim run that also occurs there
    is the target echoing our input, not the target's expression.
    """
    projection = _replace_names(draft.release_projection(), config)
    matcher = CorpusMatcher(corpus)
    near = NearMatcher(corpus)
    ours = CorpusMatcher(supplied or [])
    quoted = [tokenize(q.text) for q in config.quotes]
    denied = [d.casefold() for d in config.denylist if d]
    found: dict[tuple[str, str], Finding] = {}

    def add(finding: Finding) -> None:
        key = (finding.kind, finding.matched)
        if key in found:
            found[key].occurrences += 1
        else:
            found[key] = finding

    for location, text in _string_leaves(projection):
        match = matcher.longest(text)
        echoed = match is not None and (own := ours.longest(" ".join(match.query_tokens))) is not None and (
            own.length >= match.length)
        if match and match.length >= config.min_tokens and _wordy(match.query_tokens) >= config.min_tokens and (
                not echoed) and not _covered(list(match.query_tokens), quoted):
            add(
                Finding(
                    kind="verbatim",
                    location=location,
                    text=text,
                    matched=" ".join(match.query_tokens),
                    tokens=match.length,
                )
            )
        tokens = tokenize(text)
        if len(tokens) >= 12 and not (match and match.length >= config.min_tokens):
            share, source = near.best(text)
            if share >= config.near_threshold and _wordy(tuple(tokens)) >= config.min_tokens:
                add(Finding(kind="near-verbatim", location=location, text=text, matched=source[:120],
                            tokens=round(share * 100)))
        lowered = text.casefold()
        for term in denied:
            if term in lowered:
                add(Finding(kind="denylist", location=location, text=text, matched=term))
    findings = list(found.values())
    blocked = config.mode is GateMode.STRICT and bool(findings)
    return projection, GateReport(mode=config.mode, findings=findings, blocked=blocked)


def release(
    draft: SpecDraft,
    corpus: list[str],
    config: GateConfig,
    releases_dir: Path,
    *,
    approved_by: str | None = None,
    supplied: list[str] | None = None,
) -> SpecRelease:
    projection, report = review(draft, corpus, config, supplied)
    if report.blocked:
        if not approved_by:
            raise ReleaseBlocked(report)
        report = report.model_copy(update={"blocked": False, "approved_by": approved_by})
    previous = _latest_id(releases_dir)
    rel = SpecRelease(codename=config.codename, mode=config.mode, spec=projection, report=report, previous=previous)
    releases_dir.mkdir(parents=True, exist_ok=True)
    (releases_dir / f"{rel.id}.json").write_text(rel.model_dump_json(indent=1), encoding="utf-8")
    (releases_dir / "LATEST").write_text(rel.id, encoding="utf-8")
    return rel


def load_release(releases_dir: Path, release_id: str | None = None) -> SpecRelease:
    release_id = release_id or _latest_id(releases_dir)
    if not release_id or not re.fullmatch(r"rel_[0-9a-f]{64}", release_id):
        raise KeyError("no spec has been released yet" if not release_id else f"malformed release id {release_id}")
    return SpecRelease.model_validate_json((releases_dir / f"{release_id}.json").read_text(encoding="utf-8"))


def _latest_id(releases_dir: Path) -> str | None:
    latest = releases_dir / "LATEST"
    return latest.read_text(encoding="utf-8").strip() if latest.exists() else None


def _replace_names(projection: dict[str, Any], config: GateConfig) -> dict[str, Any]:
    return json.loads(rename_text(json.dumps(projection, ensure_ascii=False), config))


def rename_text(text: str, config: GateConfig) -> str:
    """Replace denylisted real names with the codename (JSON-escaped forms included)."""
    for term in sorted((d for d in config.denylist if d), key=len, reverse=True):
        text = re.sub(re.escape(json.dumps(term)[1:-1]), config.codename, text, flags=re.IGNORECASE)
    return text


def rename_symbol(symbol: str, config: GateConfig) -> str:
    """Apply the release's codename substitution to a live symbol, so it compares with released expectations."""
    return json.loads(rename_text(json.dumps(symbol, ensure_ascii=False), config)) if config.denylist else symbol


def _string_leaves(value: Any, path: str = "$"):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield f"{path}.<key>", k
            yield from _string_leaves(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _string_leaves(v, f"{path}[{i}]")


def _wordy(tokens: tuple[str, ...]) -> int:
    """Distinct alphabetic words of 3+ letters: a run of numbers, keys and repeated literals is data, not prose."""
    return len({t for t in tokens if len(t.strip("-")) >= 3 and any(c.isalpha() for c in t)})


def _covered(tokens: list[str], quoted: list[list[str]]) -> bool:
    n = len(tokens)
    return any(any(q[i : i + n] == tokens for i in range(len(q) - n + 1)) for q in quoted if len(q) >= n)
