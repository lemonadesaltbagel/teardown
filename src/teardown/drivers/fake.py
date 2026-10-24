"""In-memory driver for tests and demos: a target is any object implementing :class:`FakeApp`.

Clean-side clones for the fake platform are Python classes too. Phase 0 loads them in-process; Phase 3 moves clone
execution into a sandbox, because clone code is untrusted from the dirty side's point of view.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any, Protocol

from teardown.core.ids import content_id
from teardown.drivers.base import Action, Driver, DriverCapabilities


class FakeApp(Protocol):
    def reset(self) -> None: ...
    def act(self, name: str, params: dict[str, Any]) -> bool:
        """Apply an action; return False if it is not available in the current state."""
    def observe(self) -> Any: ...


class FakeDriver(Driver):
    name = "fake"

    def __init__(self, app_factory: Callable[[], FakeApp], label: str, actions: list[str] | None = None):
        self._factory = app_factory
        self._label = label
        self._actions = list(actions or [])
        self._app: FakeApp | None = None

    def target_fingerprint(self) -> str:
        return content_id("tgt", {"platform": "fake", "label": self._label})

    def capabilities(self) -> DriverCapabilities:
        return DriverCapabilities(platform="fake", reset_cost_ms=0.0, soft_reset=True, snapshots=True, parallelism=8)

    def reset(self) -> Any:
        self._app = self._factory()
        self._app.reset()
        return self._app.observe()

    def step(self, action: Action) -> Any | None:
        if self._app is None:
            self.reset()
        assert self._app is not None
        return self._app.observe() if self._app.act(action.name, action.params) else None

    def observe(self) -> Any:
        if self._app is None:
            return self.reset()
        return self._app.observe()

    def actions(self) -> list[str]:
        return list(self._actions)


_REGISTRY: dict[str, tuple[Callable[[], FakeApp], list[str]]] = {}


def register_fake(label: str, factory: Callable[[], FakeApp], actions: list[str] | None = None) -> None:
    _REGISTRY[label] = (factory, list(actions or []))


def open_fake(spec: str) -> FakeDriver:
    """``fake:<registered label>`` or ``fake:py:<module>:<class>``."""
    rest = spec.removeprefix("fake:")
    if rest.startswith("py:"):
        _, module, attr = rest.split(":", 2)
        cls = getattr(importlib.import_module(module), attr)
        return FakeDriver(cls, label=f"py:{module}:{attr}", actions=list(getattr(cls, "ACTIONS", [])))
    if rest not in _REGISTRY:
        _load_examples()
    if rest not in _REGISTRY:
        raise KeyError(f"unknown fake target {rest!r}; registered: {sorted(_REGISTRY)}")
    factory, actions = _REGISTRY[rest]
    return FakeDriver(factory, label=rest, actions=actions)


def _load_examples() -> None:
    importlib.import_module("teardown.examples.signup")
