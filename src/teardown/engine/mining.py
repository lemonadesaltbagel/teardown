"""Decision-table claim mining for probe batches.

Probes are grouped by the factor that generated them (option x value class, input x delivery mode, syntax edge,
operand form x value class). Within a factor, value classes with the same outcome class are folded into one claim,
so the ledger says "classes {zero, nonnum, empty} of -f are refused with exit 1" rather than 30 separate facts.
A fold is only made when every probe of every class agrees; a class with mixed outcomes stays out and is reported
as needing a finer partition.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from teardown.core.model import ClaimKind, TraceCheck
from teardown.engine.mapper import describe_symbol
from teardown.engine.noise import outcome_class
from teardown.engine.probing import ProbeResult


@dataclass
class MinedClaim:
    feature: str
    kind: ClaimKind
    statement: str
    factor: str
    classes: list[str]
    outcome: dict[str, Any]
    checks: list[TraceCheck] = field(default_factory=list)


def _factor(tags: list[str]) -> tuple[str, str] | None:
    """(factor, class) for single-factor probes; None for pairwise rows, which are kept as golden tests only."""
    tag = {t.split(":", 1)[0]: t.split(":", 1)[1] for t in tags if ":" in t}
    strategy = tag.get("s")
    if strategy == "sweep" and "opt" in tag:
        return f"option {tag['opt']}", tag.get("val", "flag")
    if strategy == "inputs":
        if "in" in tag and tag.get("mode") in ("stdin", "file"):
            return f"input via {tag['mode']}", tag["in"]
        if "mode" in tag:
            return "operand delivery", tag["mode"]
    if strategy == "syntax" and "syn" in tag:
        return "argv syntax" + (" (POSIXLY_CORRECT)" if tag.get("env") == "posix" else ""), tag["syn"]
    if strategy == "operands" and "val" in tag:
        position, _, cls = tag["val"].partition(".")
        opts = f" with options '{tag['opts']}'" if tag.get("opts") else ""
        on = f" on input {tag['in']}" if tag.get("in") else ""
        return f"operand {position} (form {tag.get('form', '?')}){opts}{on}", cls
    if strategy == "field" and "field" in tag:
        return f"field {tag['field']}", tag.get("val", "?")
    if strategy == "stdio" and "stdio" in tag:
        return "stdio mode", tag["stdio"]
    if strategy == "env" and "env" in tag:
        return "locale", tag["env"]
    return None


def _describe(outcome: dict[str, Any]) -> str:
    if outcome.get("timed_out"):
        return "does not terminate within the time limit"
    if outcome.get("signal") is not None:
        return f"is terminated by signal {outcome['signal']}"
    verb = "succeeds (exit 0)" if outcome.get("exit") == 0 else f"refuses with exit {outcome.get('exit')}"
    diag = "a diagnostic" + (f" ({outcome['errno']})" if outcome.get("errno") else "")
    return f"{verb} {'with' if outcome.get('diagnostic') else 'without'} {diag}"


def mine(feature: str, cmd: str, results: list[ProbeResult], *, exclude: set[str] | None = None,
         min_probes: int = 1, outcome: Callable[[Any], dict[str, Any]] = outcome_class,
         describe: Callable[[dict[str, Any]], str] | None = None) -> tuple[list[MinedClaim], list[dict[str, Any]]]:
    """Return (claims, mixed) where ``mixed`` lists factor classes whose probes disagree.

    ``results`` items need ``.probe.id``, ``.probe.tags``, ``.symbol`` and optionally ``.probe.inputs`` (the action
    sequence for UI probes; CLI probes are a single action named by the probe id).
    """
    exclude = exclude or set()
    describe = describe or _describe
    groups: dict[str, dict[str, list[tuple[ProbeResult, dict]]]] = defaultdict(lambda: defaultdict(list))
    for r in results:
        if r.probe.id in exclude:
            continue
        key = _factor(r.probe.tags)
        if key:
            groups[key[0]][key[1]].append((r, outcome(describe_symbol(r.symbol))))
    claims, mixed = [], []
    for factor, classes in sorted(groups.items()):  # noqa: PLR1702
        by_outcome: dict[str, list[str]] = defaultdict(list)
        for cls, rows in sorted(classes.items()):
            outcomes = {json.dumps(o, sort_keys=True) for _, o in rows}
            if len(outcomes) == 1:
                by_outcome[outcomes.pop()].append(cls)
            else:
                mixed.append({"factor": factor, "class": cls, "outcomes": sorted(outcomes)})
        for outcome_json, cls_list in sorted(by_outcome.items()):
            result = json.loads(outcome_json)
            rows = [r for c in cls_list for r, _ in classes[c]]
            if len(rows) < min_probes:
                continue
            # CLI outcomes refuse by exit status; UI outcomes refuse by showing alerts or invalid controls.
            if "exit" in result:
                refused = result.get("exit") != 0
            else:
                refused = bool(result.get("alerts") or result.get("invalid"))
            kind = ClaimKind.REFUSAL if refused else ClaimKind.INPUT_DOMAIN
            shown = ", ".join(cls_list[:12]) + (f" (+{len(cls_list) - 12} more)" if len(cls_list) > 12 else "")
            statement = f"For {factor} with class {{{shown}}}, `{cmd}` {describe(result)}."
            checks = []
            for r in rows:
                inputs = list(getattr(r.probe, "inputs", None) or [r.probe.id])
                checks.append(TraceCheck(inputs=inputs, expect=[None] * (len(inputs) - 1) + [outcome_json],
                                         match="subset"))
            claims.append(MinedClaim(feature, kind, statement, factor, cls_list, result, checks))
    return claims, mixed
