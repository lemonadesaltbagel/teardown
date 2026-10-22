"""Every `teardown` subcommand dispatches (guards against parser/dispatch drift)."""

from __future__ import annotations

import pytest

from teardown.cli import main


@pytest.mark.parametrize("command", ["observe", "clean", "gate-serve", "remote-verify", "demo", "verify", "verify-web",
                                     "export-clean", "bench-jq", "bench-jsonl", "audit-verify", "review",
                                     "approve", "release", "egress-proxy", "cleanroom",
                                     "observerroom", "verify-kit"])
def test_every_subcommand_has_help(command, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main([command, "--help"])
    assert exit_info.value.code == 0 and "usage" in capsys.readouterr().out


def test_dispatch_covers_every_parser():
    import inspect

    import teardown.cli as cli

    source = inspect.getsource(cli.main)
    for command in ["observe", "clean", "gate-serve", "remote-verify", "demo", "verify", "verify-web", "export-clean",
                    "bench-jq", "bench-jsonl", "audit-verify", "review", "approve", "release",
                    "egress-proxy", "cleanroom", "observerroom", "verify-kit"]:
        assert f'args.command == "{command}"' in source, command


def test_review_reports_classes_and_approve_refuses_without_a_terminal(tmp_path, capsys):
    import json

    from teardown.demo import ALPHABET
    from teardown.examples.signup import signup_mapper
    from teardown.project import Project

    project = Project(tmp_path / "p")
    project.open_target("fake:signup-a", purpose="substitute", strict=True, real_names=["Acme"])
    project.set_mapper(list(signup_mapper(project.state.target).rules))  # the first draft that leaks a label
    project.learn("signup", ALPHABET, walks_per_state=10, walk_len=8)
    assert main(["review", "--project", str(tmp_path / "p"), "--feature", "signup", "--json"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["mode"] == "strict" and summary["findings"] == summary["unapproved"] > 0
    assert {g["cls"] for g in summary["groups"]} <= {"expected-output", "interface", "prose"}
    code = main(["approve", "--project", str(tmp_path / "p"), "--feature", "signup", "--by", "me",
                 "--class", "expected-output", "--reason", "test-oracle"])  # pytest's stdin is not a terminal
    assert code == 2 and "interactive terminal" in capsys.readouterr().err


def test_no_subcommand_argument_shadows_the_command_name():
    """A subparser argument with dest 'command' silently overwrites the dispatch key (happened twice)."""
    import teardown.cli as cli

    parser_actions = []
    original = cli.argparse.ArgumentParser.parse_args

    def spy(self, *a, **k):
        parser_actions.append(self)
        return original(self, *a, **k)

    cli.argparse.ArgumentParser.parse_args = spy
    try:
        with pytest.raises(SystemExit):
            main(["--help"])
    finally:
        cli.argparse.ArgumentParser.parse_args = original
    top = parser_actions[0]
    sub = next(a for a in top._actions if isinstance(a, cli.argparse._SubParsersAction))
    for name, parser in sub.choices.items():
        assert all(a.dest != "command" for a in parser._actions), name


def test_room_images_copy_every_file_the_package_build_needs():
    """The rooms pip-install the source: files pyproject.toml force-includes or declares must be in the image."""
    import re
    import tomllib
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text())
    needed = set(project["project"].get("license-files", []))
    needed |= set(project["tool"]["hatch"]["build"]["targets"]["wheel"].get("force-include", {}))
    for dockerfile in ("deploy/Dockerfile", "deploy/Dockerfile.clean"):
        copied = " ".join(re.findall(r"^COPY (?!--from)(.+)$", (root / dockerfile).read_text(), re.M))
        assert all(n in copied for n in needed), (dockerfile, sorted(n for n in needed if n not in copied))
