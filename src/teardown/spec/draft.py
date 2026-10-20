"""Spec drafts (dirty side) and their release projection (what may cross to the clean side).

The draft keeps everything the observer knows: evidence ids, the real target fingerprint, the mapper rules. The
projection keeps only the abstract model, claim definitions and counts, unknowns and the completeness statement.
The gate then scans that projection for leaked expression before anything is released.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from teardown.core.model import Claim, ContentAddressed, Unknown
from teardown.spec.efsm import EFSM
from teardown.spec.export import to_ears, to_xstate

TESTABILITY_CONTRACT = (
    "The implementation must expose, after every input, an observation whose abstract form equals one of the "
    "output definitions in `model.outputs` (keys and class values exactly as given). Inputs not offered in a state "
    "must be reported as unavailable ('NA'). Wording, layout and visual design are yours to choose."
)
CLI_TESTABILITY_CONTRACT = (
    "The implementation must be installed so that the command names used in `actions` resolve on PATH. Each "
    "action is run in a fresh working directory containing the listed files. Conformance compares the behavior "
    "abstraction in `abstraction` only: exit status, stdout bytes, whether a diagnostic is written to stderr (and "
    "its errno class), and file-system effects. Diagnostic wording is yours to choose."
)

WEB_TESTABILITY_CONTRACT = (
    "Conformance drives your UI only through the actions in `actions` (ARIA role + accessible name; `goto` values "
    "are paths relative to your app's root) and compares the structured accessibility view on the keys each test "
    "names: route path, headings, alerts, visible text, control states (role:name -> flags; field values only as "
    "filled/empty), invalid fields and API exchanges (method, path template, status). Expose the same roles and "
    "accessible names, or provide an adapter mapping. Visual design and wording beyond those names are yours."
)


def contract_for(abstraction: dict[str, Any], has_probes: bool) -> str:
    builtin = (abstraction or {}).get("builtin")
    if builtin == "web.aria/v1":
        return WEB_TESTABILITY_CONTRACT
    if builtin == "cli.behavior/v1":
        return CLI_TESTABILITY_CONTRACT
    return TESTABILITY_CONTRACT


class ProbeRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    expect: str
    tags: list[str] = Field(default_factory=list)
    prefix: list[str] = Field(default_factory=list, description="Named actions run before `action` (UI targets).")
    match: str = Field(default="exact", description="'exact' or 'subset' (UI rows assert only some keys).")


class ProbeTable(ContentAddressed):
    """A batch of single-invocation probes with their behavior symbols (the CLI golden table)."""

    PREFIX: ClassVar[str] = "ptb"

    feature: str
    target: str
    mapper: str
    actions: dict[str, dict[str, Any]]
    rows: list[ProbeRow]
    excluded: dict[str, str] = Field(default_factory=dict, description="probe id -> reason (noise, env)")
    discovery: dict[str, Any] = Field(default_factory=dict, description="Interface structure (no prose).")
    mixed: list[dict[str, Any]] = Field(default_factory=list)


class ModelRecord(ContentAddressed):
    PREFIX: ClassVar[str] = "mdl"

    feature: str
    target: str
    mapper: str
    model: EFSM
    algorithm: str
    budget: dict[str, Any]
    completeness: str


class SpecDraft(ContentAddressed):
    PREFIX: ClassVar[str] = "dft"

    feature: str
    target: str
    mapper: str
    abstraction: dict[str, Any] = Field(default_factory=dict, description="Releasable built-in abstraction.")
    model: ModelRecord | None = None
    probes: ProbeTable | None = None
    actions: dict[str, dict[str, Any]] = Field(default_factory=dict, description="Named actions (definitions).")
    rules: Any = Field(default=None, description="RuleTable of observer-authored rules, if any.")
    api: dict[str, Any] | None = Field(default=None, description="Observed backend contract (value-free shapes).")
    claims: list[Claim] = Field(default_factory=list)
    unknowns: list[Unknown] = Field(default_factory=list)

    def release_projection(self) -> dict[str, Any]:
        model = self.model.model if self.model else None
        actions: dict[str, Any] = dict(sorted(self.actions.items()))
        if self.probes:
            used = {a for r in self.probes.rows for a in [*r.prefix, r.action]}
            used |= {a for c in self.claims for check in c.identity.all_checks() for a in check.inputs}
            actions.update({k: v for k, v in sorted(self.probes.actions.items()) if k in used})
        rule_records = []
        if self.rules is not None:
            table = self.rules if isinstance(self.rules, dict) else self.rules.model_dump(mode="json")
            actions.update(table["actions"])
            rule_records = [{k: r[k] for k in ("id", "statement", "origin", "kind", "status", "checks")}
                            for r in table["rules"]]
        return {
            "feature": self.feature,
            "vocabulary": self.mapper,
            "abstraction": self.abstraction,
            "testability_contract": contract_for(self.abstraction, self.probes is not None),
            "completeness": self.model.completeness if self.model else (
                "probe table only (no state model learned)" if self.probes else "claims only (no state model learned)"),
            "model": model.model_dump(mode="json") if model else None,
            "requirements": to_ears(model) if model else [],
            "xstate": to_xstate(model) if model else None,
            "interface": _interface(self.probes.discovery) if self.probes and self.probes.discovery else None,
            "actions": actions,
            "probe_table": [r.model_dump(mode="json") for r in self.probes.rows] if self.probes else [],
            "rules": rule_records,
            "api": self.api,
            "claims": [
                {
                    "id": c.id,
                    "kind": c.identity.kind,
                    "statement": c.identity.statement,
                    "check": c.identity.check.model_dump(mode="json"),
                    "cases": [k.model_dump(mode="json") for k in c.identity.cases],
                    "strictness": c.identity.strictness,
                    "origin": c.identity.origin,
                    "layer": c.identity.layer,
                    "status": c.status,
                    "probes": c.probes,
                    "confirming": c.confirming,
                    "contradicting": c.contradicting,
                }
                for c in self.claims
            ],
            "unknowns": [
                {"id": u.id, "question": u.identity.question, "recommended_probes": u.recommended_probes}
                for u in self.unknowns
            ],
        }


def _interface(discovery: dict[str, Any]) -> dict[str, Any] | None:
    """Releasable interface structure: option names, arity and value types only (never help prose)."""
    model = discovery.get("model")
    if not model:
        return None
    return {
        "command": discovery.get("cmd"),
        "options": {k: {"names": o["names"], "arity": o["arity"], "type": o["type"],
                        "undocumented": bool(o.get("undocumented"))}
                    for k, o in sorted(model["options"].items()) if not o.get("phantom")},
        "operands": model.get("usage_forms", []),
        "findings": discovery.get("findings", {}),
    }
