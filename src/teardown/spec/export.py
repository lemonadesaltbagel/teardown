"""Human-reviewable exports of the spec IR: EARS-style requirement text and an XState v5 machine config."""

from __future__ import annotations

from typing import Any

from teardown.engine.mapper import NOT_AVAILABLE
from teardown.spec.efsm import EFSM


def to_xstate(model: EFSM) -> dict[str, Any]:
    states: dict[str, Any] = {}
    for s in model.states:
        on: dict[str, Any] = {}
        for t in (t for t in model.transitions if t.source == s.name):
            if t.outputs == [NOT_AVAILABLE] and t.target == s.name:
                continue
            on[t.input] = {"target": t.target, "meta": {"outputs": t.outputs, "nondeterminism": t.nondeterminism}}
        states[s.name] = {"on": on, "meta": {"access": s.access, "label": s.label}}
    return {"id": model.name, "initial": model.initial, "states": states}


def to_ears(model: EFSM) -> list[str]:
    """One requirement per non-trivial transition, in the 'While <state>, when <input>, the system shall ...' form."""
    labels = {o.symbol: (o.label or o.symbol) for o in model.outputs}
    lines = []
    for t in model.transitions:
        out = t.outputs[0] if t.outputs else ""
        if out == NOT_AVAILABLE:
            lines.append(f"While in {t.source}, the system shall not offer '{t.input}'.")
            continue
        move = "remain in" if t.target == t.source else "move to"
        lines.append(
            f"While in {t.source}, when '{t.input}' occurs, the system shall show {labels.get(out, out)} "
            f"and {move} {t.target}."
        )
    return lines
