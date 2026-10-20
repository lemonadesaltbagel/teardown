"""Model comparison up to output renaming (needed when two abstractions hash the same page differently,
e.g. masked-noise model vs. clean model, or original vs. a clean-room clone with different wording)."""
from __future__ import annotations

from collections import deque


def equivalent_up_to_output_renaming(m1, m2, alphabet):
    """Product BFS keeping a bijection between output symbols. Returns (True, mapping) or (False, cex_inputs)."""
    fwd, bwd = {}, {}
    start = (m1.initial_state, m2.initial_state)
    seen = {start: ()}
    q = deque([start])
    while q:
        s1, s2 = q.popleft()
        path = seen[(s1, s2)]
        for a in alphabet:
            o1, o2 = s1.output_fun[a], s2.output_fun[a]
            if fwd.setdefault(o1, o2) != o2 or bwd.setdefault(o2, o1) != o1:
                return False, path + (a,)
            nxt = (s1.transitions[a], s2.transitions[a])
            if nxt not in seen:
                seen[nxt] = path + (a,)
                q.append(nxt)
    return True, fwd
