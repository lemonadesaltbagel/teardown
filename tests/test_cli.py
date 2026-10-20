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
    obs = {"exit": 1, "signal": None, "timed_out": False, "stdout": "", "stdout_truncated": False,
           "stderr": "cut: in.txt: No such file or directory\n", "fs": []}
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
    hints = {"cmd": "cut", "base": ["-f", "2"], "selector_options": ["-b", "-c", "-f"], "sweep_inputs": ["tsv"],
             "inputs": ["tsv", "empty", "no_eol"], "pair_inputs": ["tsv"]}
    summary = project.probe_cli("cut", hints, workers=2, env_sample=20)
    assert summary["claims"] > 0 and summary["rows"] > 10
    statuses = {c.status for c in project.ledger.all().values()}
    assert statuses == {"corroborated"}
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


@needs_docker
def test_differential_gnu_vs_busybox(tmp_path):
    project = Project(tmp_path / "p")
    project.open_target("cli:docker:debian:stable-slim", purpose="interop")
    hints = {"cmd": "cut", "base": ["-f", "2"], "selector_options": ["-b", "-c", "-f"], "sweep_inputs": ["tsv"],
             "inputs": ["tsv", "empty"], "pair_inputs": ["tsv"]}
    project.probe_cli("cut", hints, env_sample=20)
    project.release_spec(project.compile_spec("cut").id)
    verifier = project.verifier()
    same = verifier.verify("cli:docker:debian:stable-slim", repeats=1)
    other = verifier.verify("cli:docker:busybox:musl", repeats=1)
    assert same.failed == 0 and other.failed > 0
