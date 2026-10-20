from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from teardown.drivers.cli.discover import parse_help
from teardown.drivers.cli.invocation import Invocation
from teardown.drivers.cli.plan import ProbeHints, accepted_classes, pairwise, plan_pairwise, plan_sweep
from teardown.drivers.cli.runner import ContainerRunner, LocalRunner
from teardown.engine.abstractions import cli_behavior, errno_class
from teardown.project import Project


def _docker_ok() -> bool:
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


needs_docker = pytest.mark.skipif(not _docker_ok(), reason="docker is not available")

GNU_HELP = """Usage: cut OPTION... [FILE]...
  -b, --bytes=LIST        select only these bytes
  -d, --delimiter=DELIM   use DELIM instead of TAB for field delimiter
  -s, --only-delimited    do not print lines not containing delimiters
      --output-delimiter=STRING  use STRING as the output delimiter
      --help        display this help and exit
"""


def test_help_parsing_keeps_structure_not_prose():
    model = parse_help(GNU_HELP, "cut")
    opts = model["options"]
    assert opts["-b"]["names"] == ["-b", "--bytes"] and opts["-b"]["type"] == "list"
    assert opts["-s"]["arity"] == "none" and opts["--output-delimiter"]["arity"] == "required"
    assert "select only" not in json.dumps(model)


def test_behavior_abstraction_drops_wording_keeps_behavior():
    obs = {
        "exit": 1,
        "signal": None,
        "timed_out": False,
        "stdout": "",
        "stdout_truncated": False,
        "stderr": "cut: in.txt: No such file or directory\n",
        "fs": [],
    }
    sym = cli_behavior(obs, {})
    assert sym == {"exit": 1, "stdout": "", "diagnostic": True, "errno": "ENOENT"}
    assert errno_class("tool: whatever: Permission denied") == "EACCES"
    utf8 = cli_behavior({**obs, "exit": 0, "stderr": "", "stdout": "é\n".encode().decode("latin-1")}, {})
    assert utf8["stdout"] == "é\n"


def test_pairwise_covers_every_pair():
    grid = {"a": [0, 1, 2], "b": [0, 1], "c": [0, 1, 2]}
    rows = pairwise(grid)
    for x, y in [("a", "b"), ("a", "c"), ("b", "c")]:
        assert {(r[x], r[y]) for r in rows} == {(i, j) for i in grid[x] for j in grid[y]}


def test_planner_is_single_fault_then_pairwise_over_accepted_only():
    model = parse_help(GNU_HELP, "cut")
    hints = ProbeHints(cmd="cut", base=["-f", "2"], selector_options=["-b", "-f"])
    sweep = plan_sweep(model, hints)
    assert all(p.invocation.argv[0] == "cut" for p in sweep) and len({p.id for p in sweep}) == len(sweep)
    assert not any("--help" in p.invocation.argv for p in sweep)
    fake = [{"exit": 0 if "val:list.one" in p.tags or "val:string.colon" in p.tags else 1} for p in sweep]
    accepted = accepted_classes(sweep, fake)
    assert accepted == {"-b": ["list.one"], "-d": ["string.colon"], "--output-delimiter": ["string.colon"]}
    rows = plan_pairwise(model, hints, accepted)
    for p in rows:
        for t in p.tags:
            if t.startswith("val:"):
                assert t.split("=", 1)[1] in ("list.one", "string.colon")


def test_local_runner_episode_and_fs_effects(tmp_path):
    runner = LocalRunner()
    try:
        runner.reset({"in.txt": "b\na\n"})
        obs = runner.run(Invocation(argv=["sort", "-o", "out.txt", "in.txt"]))
        assert obs["exit"] == 0 and obs["fs"][0]["path"] == "out.txt" and obs["fs"][0]["content"] == "a\nb\n"
        obs = runner.run(Invocation(argv=["cat", "missing.txt"]))
        assert obs["exit"] != 0 and cli_behavior(obs, {})["errno"] == "ENOENT"
        runner.reset()
        assert runner.run(Invocation(argv=["ls"]))["stdout"] == ""
    finally:
        runner.close()


