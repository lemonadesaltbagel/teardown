"""Step 6: nondeterministic UI noise (random 'N people signed up' counter + timestamped toasts that vanish after
200-800 ms) vs. the abstraction. Each variant learns signup_a.html?noise=1 and is compared with the clean model."""
import argparse
import json

from aalpy.utils import load_automaton_from_file

from teardown_spike import signup_mapper as M
from teardown_spike.abstraction import HEURISTIC_MASKS, RAW, Abstraction
from teardown_spike.calibrate import calibrate
from teardown_spike.compare import equivalent_up_to_output_renaming
from teardown_spike.driver import LocalServer, WebDriver
from teardown_spike.learn import RESULTS, learn

ap = argparse.ArgumentParser()
ap.add_argument('--algo', default='kv')
ap.add_argument('--eq', default='rwm')
ap.add_argument('--eq-kw', default='{"walks_per_state":25,"walk_len":12}')
ap.add_argument('--clean-model', required=True)
ap.add_argument('--only', default='')
a = ap.parse_args()

srv = LocalServer()
url = srv.url('signup_a.html', 'noise=1')
clean = load_automaton_from_file(a.clean_model, 'mealy')
letters = list(M.ALPHABET)


def calibrated(jitter):
    d = WebDriver(url)
    ab, info = calibrate(d, M.ALPHABET, walks=15, walk_len=10, jitter_ms=jitter)
    d.close()
    return ab, info


variants = {
    'raw': lambda: (Abstraction(**RAW), None),
    'default_drop_status_only': lambda: (Abstraction(), None),
    'heuristic_regex_plus_drop_status': lambda: (Abstraction(regex_masks=HEURISTIC_MASKS), None),
    'calibrated_no_jitter': lambda: calibrated(None),
    'calibrated_jitter': lambda: calibrated((0, 900)),
}
out = {}
for vname, mk in variants.items():
    if a.only and vname not in a.only.split(','):
        continue
    ab, cal = mk()
    model, res, _ = learn(url, M.ALPHABET, algo=a.algo, eq=a.eq, eq_kw=json.loads(a.eq_kw), abstraction=ab,
                          name=f'noise_{vname}')
    rec = dict(calibration=cal, states=res['states'], error=res['error'], wall_s=res['wall_s'],
               resets=res['sul']['real_resets'], aalpy={k: res['aalpy'].get(k) for k in
                                                        ('queries_learning', 'queries_eq_oracle', 'learning_rounds')})
    if model is not None:
        ok, detail = equivalent_up_to_output_renaming(model, clean, letters)
        rec['equivalent_to_clean_model'] = ok
        rec['detail'] = detail if not ok else f'{len(detail)} output symbols mapped 1:1'
    out[vname] = rec
    print(vname, json.dumps(rec, default=str), flush=True)
(RESULTS / f'noise_summary{"_" + a.only if a.only else ""}.json').write_text(json.dumps(out, indent=1, default=str))
