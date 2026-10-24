"""Hidden-oracle harness for the jq benchmark: run jq's own ``tests/jq.test`` against any implementation.

The suite is fetched at a pinned version and stays on the dirty/evaluation side; it is never shown to the clean
implementer. Outputs are compared as JSON values (so ``1.0`` and ``1`` agree, as with ``jq --run-tests``).
``%%FAIL`` cases pass when the implementation refuses the program (non-zero exit); the expected error *wording*
is not compared, consistent with treating diagnostic text as expression.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from teardown.drivers.cli.invocation import Invocation
from teardown.drivers.cli.runner import Runner

SUITE_URL = "https://raw.githubusercontent.com/jqlang/jq/{tag}/tests/jq.test"


@dataclass
class Case:
    line: int
    program: str
    input: str | None
    expected: list[str]
    must_fail: bool = False


@dataclass
class Report:
    total: int = 0
    passed: int = 0
    failures: list[dict] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


def fetch(tag: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        with urllib.request.urlopen(SUITE_URL.format(tag=tag), timeout=30) as resp:  # noqa: S310 - fixed host
            dest.write_bytes(resp.read())
    return dest


def parse(text: str) -> list[Case]:
    cases, block, start = [], [], 0
    lines = text.splitlines()
    for i, raw in enumerate([*lines, ""], start=1):
        if raw.startswith("#"):
            continue
        if raw.strip() == "":
            if block:
                cases.append(_case(block, start))
                block = []
            continue
        if not block:
            start = i
        block.append(raw)
    return [c for c in cases if c is not None]


def _case(block: list[str], line: int) -> Case | None:
    if block[0].startswith("%%FAIL"):
        return Case(line, block[1], None, [], must_fail=True) if len(block) >= 2 else None
    if len(block) < 2:
        return None
    return Case(line, block[0], block[1], block[2:])


def _values(lines: list[str]) -> list[object] | None:
    try:
        return [json.loads(x) for x in lines if x.strip()]
    except json.JSONDecodeError:
        return None


def run(runner: Runner, command: str, cases: list[Case], timeout_s: float = 10.0) -> Report:
    report = Report()
    runner.reset()
    for case in cases:
        report.total += 1
        if case.must_fail:
            obs = runner.run(Invocation(argv=[command, "-n", case.program], stdin_mode="null", timeout_s=timeout_s))
            ok = obs["exit"] not in (0, None)
        else:
            stdin = (case.input + "\n").encode().decode("latin-1")  # runner carries bytes as latin-1
            obs = runner.run(Invocation(argv=[command, "-c", case.program], stdin=stdin, timeout_s=timeout_s))
            stdout = (obs["stdout"] or "").encode("latin-1").decode("utf-8", "replace")
            got, want = _values(stdout.splitlines()), _values(case.expected)
            ok = obs["exit"] == 0 and got is not None and want is not None and got == want
        if ok:
            report.passed += 1
        else:
            report.failures.append({"line": case.line, "program": case.program, "exit": obs["exit"]})
    return report