def test_cli_round_trip_locally_on_system_cut(tmp_path):
    """Original and 'clone' are the same system cut, so verification must pass with nothing inconclusive.

    Portable across GNU and BSD cut; BSD cut has no --help, so discovery finds little and the table is small."""
    project = Project(tmp_path / "p")
    project.open_target("cli:local", purpose="research")
    hints = {
        "cmd": "cut",
        "base": ["-f", "2"],
        "selector_options": ["-b", "-c", "-f"],
        "sweep_inputs": ["tsv"],
        "inputs": ["tsv", "empty", "no_eol"],
        "pair_inputs": ["tsv"],
    }
    summary = project.probe_cli("cut", hints, workers=2, env_sample=20)
    assert summary["claims"] > 0 and summary["rows"] > 10
    statuses = {c.status for c in project.ledger.all().values()}
    assert statuses == {"corroborated"}
    faults = [c.identity.statement for c in project.ledger.all().values() if "file fault" in c.identity.statement]
    assert any("unreadable" in f and "EACCES" in f for f in faults)  # permission faults are probed and mined
    rel = project.release_spec(project.compile_spec("cut").id)
    assert rel.spec["actions"] and rel.spec["probe_table"] and rel.spec["interface"]["command"] == "cut"
    verdict = project.verifier().verify("cli:local", repeats=1)
    assert verdict.failed == 0 and verdict.inconclusive == 0 and verdict.passed > 10


@needs_docker
def test_container_isolation():
    runner = ContainerRunner("debian:stable-slim")
    try:
        runner.reset()
        probe = "id -u; touch /etc/x 2>/dev/null || echo ro; (exec 3<>/dev/tcp/1.1.1.1/53) 2>/dev/null || echo nonet"
        obs = runner.run(Invocation(argv=["bash", "-c", probe]))
        assert obs["stdout"].split() == ["65534", "ro", "nonet"]
        obs = runner.run(Invocation(argv=["sh", "-c", "sleep 30"], timeout_s=1))
        assert obs["timed_out"]
        assert runner.run(Invocation(argv=["seq", "3"]))["stdout"] == "1\n2\n3\n"  # session survives a timeout
    finally:
        runner.close()


def _permission_faults(runner):
    runner.reset({"in.txt": "b\na\n", "out/keep": ""}, {"in.txt": "000", "out": "555"})
    obs = runner.run(Invocation(argv=["cat", "in.txt"]))
    assert obs["exit"] != 0 and cli_behavior(obs, {})["errno"] == "EACCES"
    assert obs["fs"] == []  # the seeded modes are the starting state, not an effect of the program
    obs = runner.run(Invocation(argv=["sh", "-c", "echo x > out/new.txt"]))
    assert obs["exit"] != 0 and cli_behavior(obs, {})["errno"] == "EACCES" and obs["fs"] == []
    assert runner.run(Invocation(argv=["cat", "in.txt"]))["exit"] != 0  # modes survive the snapshot
    obs = runner.run(Invocation(argv=["chmod", "644", "in.txt"]))  # the program's own chmod is an effect
    assert [(e["op"], e["path"], e["mode"]) for e in obs["fs"]] == [("modify", "in.txt", "0o644")]
    runner.reset()  # a locked tree does not block the next reset
    assert runner.run(Invocation(argv=["ls"]))["stdout"] == ""


def test_seeded_file_modes_local():
    runner = LocalRunner()
    try:
        _permission_faults(runner)
        with pytest.raises(ValueError):
            runner.reset({"a": ""}, {"b": "000"})
    finally:
        runner.close()


@needs_docker
def test_seeded_file_modes_in_container():
    runner = ContainerRunner("debian:stable-slim")
    try:
        _permission_faults(runner)
    finally:
        runner.close()


