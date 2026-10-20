"""Linux desktop loop in a container (skipped when the desktop image is not built)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1] / "src/teardown/examples/desktop"
IMAGE = "teardown/desktop-linux"
HAVE_IMAGE = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode == 0
pytestmark = pytest.mark.skipif(not HAVE_IMAGE, reason="build deploy/desktop-linux first")

OPTIONS = {"app": ["python3", "/app/converter.py"], "mount": f"{APP_DIR}:/app"}
ACTIONS = {
    "c2f": {"action": "click", "role": "radio button", "name": "Celsius to Fahrenheit"},
    "f2c": {"action": "click", "role": "radio button", "name": "Fahrenheit to Celsius"},
    "t100": {"action": "fill", "role": "text", "name": "Temperature", "value": "100"},
    "convert": {"action": "click", "role": "button", "name": "Convert"},
    "clear": {"action": "click", "role": "button", "name": "Clear history"},
}


def test_desktop_observe_probe_release_verify(tmp_path):
    from teardown.project import Project

    project = Project(tmp_path / "p")
    project.open_target(f"desktop:docker:{IMAGE}", purpose="research", target_options=OPTIONS)
    project.define_actions(ACTIONS)
    outputs = project.session().run(["convert", "t100", "convert"], use_cache=False)[0]
    assert outputs[0] == "DISABLED" and "212" in outputs[2]
    result = project.probe_ui_field("convert", prefix=["c2f"], role="text", name="Temperature", submit="convert",
                                    kind="number", classes={"boiling": "100", "zero": "0", "below_zero": "-300",
                                                            "text": "abc", "comma": "36,6"}, valid="boiling",
                                    boundary=False, workers=2)
    assert result["claims"] >= 2
    rules = [{"statement": "Clearing the history leaves the last result visible but empties the list.", "checks": [
        {"kind": "differs", "a": {"actions": ["t100", "convert"]}, "b": {"actions": ["t100", "convert", "clear"]},
         "keys": ["items"]}]}]
    assert project.check_rules("convert", rules, workers=1)["rules"][0]["status"] == "corroborated"
    project.release_spec(project.compile_spec("convert").id)
    verifier = project.verifier()
    assert verifier.verify(f"desktop:docker:{IMAGE}", repeats=1).failed == 0
    lenient = {"target_options": {**OPTIONS, "app": ["python3", "/app/converter.py", "--lenient"]}}
    assert verifier.verify(f"desktop:docker:{IMAGE}", repeats=1, adapter=lenient).failed > 0
