"""Micro-benchmark of per-reset / per-step costs for reset and settle strategies (headless Chromium)."""
import json, time
from teardown_spike.driver import LocalServer, WebDriver
from teardown_spike.abstraction import Abstraction
from teardown_spike import signup_mapper as M
from teardown_spike.learn import RESULTS

srv = LocalServer(); out = {}
seq = 'email_ok next pw_weak next pw_ok next terms back next submit'.split()
for reset in ('context', 'goto'):
    for settle in ('none', 'stable'):
        d = WebDriver(srv.url('signup_a.html'), reset_mode=reset, settle=settle); ab = Abstraction()
        t = time.perf_counter()
        for _ in range(40):
            d.reset()
            for l in seq:
                if d.act(M.ALPHABET[l]) is None:
                    ab.symbol(d.snapshot())
        wall = time.perf_counter() - t
        out[f'{reset}/{settle}'] = dict(wall_s=round(wall, 2), ms_per_query_of_10=round(1000 * wall / 40, 1), **d.m.as_dict())
        d.close()
        print(reset, settle, out[f'{reset}/{settle}'], flush=True)
(RESULTS / 'bench.json').write_text(json.dumps(out, indent=1))
