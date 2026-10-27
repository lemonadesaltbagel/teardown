"""Driver contract shared by every platform adapter (cli, web, android, desktop, ios, fake).

A driver only *acts* and *observes*. It never decides what a state is (that is the mapper's job) and it never
returns implementation-tier data. Every call goes through :class:`teardown.drivers.session.ObservationSession`,
which records evidence and enforces the hard refusals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from teardown.core.model import ObservationTier


class DeviceLost(RuntimeError):
    """The device under observation went away mid-episode (an emulator crashed). The episode's observations are not
    the target's behavior; a caller may retry the episode once the driver has brought the device back."""


class Action(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    params: dict[str, Any] = Field(default_factory=dict)
    category: str = Field(default="ui", description="What kind of act this is; used by the hard-refusal policy.")


class DriverCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    platform: str
    reset_cost_ms: float = Field(description="Typical cost of a hard reset; drives the learning strategy.")
    soft_reset: bool = False
    snapshots: bool = False
    parallelism: int = 1
    tiers: list[ObservationTier] = Field(default_factory=lambda: [ObservationTier.BEHAVIOR])


class Driver(ABC):
    """One running instance of one target."""

    name: str = "driver"

    @abstractmethod
    def target_fingerprint(self) -> str:
        """Stable identity of the build under observation (version, digest, URL+build id, ...)."""

    @abstractmethod
    def capabilities(self) -> DriverCapabilities: ...

    @abstractmethod
    def reset(self) -> Any:
        """Return the target to its initial state and return the initial observation."""

    @abstractmethod
    def step(self, action: Action) -> Any | None:
        """Apply one action and return the resulting observation, or None if the action is not available."""

    @abstractmethod
    def observe(self) -> Any: ...

    def actions(self) -> list[str]:
        """Actions the driver can discover on its own (menu items, options, controls). May be empty."""
        return []

    def close(self) -> None:  # noqa: B027 - optional hook
        pass
