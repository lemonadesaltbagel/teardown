"""Step 3: learn Target A with several learners / oracles and record cost metrics."""
import argparse, json
from teardown_spike.driver import LocalServer
from teardown_spike.learn import learn
from teardown_spike import signup_mapper as M

ap = argparse.ArgumentParser()
ap.add_argument('--target', default='signup_a.html')
ap.add_argument('--algo', default='lstar')
ap.add_argument('--eq', default='rwm')
ap.add_argument('--lazy', type=int, default=1)
ap.add_argument('--reset', default='context')
ap.add_argument('--settle', default='none')
ap.add_argument('--refined', type=int, default=0)
ap.add_argument('--fast', type=int, default=0)
ap.add_argument('--seed', type=int, default=1)
ap.add_argument('--name')
ap.add_argument('--eq-kw', default='{}')
a = ap.parse_args()
srv = LocalServer()
alpha = M.ALPHABET_REFINED if a.refined else (M.ALPHABET_FAST if a.fast else M.ALPHABET)
name = a.name or f"learn_{a.target.split('.')[0]}_{a.algo}_{a.eq}_lazy{a.lazy}_{a.reset}_{a.settle}{'_refined' if a.refined else ''}"
model, res, _ = learn(srv.url(a.target), alpha, algo=a.algo, eq=a.eq, lazy=bool(a.lazy), reset_mode=a.reset,
                      settle=a.settle, seed=a.seed, name=name, eq_kw=json.loads(a.eq_kw))
print(json.dumps(res, indent=1))
