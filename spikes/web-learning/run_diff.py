"""Step 5a: conformance-test a learned model of A against B (and against A itself as the noise/incompleteness
control, Diffy-style). A discrepancy counts as a *behavior difference* only if A agrees with the model on it."""
import argparse
import json
import random
import time

from aalpy.oracles import RandomWalkEqOracle, RandomWMethodEqOracle, WMethodEqOracle
from aalpy.utils import load_automaton_from_file

from teardown_spike import signup_mapper as M
from teardown_spike.abstraction import Abstraction
from teardown_spike.driver import LocalServer, WebDriver
from teardown_spike.learn import RESULTS
from teardown_spike.sul import WebSUL

ap = argparse.ArgumentParser()
ap.add_argument('--model', required=True)
ap.add_argument('--refined', type=int, default=0)
ap.add_argument('--seeds', type=int, default=5)
ap.add_argument('--wmethod', type=int, default=1)
ap.add_argument('--name', default='diff')
a = ap.parse_args()

alpha = M.ALPHABET_REFINED if a.refined else M.ALPHABET
letters = list(alpha)
model = load_automaton_from_file(a.model, 'mealy')
srv = LocalServer()


def make_sul(target):
    return WebSUL(WebDriver(srv.url(target)), alpha, Abstraction())


def model_out(seq):
    return model.execute_sequence(model.initial_state, list(seq))


def shrink(seq, sul):
    """Greedy one-letter deletion while the trace still disagrees with the model."""
    seq = list(seq)
    tries = 0
    changed = True
    while changed:
        changed = False
        for i in range(len(seq)):
            cand = seq[:i] + seq[i + 1:]
            tries += 1
            if cand and sul.query(tuple(cand)) != model_out(cand):
                seq, changed = cand, True
                break
    return seq, tries


def verdict(seq, sul):
    obs, exp = sul.query(tuple(seq)), model_out(seq)
    k = next(i for i, (o, e) in enumerate(zip(obs, exp)) if o != e)
    return dict(inputs=seq, diverges_at=k, expected=exp[k], observed=obs[k])


def run(kind, seed, target):
    random.seed(seed)
    sul = make_sul(target)
    if kind == 'rwm':
        oracle = RandomWMethodEqOracle(letters, sul, walks_per_state=25, walk_len=12)
    elif kind == 'rw':
        oracle = RandomWalkEqOracle(letters, sul, num_steps=5000, reset_prob=0.09)
    else:
        oracle = WMethodEqOracle(letters, sul, max_number_of_states=len(model.states))
    t = time.perf_counter()
    cex = oracle.find_cex(model)
    rec = dict(oracle=kind, seed=seed, target=target, found=cex is not None,
               oracle_queries=oracle.num_queries, oracle_steps=oracle.num_steps,
               real_resets=sul.d.m.resets, wall_s=round(time.perf_counter() - t, 2))
    if cex is not None:
        cex_list = list(cex)
        small, tries = shrink(cex_list, sul)
        rec.update(cex_len=len(cex_list), shrunk=verdict(small, sul), shrink_queries=tries)
        # three-way check: does the ORIGINAL also disagree with the model here? then it's model incompleteness
        sa = sul if target == 'signup_a.html' else make_sul('signup_a.html')
        rec['A_agrees_with_model'] = sa.query(tuple(small)) == model_out(small)
        rec['classification'] = ('behavior-difference' if rec['A_agrees_with_model'] else 'model-incomplete')
        if sa is not sul:
            sa.d.close()
    rec['total_wall_s'] = round(time.perf_counter() - t, 2)
    sul.d.close()
    return rec


out = []
for target in ('signup_b.html', 'signup_a.html'):
    for seed in range(1, a.seeds + 1):
        out.append(run('rwm', seed, target))
        out.append(run('rw', seed, target))
        print(json.dumps(out[-2]), '\n', json.dumps(out[-1]), flush=True)
    if a.wmethod:
        out.append(run('w', 0, target))
        print(json.dumps(out[-1]), flush=True)
(RESULTS / f'{a.name}.json').write_text(json.dumps(dict(model=a.model, states=len(model.states), runs=out), indent=1))
