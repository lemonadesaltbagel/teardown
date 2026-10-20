"""Diffy-style noise calibration: run the same random input sequences twice (second run with timing jitter),
diff the raw aria snapshots structurally, and turn every difference into a mask:
  * same node path, different text  -> volatile_paths (text masked)
  * node present in one run only    -> flaky_role_paths (subtree dropped)
Returns an Abstraction that needs no hand-written knowledge of the target's noise."""
from __future__ import annotations

import difflib
import random
import time

from .abstraction import Abstraction, parse, role_path
from .driver import WebDriver


def _run(driver: WebDriver, alphabet: dict, seq, jitter_ms):
    driver.reset()
    snaps = [driver.snapshot()]
    for letter in seq:
        if driver.act(alphabet[letter]) is None:
            if jitter_ms:
                driver.page.wait_for_timeout(random.randint(*jitter_ms))
            snaps.append(driver.snapshot())
    return snaps


def diff_snapshots(s1: str, s2: str, volatile: set, flaky: set):
    n1, n2 = parse(s1), parse(s2)
    k1 = [(n.path, n.rest) for n in n1]
    k2 = [(n.path, n.rest) for n in n2]
    sm = difflib.SequenceMatcher(a=[k[0] for k in k1], b=[k[0] for k in k2], autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            for a, b in zip(k1[i1:i2], k2[j1:j2]):
                if a[1] != b[1]:
                    volatile.add(a[0])
        else:   # presence differs: drop the shallowest differing nodes' role paths
            nodes = n1[i1:i2] + n2[j1:j2]
            if nodes:
                top = min(n.depth for n in nodes)
                flaky.update(role_path(n.path) for n in nodes if n.depth == top)


def calibrate(driver: WebDriver, alphabet: dict, walks=15, walk_len=10, jitter_ms=(0, 900), seed=7,
              base: Abstraction | None = None) -> tuple[Abstraction, dict]:
    rnd = random.Random(seed)
    letters = list(alphabet)
    volatile, flaky = set(), set()
    t = time.perf_counter()
    for _ in range(walks):
        seq = [rnd.choice(letters) for _ in range(walk_len)]
        a = _run(driver, alphabet, seq, None)
        b = _run(driver, alphabet, seq, jitter_ms)
        for s1, s2 in zip(a, b):
            diff_snapshots(s1, s2, volatile, flaky)
    base = base or Abstraction(drop_roles=set())
    ab = Abstraction(drop_roles=set(base.drop_roles), mask_values=base.mask_values,
                     volatile_paths=volatile, flaky_role_paths=flaky, regex_masks=list(base.regex_masks))
    info = dict(walks=walks, walk_len=walk_len, jitter_ms=jitter_ms, resets=2 * walks,
                wall_s=round(time.perf_counter() - t, 2),
                volatile_paths=sorted(map(str, volatile)), flaky_role_paths=sorted(map(str, flaky)))
    return ab, info
