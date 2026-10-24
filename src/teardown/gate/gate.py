"""The gate: sanitize a spec draft's release projection and decide whether it may cross to the clean side.

Every check runs in every mode. In ``standard`` mode findings are warnings and the release proceeds; in ``strict``
mode every finding blocks the release until a recorded approval covers it. The user owns the legal judgment either
way; the gate's job is to make leaked expression visible and to keep the record.

Findings are classified by where they sit in the spec:

- ``expected-output``: observed outcomes a conforming clone must reproduce (probe rows, rule-check expectations and
  observations, model outputs). Usually functional (UI labels, messages the behavior includes).
- ``interface``: what the clean side drives and calls (action names and values, API paths, contract selectors).
- ``prose``: the observer's own sentences (rule statements, claims, unknowns) and anything unclassified. Expression
  that leaks here is never functional; it is approved one finding at a time, or rewritten.

``expected-output`` and ``interface`` findings may be approved as a class; ``prose`` findings only individually.
"""

from __future__ import annotations

import json
import random
import re
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from teardown.core.ids import canonical_json, sha256_hex
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
    approvals: list[GateApproval] = Field(default_factory=list)
    min_tokens: int = Field(default=4, description="Shortest verbatim token run that counts as a leak.")
    near_threshold: float = Field(default=0.5, description="Share of a string's winnowing fingerprints from one "
                                  "corpus passage that counts as near-verbatim (strings of 12+ words).")


FINDING_CLASSES = ("expected-output", "interface", "prose")
CLASS_APPROVABLE = {"expected-output", "interface"}
COMPAT_REASONS = ("protocol", "file-format", "public-api", "error-code", "accessibility-name", "test-oracle",
                  "user-required")


GENERATED_UNKNOWNS = ("not exercised by any probe or rule:", "value class '", "no length limit observed",
                      "documentation/behavior conflict:", "Expected UI text contains calendar dates")


def finding_class(location: str, text: str = "") -> str:
    """Spec location (``$.rules[3].checks[0].expect``) -> finding class. Unknowns that Teardown generated
    (coverage gaps, value classes) quote interface names, not the observer's prose."""
    path = re.sub(r"\[\d+\]", "[]", location)
    head = path.split(".")[1] if path.count(".") else ""
    if head.removesuffix("[]") == "unknowns" and text.startswith(GENERATED_UNKNOWNS):
        return "interface"
    head = head.removesuffix("[]")
    if head in ("probe_table", "model", "requirements", "xstate"):
        return "expected-output"
    if head in ("actions", "api", "markup_contract", "interface", "vocabulary", "abstraction"):
        return "interface"
    if head in ("rules", "claims"):
        segments = {seg.removesuffix("[]") for seg in path.split(".")[2:]}
        if segments & {"expect", "observed_a", "observed_b", "observed"}:
            return "expected-output"
        if segments & {"a", "b", "a_inputs", "b_inputs", "inputs", "keys", "actions", "argv", "stdin", "files"}:
            return "interface"
    return "prose"


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    location: str
    text: str
    matched: str = ""
    tokens: int = 0
    occurrences: int = 1
    cls: str = "prose"
    approval: str | None = Field(default=None, description="Id of the approval covering this finding, if any.")

    @property
    def id(self) -> str:
        """Stable across re-reviews: the same leaked run in the same class keeps its id."""
        return "fnd_" + sha256_hex(canonical_json([self.kind, self.cls, self.matched]))[:16]


class GateApproval(BaseModel):
    """A human's decision that findings may cross: one finding (by id), or a whole class of one kind."""

    model_config = ConfigDict(extra="forbid")

    scope: str = Field(description="'finding' or 'class'")
    finding: str | None = None
    cls: str | None = None
    kind: str = "verbatim"
    compat_reason: str
    approved_by: str
    note: str = ""

    @property
    def id(self) -> str:
        return "apv_" + sha256_hex(canonical_json(self.model_dump(mode="json")))[:16]

    def covers(self, f: Finding) -> bool:
        if self.scope == "finding":
            return self.finding == f.id
        return self.cls == f.cls and self.kind == f.kind and f.cls in CLASS_APPROVABLE


class GateReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: GateMode
    findings: list[Finding]
    blocked: bool
    approved_by: str | None = None

    def unapproved(self) -> list[Finding]:
        return [f for f in self.findings if f.approval is None]

    def summary(self) -> dict[str, Any]:
        """Findings grouped by class and kind: counts, approved counts, a few examples."""
        groups: dict[str, dict[str, Any]] = {}
        for f in self.findings:
            g = groups.setdefault(f"{f.cls}/{f.kind}", {"cls": f.cls, "kind": f.kind, "findings": 0, "approved": 0,
                                                         "class_approvable": f.cls in CLASS_APPROVABLE,
                                                         "examples": []})
            g["findings"] += 1
            g["approved"] += f.approval is not None
            if len(g["examples"]) < 3:
                g["examples"].append({"id": f.id, "location": f.location, "matched": f.matched[:80]})
        return {"mode": self.mode.value, "blocked": self.blocked, "findings": len(self.findings),
                "unapproved": len(self.unapproved()), "groups": sorted(groups.values(), key=lambda g: (
                    FINDING_CLASSES.index(g["cls"]), g["kind"]))}


class SpecRelease(ContentAddressed):
    PREFIX: ClassVar[str] = "rel"

    codename: str
    mode: GateMode
    spec: dict[str, Any]
    report: GateReport
    previous: str | None = None


class ReleaseBlocked(PermissionError):
    def __init__(self, report: GateReport):
        super().__init__(f"strict mode: {len(report.unapproved())} of {len(report.findings)} gate finding(s) have "
                         "no approval; review them with `teardown review` and approve at a terminal with "
                         "`teardown approve`, or rewrite the text")
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
        finding.cls = finding_class(finding.location, finding.text)
        key = (finding.kind, finding.cls, finding.matched)
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
        exact_hit = match is not None and match.length >= config.min_tokens
        if len(tokens) >= 12 and not exact_hit and not _mostly_quoted(tokens, quoted):
            share, source = near.best(text)
            if share >= config.near_threshold and _wordy(tuple(tokens)) >= config.min_tokens:
                add(Finding(kind="near-verbatim", location=location, text=text, matched=source[:120],
                            tokens=round(share * 100)))
        lowered = text.casefold()
        for term in denied:
            if term in lowered:
                add(Finding(kind="denylist", location=location, text=text, matched=term))
    findings = list(found.values())
    for f in findings:
        f.approval = next((a.id for a in config.approvals if a.covers(f)), None)
    approved = sorted({a.approved_by for a in config.approvals if any(f.approval == a.id for f in findings)})
    blocked = config.mode is GateMode.STRICT and any(f.approval is None for f in findings)
    return projection, GateReport(mode=config.mode, findings=findings, blocked=blocked,
                                  approved_by=", ".join(approved) or None)


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
    if report.blocked:  # strict: only recorded approvals count; a name passed here is not an approval
        raise ReleaseBlocked(report)
    if approved_by and config.mode is GateMode.STANDARD:
        report = report.model_copy(update={"approved_by": approved_by})
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
    if not config.denylist:
        return symbol
    renamed = json.loads(rename_text(json.dumps(symbol, ensure_ascii=False), config))
    try:  # keep symbols canonical after renaming (renamed keys sort differently)
        return json.dumps(json.loads(renamed), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except json.JSONDecodeError:
        return renamed


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


def _mostly_quoted(tokens: list[str], quoted: list[list[str]], share: float = 0.8) -> bool:
    words = set(tokens)
    return any(len(words & set(q)) >= share * len(words) for q in quoted) if words else False


def _wordy(tokens: tuple[str, ...]) -> int:
    """Distinct alphabetic words of 3+ letters: a run of numbers, keys and repeated literals is data, not prose."""
    return len({t for t in tokens if len(t.strip("-")) >= 3 and any(c.isalpha() for c in t)})


def _covered(tokens: list[str], quoted: list[list[str]]) -> bool:
    n = len(tokens)
    return any(any(q[i : i + n] == tokens for i in range(len(q) - n + 1)) for q in quoted if len(q) >= n)
