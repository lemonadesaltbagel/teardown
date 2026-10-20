"""Algorithmic cost on the in-memory ground truth (no browser): true state count, and queries/steps/resets per
learner x oracle. Also synthetic random Mealy machines (50 states x 20 inputs) for extrapolation."""
import json, random, time
from aalpy.learning_algs import run_KV, run_Lstar, run_Lsharp
from aalpy.oracles import RandomWMethodEqOracle, WMethodEqOracle, KWayTransitionCoverageEqOracle, PerfectKnowledgeEqOracle
from aalpy.SULs import MealySUL
from aalpy.utils import generate_random_mealy_machine
from teardown_spike.sim import SignupSim, ground_truth
from teardown_spike.compare import equivalent_up_to_output_renaming
from teardown_spike.learn import RESULTS

L = ['email_ok', 'email_bad', 'pw_ok', 'pw_weak', 'terms', 'next', 'back', 'submit', 'restart']
ALGOS = {'lstar': run_Lstar, 'kv': run_KV, 'lsharp': run_Lsharp}
out = {}

def go(algo, sul, alphabet, oracle_fn, seed=1):
    random.seed(seed)
    o = oracle_fn(alphabet, sul)
    t = time.perf_counter()
    m, info = ALGOS[algo](alphabet, sul, o, automaton_type='mealy', return_data=True, print_level=0)
    # AALpy counts: queries_learning = cache-missing MQs (each one reset), eq oracle queries = each one reset
    return m, dict(states=len(m.states), rounds=info['learning_rounds'],
                   mq=info['queries_learning'], mq_steps=info['steps_learning'],
                   eq=info['queries_eq_oracle'], eq_steps=info['steps_eq_oracle'],
                   resets=info['queries_learning'] + info['queries_eq_oracle'],
                   steps=info['steps_learning'] + info['steps_eq_oracle'], cpu_s=round(time.perf_counter() - t, 2))

# 1. ground truth (explicit BFS + minimization -> exact)
truth, conc = ground_truth(SignupSim(), L)
truth_b, conc_b = ground_truth(SignupSim(clear_pw_on_back=True), L)
out['truth'] = dict(concrete_states=conc, minimal_states=len(truth.states))
out['truth_B'] = dict(concrete_states=conc_b, minimal_states=len(truth_b.states))
print(out['truth'], out['truth_B'], flush=True)
truth.save(str(RESULTS / 'sim_truth_A')); truth_b.save(str(RESULTS / 'sim_truth_B'))
oracles = {
    'rwm25x12': lambda a, s: RandomWMethodEqOracle(a, s, walks_per_state=25, walk_len=12),
    'rwm100x20': lambda a, s: RandomWMethodEqOracle(a, s, walks_per_state=100, walk_len=20),
    'kway2': lambda a, s: KWayTransitionCoverageEqOracle(a, s, k=2, num_generate_paths=2000, max_path_len=30),
    'perfect': lambda a, s: PerfectKnowledgeEqOracle(a, s, truth),
}
for algo in ALGOS:
    for oname, ofn in oracles.items():
        rows = []
        for seed in range(1, 6 if oname != 'perfect' else 2):
            m, r = go(algo, SignupSim(), L, ofn, seed)
            r['correct'] = equivalent_up_to_output_renaming(m, truth, L)[0]
            rows.append(r)
        out[f'signup/{algo}/{oname}'] = rows
        print(algo, oname, [(x['states'], x['resets'], x['steps'], x['correct']) for x in rows], flush=True)

# 2. synthetic: 50 states x 20 inputs x 10 outputs, perfect oracle and a random W-method oracle
for n, k in ((19, 9), (50, 20), (200, 20)):
    for algo in ('lstar', 'kv', 'lsharp'):
        rows = []
        for seed in range(3):
            random.seed(seed)
            tm = generate_random_mealy_machine(n, list(range(k)), list(range(10)))
            for oname, ofn in (('perfect', lambda a, s, tm=tm: PerfectKnowledgeEqOracle(a, s, tm)),
                               ('rwm25x12', lambda a, s: RandomWMethodEqOracle(a, s, walks_per_state=25, walk_len=12))):
                m, r = go(algo, MealySUL(tm), list(range(k)), ofn, seed)
                r['oracle'] = oname; r['correct'] = len(m.states) == len(tm.states)
                rows.append(r)
        out[f'random_{n}x{k}/{algo}'] = rows
        print(n, k, algo, [(x['oracle'], x['states'], x['resets'], x['steps'], x['correct']) for x in rows], flush=True)
(RESULTS / 'sim_costs.json').write_text(json.dumps(out, indent=1))
