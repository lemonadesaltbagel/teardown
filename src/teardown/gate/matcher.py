"""Verbatim-leak detection: longest common token run between a candidate string and the observed-string corpus.

Built on a suffix automaton over the corpus token stream (documents separated by unique sentinels), so a query costs
O(len(query)) regardless of corpus size.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Hyphenated words and option names (--only-delimited) are one token each: they are single interface names.
_TOKEN = re.compile(r"-{0,2}\w+(?:-\w+)*|[^\w\s]", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return [t.casefold() for t in _TOKEN.findall(text)]


@dataclass(frozen=True)
class Match:
    length: int
    query_tokens: tuple[str, ...]
    corpus_text: str


class CorpusMatcher:
    def __init__(self, corpus: list[str]):
        self._docs = list(corpus)
        self._next: list[dict[object, int]] = [{}]
        self._link = [-1]
        self._len = [0]
        self._end_doc = [-1]
        last = 0
        for doc_index, doc in enumerate(self._docs):
            for token in tokenize(doc):
                last = self._extend(last, token, doc_index)
            last = self._extend(last, ("sentinel", doc_index), doc_index)

    def _extend(self, last: int, token: object, doc_index: int) -> int:
        cur = len(self._len)
        self._next.append({})
        self._len.append(self._len[last] + 1)
        self._link.append(-1)
        self._end_doc.append(doc_index)
        p = last
        while p != -1 and token not in self._next[p]:
            self._next[p][token] = cur
            p = self._link[p]
        if p == -1:
            self._link[cur] = 0
        else:
            q = self._next[p][token]
            if self._len[p] + 1 == self._len[q]:
                self._link[cur] = q
            else:
                clone = len(self._len)
                self._next.append(dict(self._next[q]))
                self._len.append(self._len[p] + 1)
                self._link.append(self._link[q])
                self._end_doc.append(self._end_doc[q])
                while p != -1 and self._next[p].get(token) == q:
                    self._next[p][token] = clone
                    p = self._link[p]
                self._link[q] = clone
                self._link[cur] = clone
        return cur

    def longest(self, text: str) -> Match | None:
        tokens = tokenize(text)
        state, length, best, best_end, best_state = 0, 0, 0, -1, 0
        for i, token in enumerate(tokens):
            while state and token not in self._next[state]:
                state = self._link[state]
                length = self._len[state]
            if token in self._next[state]:
                state = self._next[state][token]
                length += 1
            else:
                state, length = 0, 0
            if length > best:
                best, best_end, best_state = length, i, state
        if best == 0:
            return None
        doc = self._end_doc[best_state]
        return Match(best, tuple(tokens[best_end - best + 1 : best_end + 1]), self._docs[doc] if doc >= 0 else "")
