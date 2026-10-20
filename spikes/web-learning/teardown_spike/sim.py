"""Experimenter-side ground truth: an in-memory re-statement of the wizard's *observable* behavior (written from the
test author's knowledge of what Target A is supposed to do, NOT used by the black-box loop). Used to (1) know the true
minimal state count, (2) replay learner/oracle configurations in milliseconds to separate algorithmic query cost
from browser cost, and (3) audit the browser-learned models."""
from __future__ import annotations

from aalpy.base import SUL


class SignupSim(SUL):
    def __init__(self, clear_pw_on_back=False):
        super().__init__()
        self.clear_pw_on_back = clear_pw_on_back

    def pre(self):
        self.s = dict(step=1, email='', pw='', terms=False, err=False, done=False)

    def post(self):
        pass

    def _obs(self):
        s = self.s
        if s['done']:
            return 'done'
        if s['step'] == 1:
            return f"p1|email={'filled' if s['email'] else 'empty'}|err={s['err'] or '-'}"
        if s['step'] == 2:
            return f"p2|pw={'filled' if s['pw'] else 'empty'}|strength={s['pw'] or '-'}|err={s['err'] or '-'}"
        return f"p3|terms={s['terms']}"

    def step(self, a):
        s = self.s
        st = s['step'] if not s['done'] else 'done'
        if a == 'restart':
            self.pre()
            return self._obs()
        if st == 'done':
            return 'NA'
        if a in ('email_ok', 'email_bad'):
            if st != 1:
                return 'NA'
            s['email'], s['err'] = ('ok' if a == 'email_ok' else 'bad'), False
        elif a in ('pw_ok', 'pw_weak'):
            if st != 2:
                return 'NA'
            s['pw'], s['err'] = ('ok' if a == 'pw_ok' else 'weak'), False
        elif a == 'terms':
            if st != 3:
                return 'NA'
            s['terms'] = not s['terms']
        elif a == 'next':
            if st == 3:
                return 'NA'
            if st == 1:
                if s['email'] == 'ok':
                    s['step'], s['err'] = 2, False
                else:
                    s['err'] = s['email'] or 'empty'
            else:
                if s['pw'] == 'ok':
                    s['step'], s['err'] = 3, False
                else:
                    s['err'] = s['pw'] or 'empty'
        elif a == 'back':
            if st == 1:
                return 'NA'
            if st == 3 and self.clear_pw_on_back:
                s['pw'] = ''
            s['step'], s['err'] = st - 1, False
        elif a == 'submit':
            if st != 3:
                return 'NA'
            if not s['terms']:
                return 'DISABLED'
            s['done'] = True
        return self._obs()


def ground_truth(sim: SignupSim, alphabet):
    """Explicit-state BFS over the simulator's concrete states, then Mealy minimization -> exact reference model."""
    import json
    from collections import deque
    from aalpy.automata import MealyMachine, MealyState
    sim.pre()
    key = lambda s: json.dumps(s, sort_keys=True)
    init = dict(sim.s)
    states, q = {key(init): MealyState(f's{0}')}, deque([init])
    while q:
        cur = q.popleft()
        st = states[key(cur)]
        for a in alphabet:
            sim.s = dict(cur)
            out = sim.step(a)
            k = key(sim.s)
            if k not in states:
                states[k] = MealyState(f's{len(states)}')
                q.append(dict(sim.s))
            st.transitions[a] = states[k]
            st.output_fun[a] = out
    m = MealyMachine(states[key(init)], list(states.values()))
    concrete = len(m.states)
    m.minimize()
    return m, concrete
