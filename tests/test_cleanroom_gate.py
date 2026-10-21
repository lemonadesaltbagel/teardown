"""The gate in kit mode: the clean side can only name clones built from the kit."""

from __future__ import annotations

import shutil

import pytest

pytest.importorskip("playwright")

from teardown.cli import _local_room  # noqa: E402
from teardown.drivers.web.driver import EXAMPLES, LocalSite, shutdown_browser  # noqa: E402
from teardown.project import Project  # noqa: E402


def test_kit_gate_verifies_web_kit_and_refuses_other_targets(tmp_path):
    site = LocalSite(EXAMPLES)
    try:
        project = Project(tmp_path / "p")
        project.open_target("web:" + site.url("fetcher.html"), purpose="research")
        project.define_actions({"load": {"op": "click", "role": "button", "name": "Load quotes"}})
        project.check_rules("quotes", [{"statement": "Loading lists the quotes.",
                                        "checks": [{"kind": "outcome", "a": {"actions": ["load"]},
                                                    "expect": {"headings": ["Quotes"]}}]}], workers=1)
        project.release_spec(project.compile_spec("quotes").id)
        kit = tmp_path / "kit"
        (kit / "impl").mkdir(parents=True)
        shutil.copy(EXAMPLES / "fetcher.html", kit / "impl" / "index.html")
        shutil.copy(EXAMPLES / "quotes.json", kit / "impl" / "quotes.json")
        room = _local_room(project, kit=kit)
        verdict = room.verify_against_original("web:kit")
        assert verdict["passed"] >= 1 and verdict["failed"] == 0
        for target in ("fake:py:teardown.examples.signup_clone:CleanSignup", "cli:local", "web:" + site.url("")):
            with pytest.raises(PermissionError):
                room.verify_against_original(target)
    finally:
        site.close()
        shutdown_browser()
