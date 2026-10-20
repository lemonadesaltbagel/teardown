"""AALpy SUL over the web driver, with a prefix-trie cache and *lazy reset*.

Lazy reset: pre() does not touch the browser. step() answers from the trie while the query is still a
prefix of something already observed; on the first miss it does one real reset, replays the buffered
prefix (re-checking determinism) and continues live. Fully cached queries therefore cost zero resets,
which matters because AALpy's equivalence oracles bypass its own CacheSUL for step-wise testing.
"""
from __future__ import annotations

import time

from aalpy.base import SUL

from .abstraction import Abstraction
from .driver import WebDriver


class NonDeterminism(Exception):
    def __init__(self, prefix, cached, observed):
        super().__init__(f'non-determinism after {prefix}: cached={cached} observed={observed}')
        self.prefix, self.cached, self.observed = prefix, cached, observed


class WebSUL(SUL):
    def __init__(self, driver: WebDriver, alphabet: dict, abstraction: Abstraction, lazy: bool = True,
                 trace_log: list | None = None):
        super().__init__()
        self.d, self.alphabet, self.abs, self.lazy = driver, alphabet, abstraction, lazy
        self.trie: dict = {}
        self.cache_hit_steps = 0
        self.replay_steps = 0
        self.live_steps = 0
        self.logical_queries = 0
        self.trace_log = trace_log
        self._t0 = time.perf_counter()

    # -- AALpy interface -------------------------------------------------
    def pre(self):
        self.logical_queries += 1
        self._node = self.trie
        self._buffer: list = []
        self._live = False
        if not self.lazy:
            self.d.reset()
            self._live = True

    def post(self):
        if self.trace_log is not None:
            self.trace_log.append(tuple(self._buffer))

    def step(self, letter):
        if letter is None:
            return None
        if not self._live:
            hit = self._node.get(letter)
            if hit is not None:
                self.cache_hit_steps += 1
                self._buffer.append(letter)
                self._node = hit[1]
                return hit[0]
            self._go_live()
        out = self._real_step(letter)
        self.live_steps += 1
        self._record(letter, out)
        self._buffer.append(letter)
        return out

    # -- internals -------------------------------------------------------
    def _go_live(self):
        self.d.reset()
        node = self.trie
        for i, l in enumerate(self._buffer):
            out = self._real_step(l)
            self.replay_steps += 1
            cached, node = node[l]
            if out != cached:
                raise NonDeterminism(tuple(self._buffer[:i + 1]), cached, out)
        self._live = True

    def _real_step(self, letter):
        reason = self.d.act(self.alphabet[letter])
        if reason:
            return reason                      # control absent/disabled: no state change, skip snapshot
        return self.abs.symbol(self.d.snapshot())

    def _record(self, letter, out):
        hit = self._node.get(letter)
        if hit is None:
            hit = self._node[letter] = (out, {})
        elif hit[0] != out:
            raise NonDeterminism(tuple(self._buffer) + (letter,), hit[0], out)
        self._node = hit[1]

    def stats(self) -> dict:
        return dict(logical_queries=self.logical_queries, real_resets=self.d.m.resets,
                    live_steps=self.live_steps, replay_steps=self.replay_steps,
                    cache_hit_steps=self.cache_hit_steps, wall_s=round(time.perf_counter() - self._t0, 2),
                    driver=self.d.m.as_dict())
