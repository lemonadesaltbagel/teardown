"""Observation tree: every abstract trace ever seen, shared as the query cache for all learners.

A conflict (same abstract input word, different abstract output) is never silently overwritten: it is recorded so
the refinement step can decide whether it is noise, an abstraction that is too coarse, or hidden state.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class _Node:
    output: str | None = None
    count: int = 0
    children: dict[str, _Node] = field(default_factory=dict)


@dataclass(frozen=True)
class Conflict:
    inputs: tuple[str, ...]
    known: str
    observed: str


class ObservationTree:
    def __init__(self, mapper: str):
        self.mapper = mapper
        self.root = _Node()
        self.conflicts: list[Conflict] = []

    def insert(self, inputs: list[str], outputs: list[str]) -> list[Conflict]:
        if len(inputs) != len(outputs):
            raise ValueError("inputs and outputs must have the same length")
        node, new = self.root, []
        for i, (a, o) in enumerate(zip(inputs, outputs, strict=True)):
            child = node.children.get(a)
            if child is None:
                child = node.children[a] = _Node(output=o)
            elif child.output != o:
                conflict = Conflict(tuple(inputs[: i + 1]), child.output or "", o)
                self.conflicts.append(conflict)
                new.append(conflict)
            child.count += 1
            node = child
        return new

    def lookup(self, inputs: list[str]) -> list[str] | None:
        node, outputs = self.root, []
        for a in inputs:
            node = node.children.get(a)
            if node is None:
                return None
            outputs.append(node.output or "")
        return outputs

    def size(self) -> int:
        stack, n = [self.root], 0
        while stack:
            node = stack.pop()
            n += len(node.children)
            stack.extend(node.children.values())
        return n
