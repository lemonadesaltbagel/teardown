"""Unbounded data (TodoMVC): without a cap the learner keeps discovering 'new' states (one per item count);
with a mapper-level cap it converges."""
import json
from teardown_spike.driver import LocalServer
from teardown_spike.learn import learn, RESULTS
from teardown_spike.todo_mapper import make_alphabet

srv = LocalServer(); url = srv.url('todo.html'); out = {}
for cap in (2, 3):
    m, r, _ = learn(url, make_alphabet(cap), algo='kv', eq='rwm', eq_kw=dict(walks_per_state=50, walk_len=15),
                    name=f'todo_cap{cap}')
    out[f'cap{cap}'] = {k: r[k] for k in ('states', 'wall_s', 'error')} | {'resets': r['sul']['real_resets'],
                        'steps': r['sul']['live_steps'] + r['sul']['replay_steps'], 'rounds': r['aalpy'].get('learning_rounds')}
    print(cap, out[f'cap{cap}'], flush=True)
for rounds in (1, 2, 3, 4):
    m, r, _ = learn(url, make_alphabet(None), algo='kv', eq='rwm', eq_kw=dict(walks_per_state=50, walk_len=15),
                    name=f'todo_nocap_r{rounds}', max_learning_rounds=rounds)
    out[f'nocap_rounds{rounds}'] = {k: r[k] for k in ('states', 'wall_s', 'error')} | {'resets': r['sul']['real_resets']}
    print('nocap', rounds, out[f'nocap_rounds{rounds}'], flush=True)
(RESULTS / 'todo_summary.json').write_text(json.dumps(out, indent=1))
