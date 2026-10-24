"""Spec IR: a symbolic extended Mealy machine (EFSM) with a reference interpreter.

Phase 0 learns finite Mealy machines, so guards and registers are present in the schema but not yet produced by the
learner. Outputs are lists so a transition can carry a multiset of observation symbols; the ``nondeterminism`` tag
says how strictly order and choice must match.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from teardown.engine.mapper import describe_symbol

Nondeterminism = Literal["none", "set", "partial-order", "stochastic"]


class StateDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    access: list[str] = Field(default_factory=list, description="Shortest input sequence that reaches the state.")
    parent: str | None = None
    label: str = ""


class InputDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    label: str = ""
    classes: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="Named equivalence classes of the input's parameter, as JSON Schemas."
    )


class OutputDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    abstract: Any = None
    label: str = ""


class TransitionDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    input: str
    target: str
    outputs: list[str]
    nondeterminism: Nondeterminism = "none"
    guard: str | None = None
    updates: dict[str, str] = Field(default_factory=dict)


class EFSM(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    initial: str
    states: list[StateDef]
    inputs: list[InputDef]
    outputs: list[OutputDef]
    transitions: list[TransitionDef]
    registers: dict[str, str] = Field(default_factory=dict)

    _index: dict[tuple[str, str], TransitionDef] = PrivateAttr(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        self._index = {(t.source, t.input): t for t in self.transitions}

    # -- interpreter -------------------------------------------------------------------------------------------
    def run(self, inputs: list[str]) -> list[str]:
        """Expected output symbol for each input (first element of each transition's output multiset)."""
        state, outputs = self.initial, []
        for a in inputs:
            t = self._index.get((state, a))
            if t is None:
                raise KeyError(f"no transition from {state!r} on {a!r}")
            outputs.append(t.outputs[0] if t.outputs else "")
            state = t.target
        return outputs

    def accepts(self, inputs: list[str], observed: list[str]) -> tuple[bool, int | None]:
        """Trace acceptance: does the model admit this observed trace? Returns (ok, first mismatching index)."""
        state = self.initial
        for i, (a, o) in enumerate(zip(inputs, observed, strict=True)):
            t = self._index.get((state, a))
            if t is None:
                return False, i
            ok = (o in t.outputs) if t.nondeterminism != "none" else (t.outputs[:1] == [o])
            if not ok:
                return False, i
            state = t.target
        return True, None

    def transition_cover(self) -> list[list[str]]:
        """One test per transition: the source state's access sequence followed by the transition's input."""
        access = {s.name: s.access for s in self.states}
        return [access[t.source] + [t.input] for t in self.transitions]

    def reachable_states(self) -> set[str]:
        seen, queue = {self.initial}, deque([self.initial])
        while queue:
            s = queue.popleft()
            for (src, _), t in self._index.items():
                if src == s and t.target not in seen:
                    seen.add(t.target)
                    queue.append(t.target)
        return seen


def from_mealy(mealy, name: str, input_labels: dict[str, str] | None = None) -> EFSM:
    """Convert an AALpy MealyMachine; state names are s0..sN in BFS order from the initial state."""
    order, queue, seen = [], deque([mealy.initial_state]), {mealy.initial_state}
    access = {mealy.initial_state: []}
    alphabet = sorted(mealy.get_input_alphabet())
    while queue:
        s = queue.popleft()
        order.append(s)
        for a in alphabet:
            nxt = s.transitions[a]
            if nxt not in seen:
                seen.add(nxt)
                access[nxt] = access[s] + [a]
                queue.append(nxt)
    names = {s: f"s{i}" for i, s in enumerate(order)}
    symbols: dict[str, None] = {}
    transitions = []
    for s in order:
        for a in alphabet:
            o = s.output_fun[a]
            symbols.setdefault(o, None)
            transitions.append(TransitionDef(source=names[s], input=a, target=names[s.transitions[a]], outputs=[o]))
    labels = input_labels or {}
    return EFSM(
        name=name,
        initial=names[mealy.initial_state],
        states=[StateDef(name=names[s], access=access[s]) for s in order],
        inputs=[InputDef(name=a, label=labels.get(a, "")) for a in alphabet],
        outputs=[OutputDef(symbol=o, abstract=describe_symbol(o)) for o in symbols],
        transitions=transitions,
    )
