"""verify_against_original: run the released conformance suite on the original and on a clone, return symbols only.

What crosses back to the clean side is an :class:`AbstractVerdict`: test inputs (already public in the spec), the
expected *symbol from the released vocabulary*, and the clone's own observed symbol. If the original produces
something outside the released vocabulary (the model was incomplete), that output is withheld, the test is reported
inconclusive, and an unknown is recorded on the dirty side for the observer to investigate.

Noise is calibrated Diffy-style: each test runs ``repeats`` times on the original; positions where those runs
disagree are reported inconclusive rather than failed.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from teardown.audit.log import AuditLog
from teardown.core.model import ContentAddressed
from teardown.drivers.session import ObservationSession
from teardown.engine.claims import ClaimLedger
from teardown.gate.gate import load_release
from teardown.spec.efsm import EFSM


class BudgetExceeded(PermissionError):
    pass


class TestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test: int
    kind: Literal["transition", "claim"]
    claim_id: str | None = None
    status: Literal["pass", "fail", "inconclusive"]
    step: int | None = None
    inputs: list[str]
    expected: str | None = None
    observed: str | None = None
    note: str = ""


class AbstractVerdict(ContentAddressed):
    PREFIX: ClassVar[str] = "vrd"

    release: str
    clone: str
    passed: int
    failed: int
    inconclusive: int
    results: list[TestResult] = Field(default_factory=list)


class Verifier:
    def __init__(
        self,
        *,
        releases_dir: Path,
        open_original: Callable[[], ObservationSession],
        open_clone: Callable[[str], ObservationSession],
        ledger: ClaimLedger,
        audit: AuditLog,
        max_calls_per_release: int = 50,
        max_tests: int = 1000,
    ):
        self.releases_dir = releases_dir
        self.open_original = open_original
        self.open_clone = open_clone
        self.ledger = ledger
        self.audit = audit
        self.max_calls = max_calls_per_release
        self.max_tests = max_tests
        self._calls: dict[str, int] = {}

    def verify(self, clone_target: str, release_id: str | None = None, repeats: int = 2) -> AbstractVerdict:
        rel = load_release(self.releases_dir, release_id)
        used = self._calls.get(rel.id, 0)
        if used >= self.max_calls:
            raise BudgetExceeded(f"verification budget for this release is spent ({self.max_calls} calls)")
        self._calls[rel.id] = used + 1

        model = EFSM.model_validate(rel.spec["model"])
        vocabulary = {o.symbol for o in model.outputs}
        tests: list[tuple[str, list[str], list[str | None], str | None]] = []
        for inputs in _dedupe(model.transition_cover()):
            tests.append(("transition", inputs, list(model.run(inputs)), None))
        for claim in rel.spec["claims"]:
            if claim["status"] == "corroborated" and claim["strictness"] == "must":
                tests.append(("claim", claim["check"]["inputs"], claim["check"]["expect"], claim["id"]))
        tests = tests[: self.max_tests]

        original = self.open_original()
        clone = self.open_clone(clone_target)
        results: list[TestResult] = []
        try:
            for i, (kind, inputs, expect, claim_id) in enumerate(tests):
                runs = [original.run(inputs, use_cache=False)[0] for _ in range(max(1, repeats))]
                observed = clone.run(inputs, use_cache=False)[0]
                results.append(self._judge(i, kind, claim_id, inputs, expect, runs, observed, vocabulary, rel.codename))
        finally:
            original.close()
            clone.close()

        verdict = AbstractVerdict(
            release=rel.id,
            clone=clone_target,
            passed=sum(r.status == "pass" for r in results),
            failed=sum(r.status == "fail" for r in results),
            inconclusive=sum(r.status == "inconclusive" for r in results),
            results=results,
        )
        self.audit.append(
            "verdict",
            {"release": rel.id, "verdict": verdict.id},
            {"clone": clone_target, "passed": verdict.passed, "failed": verdict.failed,
             "inconclusive": verdict.inconclusive, "repeats": repeats},
        )
        return verdict

    def _judge(self, i, kind, claim_id, inputs, expect, runs, observed, vocabulary, codename) -> TestResult:
        base = {"test": i, "kind": kind, "claim_id": claim_id, "inputs": inputs}
        for step, want in enumerate(expect):
            if want is None and kind == "claim":
                continue  # the claim says nothing about this step
            originals = {run[step] for run in runs}
            if len(originals) > 1:
                return TestResult(**base, status="inconclusive", step=step, note="original is nondeterministic here")
            original = originals.pop()
            if want is not None and original != want:
                self.ledger.record_unknown(
                    codename,
                    f"original no longer matches the released spec after {inputs[: step + 1]}",
                    ["re-learn this feature", "re-probe the affected claims"],
                )
                return TestResult(**base, status="inconclusive", step=step, note="original diverged from the spec")
            if original not in vocabulary:
                self.ledger.record_unknown(
                    codename,
                    f"original produced an output outside the released vocabulary after {inputs[: step + 1]}",
                    ["raise the equivalence-oracle budget", "add round-trip probes around this prefix"],
                )
                return TestResult(**base, status="inconclusive", step=step, note="released model is incomplete here")
            if observed[step] != original:
                return TestResult(**base, status="fail", step=step, expected=original, observed=observed[step])
        return TestResult(**base, status="pass")


def _dedupe(sequences: list[list[str]]) -> list[list[str]]:
    seen, out = set(), []
    for seq in sequences:
        key = tuple(seq)
        if key not in seen:
            seen.add(key)
            out.append(seq)
    return out
