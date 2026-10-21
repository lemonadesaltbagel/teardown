"""Every `teardown` subcommand dispatches (guards against parser/dispatch drift)."""

from __future__ import annotations

import pytest

from teardown.cli import main


@pytest.mark.parametrize("command", ["observe", "clean", "gate-serve", "remote-verify", "demo", "verify", "verify-web",
                                     "export-clean", "bench-jq", "bench-jsonl", "audit-verify", "review",
                                     "approve", "release"])
def test_every_subcommand_has_help(command, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main([command, "--help"])
    assert exit_info.value.code == 0 and "usage" in capsys.readouterr().out


def test_dispatch_covers_every_parser():
    import inspect

    import teardown.cli as cli

    source = inspect.getsource(cli.main)
    for command in ["observe", "clean", "gate-serve", "remote-verify", "demo", "verify", "verify-web", "export-clean",
                    "bench-jq", "bench-jsonl", "audit-verify", "review", "approve", "release"]:
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
