"""Active automata learning over an observation session (AALpy KV or L#; L* is deliberately not offered).

The spikes showed the equivalence oracle, not the learner, decides whether the model is complete: with a modest
budget every learner silently stopped at 14 of 19 states. So the result always carries the budget that was spent
and an explicit statement that completeness is not proven.
"""

from __future__ import annotations

import random
import time
import warnings
from dataclasses import dataclass, field

from teardown.core.obstree import Conflict
from teardown.drivers.session import ObservationSession
from teardown.spec.efsm import EFSM, from_mealy

ALGORITHMS = ("kv", "lsharp")


@dataclass
class LearnResult:
    model: EFSM
    algorithm: str
    budget: dict
    stats: dict
    conflicts: list[Conflict] = field(default_factory=list)

    @property
    def completeness(self) -> str:
        return (
            f"{len(self.model.states)} states found with a random-W-method oracle budget of "
            f"{self.budget['walks_per_state']}x{self.budget['walk_len']}; equivalence is not proven"
        )


def learn(
    session: ObservationSession,
    alphabet: list[str],
    *,
    name: str,
    algorithm: str = "kv",
    walks_per_state: int = 100,
    walk_len: int = 20,
    seed: int = 1,
) -> LearnResult:
    try:
        with warnings.catch_warnings():  # aalpy ships regexes with invalid escapes
            warnings.simplefilter("ignore", SyntaxWarning)
            from aalpy.base import SUL
            from aalpy.learning_algs import run_KV, run_Lsharp
            from aalpy.oracles import RandomWMethodEqOracle
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("learning needs aalpy: pip install aalpy") from exc

    if algorithm not in ALGORITHMS:
        raise ValueError(f"algorithm must be one of {ALGORITHMS}")

    class SessionSUL(SUL):
        def __init__(self):
            super().__init__()
            self.inputs: list[str] = []
            self.outputs: list[str] = []
            self.conflicts: list[Conflict] = []

        def pre(self):
            session.reset()
            self.inputs, self.outputs = [], []

        def post(self):
            if self.inputs:
                self.conflicts += session.tree.insert(self.inputs, self.outputs)

        def step(self, letter):
            _, symbol = session.step(letter)
            self.inputs.append(letter)
            self.outputs.append(symbol)
            return symbol

    random.seed(seed)
    sul = SessionSUL()
    oracle = RandomWMethodEqOracle(alphabet, sul, walks_per_state=walks_per_state, walk_len=walk_len)
    run = run_KV if algorithm == "kv" else run_Lsharp
    started = time.perf_counter()
    mealy, info = run(alphabet, sul, oracle, automaton_type="mealy", return_data=True, print_level=0)
    wall = time.perf_counter() - started
    session.close_trace()
    stats = {k: v for k, v in info.items() if isinstance(v, (int, float, str))}
    stats.update(wall_s=round(wall, 3), session=dict(session.stats))
    return LearnResult(
        model=from_mealy(mealy, name),
        algorithm=algorithm,
        budget={"oracle": "random-w-method", "walks_per_state": walks_per_state, "walk_len": walk_len, "seed": seed},
        stats=stats,
        conflicts=sul.conflicts,
    )
