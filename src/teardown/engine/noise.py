"""Noise calibration (Diffy-style plus a reprotest-style variation sweep).

Every probe runs twice in different orders and batch boundaries; any probe whose symbol differs between the two
runs is nondeterministic. Then a sample of probes re-runs with one environment variable changed at a time; a
difference there is not noise but an *environment dependence*, which becomes a claim of its own.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from teardown.drivers.cli.plan import Probe
from teardown.drivers.session import ObservationSession
from teardown.engine.probing import ProbeResult, run_probes

DEFAULT_VARIATIONS: dict[str, str] = {"TZ": "Asia/Kathmandu", "LC_ALL": "C.UTF-8", "LANG": "C.UTF-8"}


class NoiseReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probes: int
    nondeterministic: list[str] = Field(default_factory=list)
    env_dependent: dict[str, list[str]] = Field(default_factory=dict, description="variable -> probe ids")
    sampled_for_env: int = 0


def calibrate(open_session: Callable[[], ObservationSession], probes: list[Probe], first: list[ProbeResult], *,
              variations: dict[str, str] | None = None, env_sample: int = 200, workers: int = 4) -> NoiseReport:
    """``first`` is the already-executed baseline run; this adds a reordered rerun and the variation sweep."""
    second = run_probes(open_session, list(reversed(probes)), workers=workers)
    by_id = {r.probe.id: r.symbol for r in second}
    nondet = sorted(r.probe.id for r in first if by_id.get(r.probe.id) != r.symbol)

    stable = [r for r in first if r.probe.id not in set(nondet)]
    step = max(1, len(stable) // max(1, env_sample))
    sample = stable[::step][:env_sample]
    env_dependent: dict[str, list[str]] = {}
    for var, value in (variations if variations is not None else DEFAULT_VARIATIONS).items():
        varied, origin = [], {}
        for r in sample:
            if r.probe.invocation.env.get(var) == value:
                continue
            inv = r.probe.invocation.model_copy(update={"env": {**r.probe.invocation.env, var: value}})
            p = Probe(id=f"{r.probe.id}~{var}", invocation=inv, tags=[*r.probe.tags, f"vary:{var}"])
            varied.append(p)
            origin[p.id] = r
        changed = [origin[v.probe.id].probe.id for v in run_probes(open_session, varied, workers=workers)
                   if v.symbol != origin[v.probe.id].symbol]
        if changed:
            env_dependent[var] = sorted(changed)
    return NoiseReport(probes=len(probes), nondeterministic=nondet, env_dependent=env_dependent,
                       sampled_for_env=len(sample))


def outcome_class(symbol: Any) -> dict[str, Any]:
    """The part of a CLI behavior symbol that decides accept/refuse: exit, signal, timeout, diagnostic, errno."""
    if not isinstance(symbol, dict):
        return {"value": symbol}
    keys = ("exit", "signal", "timed_out", "diagnostic", "errno")
    return {k: symbol[k] for k in keys if k in symbol}
