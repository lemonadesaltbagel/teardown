"""CLI driver: actions are named invocations; an episode is one work directory between resets.

Target specs::

    cli:docker:<image>      run inside a locked-down container session (default for anything portable)
    cli:local               run on the host in a scratch directory (no isolation; native tools only)

An action is either a name from the action table (what learners and claims use) or an ad-hoc invocation passed in
``Action.params`` (what probe batches use). An invocation that carries seed files starts a fresh episode.
"""

from __future__ import annotations

from typing import Any

from teardown.core.ids import content_id
from teardown.drivers.base import Action, Driver, DriverCapabilities
from teardown.drivers.cli.invocation import Invocation
from teardown.drivers.cli.runner import ContainerRunner, LocalRunner, Runner


def make_runner(target_spec: str) -> Runner:
    rest = target_spec.removeprefix("cli:")
    if rest.startswith("docker:"):
        return ContainerRunner(rest.removeprefix("docker:"))
    if rest == "local":
        return LocalRunner()
    raise ValueError(f"unknown CLI target spec {target_spec!r}; use cli:docker:<image> or cli:local")


class CliDriver(Driver):
    name = "cli"

    def __init__(self, target_spec: str, actions: dict[str, Invocation] | None = None,
                 seed: dict[str, str] | None = None):
        self.target_spec = target_spec
        self.table = dict(actions or {})
        self.seed = dict(seed or {})
        self.runner = make_runner(target_spec)
        self._fingerprint: str | None = None

    def target_fingerprint(self) -> str:
        if self._fingerprint is None:
            self._fingerprint = content_id("tgt", {"platform": "cli", "spec": self.target_spec,
                                                   "runner": self.runner.fingerprint()})
        return self._fingerprint

    def capabilities(self) -> DriverCapabilities:
        container = isinstance(self.runner, ContainerRunner)
        return DriverCapabilities(platform="cli", reset_cost_ms=25.0 if container else 5.0, soft_reset=True,
                                  snapshots=False, parallelism=8 if container else 1)

    def reset(self) -> Any:
        self.runner.reset(self.seed)
        return {"reset": True, "seed": sorted(self.seed)}

    def step(self, action: Action) -> Any | None:
        invocation = self.resolve(action)
        if invocation is None:
            return None
        if invocation.files:
            self.runner.reset({**self.seed, **invocation.files})
            invocation = invocation.model_copy(update={"files": {}})
        return self.runner.run(invocation)

    def resolve(self, action: Action) -> Invocation | None:
        if action.params:
            return Invocation.model_validate(action.params)
        return self.table.get(action.name)

    def observe(self) -> Any:
        return {"note": "CLI targets have no ambient state to observe; inspect the last step's observation"}

    def actions(self) -> list[str]:
        return sorted(self.table)

    def close(self) -> None:
        self.runner.close()
