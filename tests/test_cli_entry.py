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
        text = (root / dockerfile).read_text().replace("\\\n", " ")  # join continued lines
        sources = [src for line in re.findall(r"^COPY (?!--from)(.+)$", text, re.M) for src in line.split()[:-1]]
        missing = sorted(n for n in needed if not any(n == s or n.startswith(s.rstrip("/") + "/") for s in sources))
        assert not missing, (dockerfile, missing)


def test_the_wheel_carries_the_room_files_and_no_local_secrets(tmp_path):
    import shutil
    import subprocess
    import zipfile
    from pathlib import Path

    if not shutil.which("uv"):
        pytest.skip("uv is not available")
    root = Path(__file__).resolve().parents[1]
    subprocess.run(["uv", "build", "--wheel", "-q", "--out-dir", str(tmp_path)], cwd=root, check=True)
    names = zipfile.ZipFile(next(tmp_path.glob("*.whl"))).namelist()
    for needed in ("teardown/_room/deploy/cleanroom.yaml", "teardown/_room/deploy/observerroom.yaml",
                   "teardown/_room/deploy/Dockerfile.clean", "teardown/_room/deploy/clean/room-claude",
                   "teardown/_room/pyproject.toml", "teardown/observer-playbook.md",
                   "teardown/_room/deploy/android-agent/build.sh",
                   "teardown/_room/deploy/android-agent/src/dev/teardown/agent/Agent.java"):
        assert needed in names, needed
    assert not [n for n in names if n.endswith((".keystore", ".apk", ".pem")) or "/.teardown/" in n]


def test_an_installed_copy_assembles_the_room_build_context(tmp_path, monkeypatch):
    from teardown import resources

    package = tmp_path / "site" / "teardown"
    (package / "_room" / "deploy").mkdir(parents=True)
    (package / "_room" / "pyproject.toml").write_text("[project]\n")
    (package / "_room" / "deploy" / "cleanroom.yaml").write_text("name: x\n")
    (package / "observer-playbook.md").write_text("# playbook\n")
    (package / "cli.py").write_text("")
    monkeypatch.setattr(resources, "PACKAGE", package)
    monkeypatch.setattr(resources, "in_checkout", lambda: False)
    monkeypatch.setenv("TEARDOWN_HOME", str(tmp_path / "home"))
    root = resources.room_root()
    assert root.is_relative_to(tmp_path / "home") and (root / "deploy" / "cleanroom.yaml").exists()
    assert (root / "src" / "teardown" / "cli.py").exists() and (root / "docs" / "observer-playbook.md").exists()
    assert not (root / "src" / "teardown" / "_room").exists()
    assert not (root / "src" / "teardown" / "observer-playbook.md").exists()  # once, under docs/
    assert resources.room_root() == root  # assembled once per version
