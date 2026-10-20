"""Observation session: the only way the engine touches a driver.

Every reset, step and observation becomes content-addressed evidence in the workspace; every run becomes a trace
and is inserted into the observation tree, so conflicts surface instead of being overwritten.
"""

from __future__ import annotations

import uuid
from typing import Any

from teardown.core.model import Evidence, ObservationTier, Trace
from teardown.core.obstree import Conflict, ObservationTree
from teardown.core.store import Workspace
from teardown.drivers.base import Action, Driver
from teardown.drivers.policy import RateLimiter, check_action
from teardown.engine.mapper import NOT_AVAILABLE, Mapper


class ObservationSession:
    def __init__(
        self,
        workspace: Workspace,
        driver: Driver,
        mapper: Mapper,
        *,
        session_id: str | None = None,
        max_actions_per_second: float | None = None,
    ):
        self.workspace = workspace
        self.driver = driver
        self.mapper = mapper
        self.session_id = session_id or f"ses_{uuid.uuid4().hex[:16]}"
        self.target = driver.target_fingerprint()
        self.tree = ObservationTree(mapper.id)
        self._limiter = RateLimiter(max_actions_per_second)
        self._seq = 0
        self._reset_ev: str | None = None
        self._steps: list[tuple[str, str]] = []
        self.stats = {"resets": 0, "steps": 0, "cache_hits": 0}

    # -- primitive operations ----------------------------------------------------------------------------------
    def reset(self) -> tuple[str, str]:
        self._flush_trace()
        payload = self.driver.reset()
        self.stats["resets"] += 1
        ev = self._record("reset", None, payload)
        self._reset_ev, self._steps = ev, []
        return ev, self.mapper.symbol(payload)

    def step(self, name: str, params: dict[str, Any] | None = None, category: str = "ui") -> tuple[str, str]:
        action = Action(name=name, params=params or {}, category=category)
        check_action(action)
        if self._reset_ev is None:
            self.reset()
        self._limiter.wait()
        payload = self.driver.step(action)
        self.stats["steps"] += 1
        if payload is None:
            ev = self._record("step", action, {"unavailable": name})
            symbol = NOT_AVAILABLE
        else:
            ev = self._record("step", action, payload)
            symbol = self.mapper.symbol(payload)
        self._steps.append((name, ev))
        return ev, symbol

    def observe(self) -> tuple[str, str]:
        payload = self.driver.observe()
        return self._record("observe", None, payload), self.mapper.symbol(payload)

    # -- query interface used by learners and probes -----------------------------------------------------------
    def run(self, inputs: list[str], *, use_cache: bool = True) -> tuple[list[str], list[str], list[Conflict]]:
        """Reset, apply ``inputs``, return (output symbols, evidence ids, new conflicts)."""
        if use_cache:
            cached = self.tree.lookup(inputs)
            if cached is not None:
                self.stats["cache_hits"] += 1
                return cached, [], []
        self.reset()
        outputs, evidence = [], []
        for name in inputs:
            ev, symbol = self.step(name)
            outputs.append(symbol)
            evidence.append(ev)
        conflicts = self.tree.insert(list(inputs), outputs)
        self._flush_trace()
        return outputs, evidence, conflicts

    def close_trace(self) -> None:
        """Persist the in-progress trace (learners call this after their last query)."""
        self._flush_trace()

    def close(self) -> None:
        self._flush_trace()
        self.driver.close()

    # -- internals ---------------------------------------------------------------------------------------------
    def _record(self, operation: str, action: Action | None, payload: Any) -> str:
        ev = Evidence(
            session=self.session_id,
            seq=self._seq,
            target=self.target,
            driver=self.driver.name,
            operation=operation,
            action=action.model_dump() if action else None,
            payload=payload,
            tier=ObservationTier.BEHAVIOR,
        )
        self._seq += 1
        return self.workspace.put(ev)

    def _flush_trace(self) -> None:
        if self._reset_ev is not None and self._steps:
            self.workspace.put(
                Trace(session=self.session_id, target=self.target, reset_evidence=self._reset_ev, steps=self._steps)
            )
        self._reset_ev, self._steps = None, []
