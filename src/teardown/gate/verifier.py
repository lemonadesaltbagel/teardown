"""verify_against_original: run the released conformance suite on the original and on a clone, return symbols only.

The suite is (a) one test per transition of the released state model, (b) every row of the released probe table,
and (c) every case of every corroborated ``must`` claim.

What crosses back to the clean side is an :class:`AbstractVerdict`: test inputs (already public in the spec), the
expected *symbol from the released spec*, and the clone's own observed symbol. If the original no longer behaves as
released (drift) or produces something outside the released vocabulary (an incomplete model), that output is
withheld, the test is reported inconclusive, and an unknown is recorded on the dirty side for the observer.

Noise is calibrated Diffy-style: each test runs ``repeats`` times on the original; positions where those runs
disagree are reported inconclusive rather than failed.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from teardown.audit.log import AuditLog
from teardown.core.model import ContentAddressed
from teardown.drivers.base import DeviceLost
from teardown.drivers.session import ObservationSession
from teardown.engine.claims import ClaimLedger
from teardown.engine.mapper import symbol_matches
from teardown.gate.gate import SpecRelease, load_release
from teardown.spec.efsm import EFSM


class BudgetExceeded(PermissionError):
    pass


class TestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test: int
    kind: Literal["transition", "probe", "claim", "rule"]
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


class _Test(BaseModel):
    kind: Literal["transition", "probe", "claim", "rule"]
    inputs: list[str]
    expect: list[str | None]
    match: Literal["exact", "subset"] = "exact"
    claim_id: str | None = None
    relation: Literal["same", "differs"] | None = None
    other: list[str] | None = None
    keys: list[str] | None = None


def conformance_suite(rel: SpecRelease, max_tests: int = 5000) -> list[_Test]:
    spec, tests, seen = rel.spec, [], set()
    if spec.get("model"):
        model = EFSM.model_validate(spec["model"])
        for inputs in model.transition_cover():
            if tuple(inputs) not in seen:
                seen.add(tuple(inputs))
                tests.append(_Test(kind="transition", inputs=inputs, expect=model.run(inputs)))
    for row in spec.get("probe_table", []):
        inputs = [*row.get("prefix", []), row["action"]]
        seen.add(tuple(inputs))
        tests.append(_Test(kind="probe", inputs=inputs, expect=[None] * (len(inputs) - 1) + [row["expect"]],
                           match=row.get("match", "exact")))
    for claim in spec.get("claims", []):
        if claim["status"] == "corroborated" and claim["strictness"] == "must":
            for check in [claim["check"], *claim.get("cases", [])]:
                if tuple(check["inputs"]) in seen:
                    continue  # already tested exactly by a probe-table row
                tests.append(_Test(kind="claim", inputs=check["inputs"], expect=check["expect"],
                                   match=check.get("match", "exact"), claim_id=claim["id"]))
    for rule in spec.get("rules", []):
        if rule["status"] != "corroborated":
            continue
        for check in rule["checks"]:
            a = check.get("a_inputs") or [check["a"]]
            if check["kind"] == "outcome":
                tests.append(_Test(kind="rule", inputs=a, expect=[None] * (len(a) - 1) + [check["expect"]],
                                   match="subset", claim_id=rule["id"]))
            else:
                b = check.get("b_inputs") or [check["b"]]
                tests.append(_Test(kind="rule", inputs=a, expect=[None] * len(a), claim_id=rule["id"],
                                   relation=check["kind"], other=b, keys=check.get("keys")))
    return tests[:max_tests]


def content_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _test_key(test: _Test) -> str:
    return content_hash(json.dumps({"inputs": test.inputs, "relation": test.relation, "other": test.other,
                                    "keys": test.keys, "kind": test.kind}, sort_keys=True))


class Verifier:
    def __init__(
        self,
        *,
        releases_dir: Path,
        open_original: Callable[[SpecRelease], ObservationSession],
        open_clone: Callable[[str, SpecRelease, dict[str, Any] | None], ObservationSession],
        ledger: ClaimLedger,
        audit: AuditLog,
        max_calls_per_release: int = 50,
        max_tests: int = 5000,
        rename: Callable[[str], str] = lambda symbol: symbol,
    ):
        self.releases_dir = releases_dir
        self.open_original = open_original
        self.open_clone = open_clone
        self.ledger = ledger
        self.audit = audit
        self.max_calls = max_calls_per_release
        self.max_tests = max_tests
        self.rename = rename  # the release's codename substitution, applied to the original's live output
        self._budget_file = releases_dir / "verify-budget.json"

    def verify(self, clone_target: str, release_id: str | None = None, repeats: int = 2,
               adapter: dict[str, Any] | None = None, only: str | None = None) -> AbstractVerdict:
        """``adapter`` (clean-side data): {"actions": {name: action}, "rules": [mapper rules]} mapping the clone's
        own UI onto the released action names and output vocabulary. Needed for UI targets, optional for CLIs.

        Speed on large targets: the original's runs are cached per release, and each call re-checks a rotating
        sample of them (any difference drops the cache); ``only="failed"`` runs just the tests this clone did not
        pass last time (the verdict then covers those tests only)."""
        rel = load_release(self.releases_dir, release_id)
        calls = json.loads(self._budget_file.read_text()) if self._budget_file.exists() else {}
        if calls.get(rel.id, 0) >= self.max_calls:
            raise BudgetExceeded(f"verification budget for this release is spent ({self.max_calls} calls)")
        calls[rel.id] = calls.get(rel.id, 0) + 1
        self._budget_file.write_text(json.dumps(calls))
        try:
            return self._verify(rel, calls[rel.id], clone_target, repeats, adapter, only)
        except Exception as exc:
            if not isinstance(exc, ValueError):  # the gate failed (not the build): the call is not spent
                calls = json.loads(self._budget_file.read_text())
                calls[rel.id] = max(0, calls.get(rel.id, 1) - 1)
                self._budget_file.write_text(json.dumps(calls))
            raise

    def _verify(self, rel: SpecRelease, call: int, clone_target: str, repeats: int,
                adapter: dict[str, Any] | None, only: str | None) -> AbstractVerdict:
        vocabulary = {o["symbol"] for o in (rel.spec.get("model") or {}).get("outputs", [])}
        vocabulary |= {row["expect"] for row in rel.spec.get("probe_table", []) if row.get("match", "exact") == "exact"}
        for claim in rel.spec.get("claims", []):
            for check in [claim["check"], *claim.get("cases", [])]:
                if check.get("match", "exact") == "exact":
                    vocabulary |= {e for e in check["expect"] if e is not None}
        tests = conformance_suite(rel, self.max_tests)
        last_file = self.releases_dir / "verify-last" / f"{rel.id}-{content_hash(clone_target)}.json"
        last = json.loads(last_file.read_text()) if last_file.exists() else {}
        selected = [i for i in range(len(tests))
                    if only != "failed" or not last or last.get(str(i)) != "pass"]
        cache_file = self.releases_dir / "verify-cache" / f"{rel.id}.json"
        cache: dict[str, Any] = json.loads(cache_file.read_text()) if cache_file.exists() else {}
        original = self.open_original(rel)
        clone = self.open_clone(clone_target, rel, adapter)
        results: list[TestResult] = []

        def original_runs(test: _Test) -> Any:
            if test.relation:
                return all(self._relation_holds(test, original, self.rename)[0] for _ in range(max(1, repeats)))
            return [[self.rename(o) for o in original.run(test.inputs, use_cache=False)[0]]
                    for _ in range(max(1, repeats))]

        try:
            if cache:  # the original may have changed since: re-check a rotating sample before trusting the cache
                keyed = [i for i in selected if _test_key(tests[i]) in cache]
                start = call * 3
                sample = [keyed[(start + k) % len(keyed)] for k in range(min(len(keyed), max(3, len(keyed) // 20)))]
                if any(original_runs(tests[i]) != cache[_test_key(tests[i])] for i in dict.fromkeys(sample)):
                    cache = {}
            def once_more_if_the_device_died(fn):
                try:
                    return fn()
                except DeviceLost:  # the driver brings the device back at the next reset: run the episode again
                    return fn()

            for i in selected:
                test, key = tests[i], _test_key(tests[i])
                if key not in cache:
                    cache[key] = once_more_if_the_device_died(lambda test=test: original_runs(test))
                if test.relation:
                    results.append(once_more_if_the_device_died(
                        lambda i=i, test=test, key=key: self._judge_relation(i, test, cache[key], clone)))
                    continue
                observed = once_more_if_the_device_died(lambda test=test: clone.run(test.inputs, use_cache=False)[0])
                results.append(self._judge(i, test, cache[key], observed, vocabulary, rel.codename))
        finally:
            original.close()
            clone.close()
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(cache))
        last.update({str(r.test): r.status for r in results})
        last_file.parent.mkdir(parents=True, exist_ok=True)
        last_file.write_text(json.dumps(last))

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

    @staticmethod
    def _relation_holds(test: _Test, session, rename) -> tuple[bool, str, str]:
        from teardown.engine.rules import projection

        a = rename(session.run(test.inputs, use_cache=False)[0][-1])
        b = rename(session.run(test.other, use_cache=False)[0][-1])
        equal = projection(a, test.keys) == projection(b, test.keys)
        return (equal if test.relation == "same" else not equal), a, b

    def _judge_relation(self, i: int, test: _Test, original_holds: bool, clone) -> TestResult:
        base = {"test": i, "kind": test.kind, "claim_id": test.claim_id, "inputs": [*test.inputs, *test.other]}
        if not original_holds:
            return TestResult(**base, status="inconclusive", note="relation no longer holds on the original")
        holds, a, b = self._relation_holds(test, clone, lambda s: s)
        if holds:
            return TestResult(**base, status="pass")
        return TestResult(**base, status="fail", expected=f"{test.relation} on {test.keys or 'all keys'}",
                          observed=json.dumps({"a": a, "b": b}, ensure_ascii=False), note="relation violated")

    def _judge(self, i: int, test: _Test, runs: list[list[str]], observed: list[str], vocabulary: set[str],
               codename: str) -> TestResult:
        base: dict[str, Any] = {"test": i, "kind": test.kind, "claim_id": test.claim_id, "inputs": test.inputs}
        for step, want in enumerate(test.expect):
            if want is None and test.kind in ("claim", "probe"):
                continue  # the test says nothing about this step
            originals = {run[step] for run in runs}
            if len(originals) > 1:
                return TestResult(**base, status="inconclusive", step=step, note="original is nondeterministic here")
            original = originals.pop()
            if want is not None and not symbol_matches(original, want, test.match):
                self.ledger.record_unknown(
                    codename, f"original no longer matches the released spec after {test.inputs[: step + 1]}",
                    ["re-probe or re-learn this feature", "re-probe the affected claims"])
                return TestResult(**base, status="inconclusive", step=step, note="original diverged from the spec")
            if test.match == "exact" and original not in vocabulary and not any(
                    symbol_matches(original, v, "exact") for v in vocabulary if v[:1] == original[:1]):
                self.ledger.record_unknown(
                    codename,
                    f"original produced an output outside the released vocabulary after {test.inputs[: step + 1]}",
                    ["raise the equivalence-oracle budget", "add round-trip probes around this prefix"])
                return TestResult(**base, status="inconclusive", step=step, note="released model is incomplete here")
            expected = want if test.match == "subset" else original
            if not symbol_matches(observed[step], expected, test.match):
                return TestResult(**base, status="fail", step=step, expected=expected, observed=observed[step])
        return TestResult(**base, status="pass")