@needs_docker
def test_differential_gnu_vs_busybox(tmp_path):
    project = Project(tmp_path / "p")
    project.open_target("cli:docker:debian:stable-slim", purpose="interop")
    hints = {
        "cmd": "cut",
        "base": ["-f", "2"],
        "selector_options": ["-b", "-c", "-f"],
        "sweep_inputs": ["tsv"],
        "inputs": ["tsv", "empty"],
        "pair_inputs": ["tsv"],
    }
    project.probe_cli("cut", hints, env_sample=20)
    project.release_spec(project.compile_spec("cut").id)
    verifier = project.verifier()
    same = verifier.verify("cli:docker:debian:stable-slim", repeats=1)
    other = verifier.verify("cli:docker:busybox:musl", repeats=1)
    assert same.failed == 0 and other.failed > 0


SORT_RULES = [
    {
        "statement": "Input order does not affect the output.",
        "origin": "documented",
        "checks": [
            {
                "kind": "same",
                "a": {"argv": ["sort"], "stdin": "b\na\nc\n"},
                "b": {"argv": ["sort"], "stdin": "c\nb\na\n"},
            }
        ],
    },
    {
        "statement": "-r reverses the order.",
        "checks": [
            {
                "kind": "differs",
                "a": {"argv": ["sort"], "stdin": "b\na\n"},
                "b": {"argv": ["sort", "-r"], "stdin": "b\na\n"},
                "keys": ["stdout"],
            }
        ],
    },
    {
        "statement": "A missing input file is refused with ENOENT.",
        "kind": "refusal",
        "checks": [
            {
                "kind": "outcome",
                "a": {"argv": ["sort", "missing.txt"]},
                "expect": {"diagnostic": True, "errno": "ENOENT"},
            }
        ],
    },
    {
        "statement": "Sorting is case-insensitive.",
        "origin": "documented",
        "checks": [  # false for sort in the C locale
            {
                "kind": "same",
                "a": {"argv": ["sort"], "stdin": "a\nB\n", "env": {"LC_ALL": "C"}},
                "b": {"argv": ["sort"], "stdin": "B\na\n", "env": {"LC_ALL": "C"}},
                "keys": [],
            },
            {
                "kind": "outcome",
                "a": {"argv": ["sort"], "stdin": "a\nB\n", "env": {"LC_ALL": "C"}},
                "expect": {"stdout": "a\nB\n"},
            },
        ],
    },
]


def test_rules_are_checked_released_and_verified_as_relations(tmp_path):
    project = Project(tmp_path / "p")
    project.open_target("cli:local", purpose="research")
    result = project.check_rules("sort", SORT_RULES, workers=1)
    status = {r["statement"]: r["status"] for r in result["rules"]}
    assert status["Input order does not affect the output."] == "corroborated"
    assert status["-r reverses the order."] == "corroborated"
    assert status["A missing input file is refused with ENOENT."] == "corroborated"
    assert status["Sorting is case-insensitive."] == "contested"  # the keys=[] check holds trivially
    conflicts = [u.identity.question for u in project.ledger.unknowns().values()]
    assert any("documentation/behavior conflict" in q for q in conflicts)
    rel = project.release_spec(project.compile_spec("sort").id)
    assert len(rel.spec["rules"]) == 4 and rel.spec["actions"]
    verdict = project.verifier().verify("cli:local", repeats=1)
    assert verdict.failed == 0 and verdict.passed == 3  # one test per check of the 3 corroborated rules


def test_input_mutations_and_coverage(tmp_path):
    from teardown.drivers.cli.plan import mutations

    muts = mutations("a\nb\nc\n", {"hash": "# x"})
    assert muts["crlf"] == "a\r\nb\r\nc\r\n" and muts["hash@middle"] == "a\n# x\nb\nc\n"
    assert muts["no_final_newline"] == "a\nb\nc"
    project = Project(tmp_path / "p")
    project.open_target("cli:local", purpose="research")
    project.probe_cli(
        "sort",
        {
            "cmd": "sort",
            "base": [],
            "default_input": "dups",
            "sweep_inputs": ["dups"],
            "inputs": ["dups"],
            "pair_inputs": [],
            "mutation_lines": {"hash": "# x"},
            "stdio_modes": False,
        },
        workers=2,
        env_sample=5,
        pairwise=False,
    )
    report = project.coverage("sort", {"reverse flag": ["-r"], "made-up feature": ["--frobnicate"]})
    assert report["counts"]["reverse flag"] > 0 and "made-up feature" in report["uncovered"]
    assert any("made-up feature" in u.identity.question for u in project.ledger.unknowns().values())


