"""Every `teardown` subcommand dispatches (guards against parser/dispatch drift)."""

from __future__ import annotations

import pytest

from teardown.cli import main


@pytest.mark.parametrize("command", ["observe", "clean", "gate-serve", "remote-verify", "demo", "verify", "verify-web",
                                     "export-clean", "bench-jq", "bench-jsonl", "audit-verify"])
def test_every_subcommand_has_help(command, capsys):
    with pytest.raises(SystemExit) as exit_info:
        main([command, "--help"])
    assert exit_info.value.code == 0 and "usage" in capsys.readouterr().out


def test_dispatch_covers_every_parser():
    import inspect

    import teardown.cli as cli

    source = inspect.getsource(cli.main)
    for command in ["observe", "clean", "gate-serve", "remote-verify", "demo", "verify", "verify-web", "export-clean",
                    "bench-jq", "bench-jsonl", "audit-verify"]:
        assert f'args.command == "{command}"' in source, command
