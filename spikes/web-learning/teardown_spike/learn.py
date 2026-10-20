"""Active automata learning driver + model summary helpers."""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

from aalpy.learning_algs import run_KV, run_Lstar, run_Lsharp
from aalpy.oracles import KWayTransitionCoverageEqOracle, RandomWalkEqOracle, RandomWMethodEqOracle, StatePrefixEqOracle, WMethodEqOracle

from .abstraction import Abstraction
from .driver import WebDriver
from .sul import WebSUL

RESULTS = Path(__file__).resolve().parent.parent / 'results'
ALGOS = {'lstar': run_Lstar, 'kv': run_KV, 'lsharp': run_Lsharp}


def make_oracle(kind: str, alphabet: list, sul, **kw):
    if kind == 'rw':
        return RandomWalkEqOracle(alphabet, sul, num_steps=kw.get('num_steps', 3000), reset_after_cex=True,
                                  reset_prob=kw.get('reset_prob', 0.09))
    if kind == 'rwm':
        return RandomWMethodEqOracle(alphabet, sul, walks_per_state=kw.get('walks_per_state', 10),
                                     walk_len=kw.get('walk_len', 8))
    if kind == 'sp':
        return StatePrefixEqOracle(alphabet, sul, walks_per_state=kw.get('walks_per_state', 10),
                                   walk_len=kw.get('walk_len', 8))
    if kind == 'kway':
        return KWayTransitionCoverageEqOracle(alphabet, sul, k=kw.get('k', 2), method=kw.get('method', 'random'),
                                              num_generate_paths=kw.get('num_generate_paths', 2000),
                                              max_path_len=kw.get('max_path_len', 30))
    if kind == 'w':
        return WMethodEqOracle(alphabet, sul, max_number_of_states=kw['max_states'])
    raise ValueError(kind)


def learn(url: str, alphabet: dict, *, algo='lstar', eq='rwm', seed=1, lazy=True, reset_mode='context',
          settle='none', abstraction: Abstraction | None = None, name='run', eq_kw=None, save=True, **algo_kw):
    random.seed(seed)
    abstraction = abstraction or Abstraction()
    driver = WebDriver(url, reset_mode=reset_mode, settle=settle)
    sul = WebSUL(driver, alphabet, abstraction, lazy=lazy)
    letters = list(alphabet)
    oracle = make_oracle(eq, letters, sul, **(eq_kw or {}))
    t = time.perf_counter()
    error = None
    try:
        model, info = ALGOS[algo](letters, sul, oracle, automaton_type='mealy', return_data=True, print_level=0,
                                     **algo_kw)
    except Exception as e:  # non-determinism etc.: report how far we got instead of crashing the experiment
        model, info, error = None, {}, f'{type(e).__name__}: {e}'
    finally:
        wall = time.perf_counter() - t
        driver.close()
    info = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in info.items() if k != 'classification_tree'}
    res = dict(name=name, url=url.split('/')[-1], algo=algo, eq=eq, eq_kw=eq_kw, seed=seed, lazy=lazy,
               reset_mode=reset_mode, settle=settle, alphabet=letters, states=len(model.states) if model else None,
               wall_s=round(wall, 2), aalpy=info, sul=sul.stats(), error=error)
    res['transitions'] = len(model.states) * len(letters) if model else None
    if model is None:
        if save:
            RESULTS.mkdir(exist_ok=True)
            (RESULTS / f'{name}.json').write_text(json.dumps(res, indent=2))
        return None, res, abstraction
    if save:
        RESULTS.mkdir(exist_ok=True)
        model.save(str(RESULTS / name))
        (RESULTS / f'{name}.json').write_text(json.dumps(res, indent=2))
        (RESULTS / f'{name}.states.txt').write_text(summarize(model, abstraction))
    return model, res, abstraction


def summarize(model, abstraction: Abstraction) -> str:
    """State table: access sequence + the non-trivial transitions. Output legend at the end."""
    lines = [f'{len(model.states)} states, initial={model.initial_state.state_id}']
    for s in model.states:
        prefix = s.prefix if s.prefix is not None else model.get_shortest_path(model.initial_state, s)
        lines.append(f'\n[{s.state_id}] reached by: {" ".join(prefix) or "<reset>"}')
        for i, o in s.output_fun.items():
            dst = s.transitions[i]
            if o in ('NA', 'DISABLED') and dst is s:
                continue
            lines.append(f'    {i:>14} / {o:<26} -> {dst.state_id}')
    lines.append('\n=== output legend (normalized aria snapshot) ===')
    for sym, norm in sorted(abstraction.legend.items()):
        lines.append(f'\n## {sym}\n{norm}')
    return '\n'.join(lines)