def test_stack_traces_are_redacted_at_capture():
    from teardown.drivers.cli.runner import redact_traces

    py = (
        b'tool: bad input\nTraceback (most recent call last):\n  File "/opt/tool/main.py", line 12, in <module>\n'
        b"    secret_line()\nValueError: x\n"
    )
    out = redact_traces(py)
    assert out.startswith(b"tool: bad input\n") and b"main.py" not in out and b"secret_line" not in out
    assert b"redacted" in out
    assert redact_traces(b"plain diagnostic\n") == b"plain diagnostic\n"
    node = b"Error: boom\n    at run (/srv/app/index.js:3:9)\n"
    assert b"index.js" not in redact_traces(node)


def test_crash_trace_never_reaches_evidence(tmp_path):
    runner = LocalRunner()
    try:
        runner.reset()
        obs = runner.run(
            Invocation(argv=["python3", "-c", "import os\ndef f():\n    raise RuntimeError('hidden')\nf()"])
        )
        assert obs["exit"] == 1 and "hidden" not in obs["stderr"] and "redacted" in obs["stderr"]
    finally:
        runner.close()


def test_help_output_can_be_approved_as_a_functional_quote(tmp_path):
    import base64

    project = Project(tmp_path / "p")
    project.open_target("cli:local", purpose="research")
    usage = "Usage: frobnicate the quantum flux capacitor with extreme prejudice and care"
    encoded = base64.b64encode(usage.encode()).decode()  # the tool's output must not be our own argv text
    program = f"import base64; print(base64.b64decode({encoded!r}).decode())"
    project.check_rules(
        "tool",
        [
            {
                "statement": "Help is printed.",
                "checks": [
                    {"kind": "outcome", "a": {"argv": ["python3", "-c", program, "--help"]}, "expect": {"exit": 0}}
                ],
            }
        ],
    )
    _, report = project.review_spec(project.compile_spec("tool").id)
    assert any(f.kind == "verbatim" for f in report.findings)
    assert project.approve_observed_output("tool", approved_by="reviewer") == [usage + "\n"]
    _, report = project.review_spec(project.compile_spec("tool").id)
    assert not report.findings


def test_strict_mode_blocks_release_until_coverage_is_measured_or_gaps_acknowledged(tmp_path):
    from teardown.project import CoverageGateBlocked

    project = Project(tmp_path / "p")
    project.open_target("cli:local", purpose="substitute", strict=True)
    project.probe_cli(
        "sort",
        {
            "cmd": "sort",
            "base": [],
            "default_input": "dups",
            "sweep_inputs": ["dups"],
            "inputs": ["dups"],
            "pair_inputs": [],
            "stdio_modes": False,
        },
        workers=2,
        env_sample=5,
        pairwise=False,
    )
    draft = project.compile_spec("sort")
    with pytest.raises(CoverageGateBlocked):
        project.release_spec(draft.id)
    project.coverage("sort", {"made-up feature": ["--frobnicate"]})
    with pytest.raises(CoverageGateBlocked) as blocked:
        project.release_spec(draft.id)
    assert "made-up feature" in blocked.value.gaps
    project.release_spec(draft.id, approved_by="reviewer")  # a human acknowledges the gaps
    kinds = [e["statement"]["predicateType"].split("/")[-2] for e in project.audit.entries()]
    assert "coverage-gaps-approved" in kinds and kinds[-1] == "spec-release"


def test_falsified_rules_come_with_rewrite_suggestions(tmp_path):
    project = Project(tmp_path / "p")
    project.open_target("cli:local", purpose="research")
    result = project.check_rules(
        "sort",
        [
            {
                "statement": "Sort uppercases its output.",
                "checks": [
                    {"kind": "outcome", "a": {"argv": ["sort"], "stdin": "b\na\n"}, "expect": {"stdout": "A\nB\n"}}
                ],
            }
        ],
        workers=1,
    )
    rule = result["rules"][0]
    assert rule["status"] == "falsified" and "a\\nb\\n" in rule["suggestions"][0]
