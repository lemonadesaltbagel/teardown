from __future__ import annotations

import json
import warnings
from collections import deque

import pytest

from teardown.core.store import Workspace
from teardown.drivers.fake import open_fake
from teardown.drivers.session import ObservationSession
from teardown.engine.mapper import NOT_AVAILABLE, Mapper
from teardown.examples.signup import ACTIONS, SignupWizard, signup_mapper


@pytest.fixture
def workspace(tmp_path) -> Workspace:
    return Workspace(tmp_path / "ws")


@pytest.fixture
def signup_session(workspace) -> ObservationSession:
    driver = open_fake("fake:signup-a")
    return ObservationSession(workspace, driver, Mapper(signup_mapper(driver.target_fingerprint())))


def ground_truth_states(make_app, mapper: Mapper, alphabet: list[str]) -> int:
    """Experimenter-side truth: BFS over the app's concrete states, then Mealy minimization."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        from aalpy.automata import MealyMachine, MealyState

    def snapshot(app):
        return json.dumps(vars(app), sort_keys=True, default=str)

    def restore(blob):
        app = make_app()
        app.__dict__.update(json.loads(blob))
        return app

    start = make_app()
    start.reset()
    init = snapshot(start)
    states, queue = {init: MealyState("s0")}, deque([init])
    while queue:
        cur = queue.popleft()
        for a in alphabet:
            app = restore(cur)
            out = mapper.symbol(app.observe()) if app.act(a, {}) else NOT_AVAILABLE
            nxt = snapshot(app)
            if nxt not in states:
                states[nxt] = MealyState(f"s{len(states)}")
                queue.append(nxt)
            states[cur].transitions[a] = states[nxt]
            states[cur].output_fun[a] = out
    machine = MealyMachine(states[init], list(states.values()))
    machine.minimize()
    return len(machine.states)


@pytest.fixture
def signup_truth():
    def _truth(mapper: Mapper, alphabet=ACTIONS, **kwargs) -> int:
        return ground_truth_states(lambda: SignupWizard(**kwargs), mapper, alphabet)

    return _truth
