"""Steps 4 + 5b: derive the email input-domain rule on A, then (i) replay A's probe suite on B, (ii) re-derive on B."""
import json, time
from teardown_spike.driver import LocalServer, WebDriver
from teardown_spike.probe import FieldProber, derive_email_rule
from teardown_spike.learn import RESULTS

srv = LocalServer()
out = {}
for tgt in ('signup_a.html', 'signup_b.html'):
    d = WebDriver(srv.url(tgt))
    t = time.perf_counter()
    p = FieldProber(d)
    res = derive_email_rule(p)
    res['wall_s'] = round(time.perf_counter() - t, 2)
    res['driver'] = d.m.as_dict()
    res['log'] = [(v if len(v) < 60 else f'<{len(v)} chars>', r) for v, r in p.log]
    out[tgt] = res
    if tgt == 'signup_a.html':
        suite_a = list(p.log)
    d.close()

# (i) replay A's exact probe suite on B: a pure regression check, no re-derivation
d = WebDriver(srv.url('signup_b.html'))
pb = FieldProber(d)
t = time.perf_counter()
diffs = [(v if len(v) < 60 else f'<{len(v)} chars>', va, pb.probe(v)) for v, va in suite_a]
diffs = [x for x in diffs if x[1] != x[2]]
out['replay_A_suite_on_B'] = dict(probes=pb.probes, wall_s=round(time.perf_counter() - t, 2),
                                  differences=diffs, error_classes_B={v: k for k, v in pb.error_classes.items()})
d.close()
ra, rb = out['signup_a.html']['rule'], out['signup_b.html']['rule']
out['rule_diff'] = {k: (ra.get(k), rb.get(k)) for k in set(ra) | set(rb) if ra.get(k) != rb.get(k)}
RESULTS.mkdir(exist_ok=True)
(RESULTS / 'probe_email.json').write_text(json.dumps(out, indent=2, ensure_ascii=False))
print(json.dumps({k: (v if k in ('rule_diff', 'replay_A_suite_on_B') else {kk: v[kk] for kk in ('rule', 'probes', 'wall_s', 'error_classes')}) for k, v in out.items()}, indent=1, ensure_ascii=False))
