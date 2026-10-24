"""Run probe batches through observation sessions, in parallel, recording evidence for every probe.

Each worker owns its own driver (for CLI: its own container session) and session; they share the workspace.
A probe is one fresh episode: reset, then one ad-hoc invocation.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from teardown.core.model import Evidence
from teardown.drivers.cli.plan import Probe
from teardown.drivers.session import ObservationSession


@dataclass
class ProbeResult:
    probe: Probe
    evidence: str
    symbol: str
    observation: dict[str, Any]


def run_probes(open_session: Callable[[], ObservationSession], probes: list[Probe], *,
               workers: int = 4) -> list[ProbeResult]:
    if not probes:
        return []
    workers = max(1, min(workers, len(probes)))
    indexed = list(enumerate(probes))
    chunks = [indexed[i::workers] for i in range(workers)]

    def work(chunk: list[tuple[int, Probe]]) -> list[tuple[int, ProbeResult]]:
        session = open_session()
        out = []
        try:
            for index, probe in chunk:
                session.reset()
                ev, symbol = session.step(probe.id, params=probe.invocation.model_dump(mode="json"))
                observation = session.workspace.get(ev, Evidence).payload
                out.append((index, ProbeResult(probe, ev, symbol, observation)))
            session.close_trace()
        finally:
            session.close()
        return out

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = [r for part in pool.map(work, chunks) for r in part]
    return [r for _, r in sorted(results, key=lambda x: x[0])]
