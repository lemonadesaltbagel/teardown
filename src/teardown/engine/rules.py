"""Rules: behavioral statements written by the observer in its own words, each with executable checks.

Mined decision-table claims say *what happened* for a class of values. Rules say *why*, as a generalization that a
reimplementer can build from ("lines starting with # are comments", "% is floored"). Each rule carries checks the
engine runs against the original to corroborate or falsify it:

``outcome``  one invocation; its behavior symbol must contain ``expect`` (subset match)
``same``     two invocations must produce the same symbol (optionally only on ``keys``): metamorphic checks
``differs``  two invocations must produce different symbols (on ``keys``)

The released spec carries each rule with its checks and the original's observed symbols, so the clean side gets
both the rule and worked examples, and the verifier can test the *relation* on the clone, not only fixed outputs.

``origin`` records where the rule came from: ``documented`` (public documentation, rewritten in the observer's
words; never copied), ``inferred-intent`` (generalized from probes), or ``observed``. A falsified documented rule is
a documentation/behavior conflict and is reported as such.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from teardown.core.ids import content_id
from teardown.core.model import ContentAddressed
from teardown.engine.mapper import describe_symbol, symbol_matches


class RuleCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["outcome", "same", "differs"]
    a: dict[str, Any] = Field(description="First side: a CLI invocation, or {'actions': [named actions]} for UIs.")
    b: dict[str, Any] | None = Field(default=None, description="Second side for same/differs.")
    expect: dict[str, Any] | None = Field(default=None, description="Subset of the behavior symbol (outcome).")
    keys: list[str] | None = Field(default=None, description="Compare only these symbol keys (same/differs).")


class RuleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature: str
    statement: str
    origin: Literal["documented", "inferred-intent", "observed"] = "inferred-intent"
    kind: str = "invariant"
    checks: list[RuleCheck]


class CheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    a: str
    b: str | None = None
    a_inputs: list[str] | None = Field(default=None, description="UI rules: the action sequence of side a.")
    b_inputs: list[str] | None = None
    expect: str | None = None
    keys: list[str] | None = None
    observed_a: str
    observed_b: str | None = None
    holds: bool


class RuleRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    statement: str
    origin: str
    kind: str
    status: Literal["corroborated", "falsified", "contested"]
    checks: list[CheckResult]


class RuleTable(ContentAddressed):
    PREFIX: ClassVar[str] = "rul"

    feature: str
    target: str
    mapper: str
    actions: dict[str, dict[str, Any]]
    rules: list[RuleRecord]


def action_id(side: dict[str, Any]) -> str:
    return content_id("act", side)[:24]


def sequence(side: dict[str, Any] | None) -> list[str] | None:
    return list(side["actions"]) if side and "actions" in side else None


def projection(symbol: str, keys: list[str] | None) -> Any:
    value = describe_symbol(symbol)
    if keys and isinstance(value, dict):
        return {k: value.get(k) for k in keys}
    return value


def evaluate(check: RuleCheck, symbols: dict[str, str]) -> CheckResult:
    a = action_id(check.a)
    b = action_id(check.b) if check.b else None
    sa, sb = symbols[a], symbols.get(b) if b else None
    if check.kind == "outcome":
        expect = json.dumps(check.expect or {}, sort_keys=True, ensure_ascii=False)
        holds = symbol_matches(sa, expect, "subset")
    else:
        if sb is None:
            raise ValueError(f"{check.kind} check needs a second invocation")
        equal = projection(sa, check.keys) == projection(sb, check.keys)
        holds = equal if check.kind == "same" else not equal
        expect = None
    return CheckResult(kind=check.kind, a=a, b=b, a_inputs=sequence(check.a), b_inputs=sequence(check.b),
                       expect=expect, keys=check.keys, observed_a=sa, observed_b=sb, holds=holds)


def status_of(results: list[CheckResult]) -> str:
    held = sum(r.holds for r in results)
    if held == len(results):
        return "corroborated"
    return "falsified" if held == 0 else "contested"


def suggest(record: RuleRecord) -> list[str]:
    """Concrete rewrites for failing checks, from what the original actually did (for the observer to adopt)."""
    out = []
    for i, c in enumerate(record.checks):
        if c.holds:
            continue
        if c.kind == "outcome":
            observed = describe_symbol(c.observed_a)
            expected = json.loads(c.expect or "{}")
            actual = {k: observed.get(k) for k in expected} if isinstance(observed, dict) else observed
            out.append(f"check {i}: expected {expected} but the original gives {actual}")
        else:
            a, b = projection(c.observed_a, c.keys), projection(c.observed_b or "", c.keys)
            if isinstance(a, dict) and isinstance(b, dict):
                differing = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
                detail = f"they differ on {differing}" if differing else "they are identical"
            else:
                detail = "they differ" if a != b else "they are identical"
            flip = "differs" if c.kind == "same" else "same"
            out.append(f"check {i}: '{c.kind}' does not hold ({detail}); consider '{flip}' or narrowing keys")
    return out
