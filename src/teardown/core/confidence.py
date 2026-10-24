"""Confidence for claims: Beta-Binomial posterior over the violation rate, plus the rule of three.

Probes are not independent, so callers must cap the reported confidence by coverage; these numbers say how often a
claim survived the probes that were run, not that the probes were representative.
"""

from __future__ import annotations

import math


def violation_upper_bound(confirming: int, contradicting: int, level: float = 0.95) -> float:
    """Upper bound on the violation rate. With no contradictions this is the exact binomial bound (≈ 3/n at 95%)."""
    n = confirming + contradicting
    if n == 0:
        return 1.0
    if contradicting == 0:
        return 1.0 - (1.0 - level) ** (1.0 / n)
    return _beta_quantile(level, 1 + contradicting, 1 + confirming)


def _beta_quantile(q: float, a: float, b: float) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if _beta_cdf(mid, a, b) < q:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _beta_cdf(x: float, a: float, b: float, steps: int = 2000) -> float:
    """Regularized incomplete beta via midpoint integration; adequate for ledger reporting."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    log_norm = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    h = x / steps
    total = 0.0
    for i in range(steps):
        t = (i + 0.5) * h
        total += math.exp(log_norm + (a - 1) * math.log(t) + (b - 1) * math.log1p(-t))
    return min(1.0, total * h)
