"""Hidden-oracle harness for JSONL CLI suites (the novel-tool benchmark).

Each case: ``{"id", "argv" (after the command), "stdin", "files", "expect_exit", "expect_stdout",
"expect_stderr_nonempty", "expect_files"?}``. A case passes when exit code, stdout bytes, presence of a diagnostic
and every expected file's content match. Diagnostic wording is not compared.

``rename`` maps the implementation's command name back to the suite's (a spec-arm clone is installed under the
codename, so its usage/version output names the codename).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from teardown.drivers.cli.invocation import Invocation
from teardown.drivers.cli.runner import Runner


def _b(text: str | None) -> str | None:
    return None if text is None else text.encode().decode("latin-1")  # runner carries bytes as latin-1


def _t(latin1: str | None) -> str:
    return (latin1 or "").encode("latin-1").decode("utf-8", "replace")


@dataclass
class Report:
    total: int = 0
    passed: int = 0
    failures: list[dict] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run(runner: Runner, command: str, cases: list[dict], *, rename: tuple[str, str] | None = None,
        timeout_s: float = 10.0) -> Report:
    report = Report()
    for case in cases:
        report.total += 1
        runner.reset({k: _b(v) for k, v in (case.get("files") or {}).items()})
        stdin = case.get("stdin")
        obs = runner.run(Invocation(argv=[command, *case["argv"]], stdin=_b(stdin),
                                    stdin_mode="pipe" if stdin is not None else "null", timeout_s=timeout_s))
        stdout = _t(obs["stdout"])
        if rename:
            stdout = stdout.replace(rename[0], rename[1])
        final = dict(case.get("files") or {})  # seeded files persist unless changed or deleted
        for c in obs["fs"]:
            if c["op"] == "delete":
                final.pop(c["path"], None)
            else:
                final[c["path"]] = _t(c.get("content"))
        created = final
        problems = []
        if obs["exit"] != case["expect_exit"]:
            problems.append(f"exit {obs['exit']} != {case['expect_exit']}")
        if stdout != case["expect_stdout"]:
            problems.append("stdout")
        if bool((obs["stderr"] or "").strip()) != case["expect_stderr_nonempty"]:
            problems.append("diagnostic presence")
        for path, content in (case.get("expect_files") or {}).items():
            if created.get(path) != content:
                problems.append(f"file {path}")
        if problems:
            report.failures.append({"id": case["id"], "problems": problems})
        else:
            report.passed += 1
    return report
