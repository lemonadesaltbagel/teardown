"""Mapper: turns a concrete observation into an abstract output symbol.

The mapper is data (a list of :class:`MapperRule`), so it is deterministic, versioned by content hash, reviewable,
and can be re-applied to cached traces when it is refined. In production an LLM proposes the rules; nothing here
calls a model.

A symbol is the canonical JSON of the abstracted observation. That keeps symbols *semantic* (a clean-room clone
that exposes the same abstract observation produces the same symbol) instead of opaque hashes, which only work
when comparing a program against a modified copy of itself.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any

from teardown.core.ids import canonical_json
from teardown.core.model import MapperRule, MapperVersion
from teardown.engine.abstractions import BUILTINS

NOT_AVAILABLE = "NA"


class Mapper:
    def __init__(self, version: MapperVersion):
        self.version = version
        self._compiled = [
            (rule, [(re.compile(rx), cls) for rx, cls in rule.classes]) for rule in version.rules
        ]
        self._cache: dict[bytes, str] = {}
        if version.builtin is not None and version.builtin not in BUILTINS:
            raise ValueError(f"unknown built-in abstraction {version.builtin!r}; known: {sorted(BUILTINS)}")
        self._builtin = BUILTINS.get(version.builtin) if version.builtin else None

    @property
    def id(self) -> str:
        return self.version.id

    def abstract(self, observation: Any) -> dict[str, Any] | str:
        """The abstract observation (still structured)."""
        if observation is None or isinstance(observation, str):
            return observation if observation is not None else NOT_AVAILABLE
        value = copy.deepcopy(observation)
        if self._builtin is not None:
            value = self._builtin(value, self.version.params)
            if not isinstance(value, dict):
                return value
        for rule, classes in self._compiled:
            _apply(value, rule.path.split("."), rule, classes)
        return value

    def symbol(self, observation: Any) -> str:
        key = canonical_json(observation)
        cached = self._cache.get(key)
        if cached is None:
            abstract = self.abstract(observation)
            cached = abstract if isinstance(abstract, str) else canonical_json(abstract).decode()
            self._cache[key] = cached
        return cached


def describe_symbol(symbol: str) -> Any:
    """Parse a symbol back into its abstract observation, for specs and verdicts."""
    try:
        return json.loads(symbol)
    except json.JSONDecodeError:
        return symbol


def _apply(node: Any, path: list[str], rule: MapperRule, classes) -> None:
    if not isinstance(node, dict) or not path:
        return
    head, rest = path[0], path[1:]
    keys = list(node) if head == "*" else ([head] if head in node else [])
    for key in keys:
        if rest:
            _apply(node[key], rest, rule, classes)
            continue
        if rule.op == "drop":
            del node[key]
        elif rule.op == "mask":
            if node[key] is not None:
                node[key] = rule.value
        elif rule.op == "classify":
            node[key] = _classify(node[key], classes, rule.default)
        elif rule.op == "rename":
            node[rule.value or key] = node.pop(key)
        else:
            raise ValueError(f"unknown mapper op {rule.op!r}")


def _classify(value: Any, classes, default: str | None) -> Any:
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    for rx, cls in classes:
        if rx.search(text):
            return cls
    return default if default is not None else "<unclassified>"


def symbol_matches(observed: str, expected: str | None, match: str = "exact") -> bool:
    """Exact symbol equality, or (match="subset") every key of the expected object equals the observed one's."""
    if expected is None:
        return True
    if match == "exact":
        # structural, not textual: renaming (codenames) can reorder keys of an otherwise identical symbol
        return observed == expected or describe_symbol(observed) == describe_symbol(expected)
    want, got = describe_symbol(expected), describe_symbol(observed)
    if isinstance(want, dict) and not isinstance(got, dict):
        got = {"value": got}  # non-dict symbols (NA, DISABLED) are written {"value": ...} in outcome expectations
    if not isinstance(want, dict) or not isinstance(got, dict):
        return observed == expected
    return _subset(want, got)


def _subset(want: dict, got: dict, top: bool = True) -> bool:
    """Every expected key matches; nested objects (e.g. ``controls``) are subsets too, so an expectation can name
    one control without listing all of them. At the top level an expected empty list or null also matches an
    absent key (abstractions omit empty collections); inside a nested object an expected key must exist (a
    control expected with no flags, ``"button:Save": []``, is a control that is there)."""
    for k, v in want.items():
        if k not in got:
            if not top or (v != [] and v is not None):
                return False
        elif isinstance(v, dict) and isinstance(got[k], dict):
            if not _subset(v, got[k], top=False):
                return False
        elif got[k] != v:
            return False
    return True
