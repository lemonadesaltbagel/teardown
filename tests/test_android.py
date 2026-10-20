"""Android loop on the emulator (skipped when no device is attached)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ADB = shutil.which("adb") or str(Path.home() / "Library/Android/sdk/platform-tools/adb")


def _device() -> str | None:
    try:
        out = subprocess.run([ADB, "devices"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    for line in out.splitlines()[1:]:
        if line.endswith("\tdevice"):
            return line.split("\t")[0]
    return None


def _installed(serial: str, package: str) -> bool:
    out = subprocess.run([ADB, "-s", serial, "shell", "pm", "list", "packages", package], capture_output=True,
                         text=True).stdout
    return f"package:{package}\n" in out + "\n"


SERIAL = _device()
pytestmark = pytest.mark.skipif(
    not SERIAL or not _installed(SERIAL, "com.example.tipper") or not _installed(SERIAL, "com.example.tipper.b"),
    reason="needs an emulator with the example apps (src/teardown/examples/android*/build.sh + adb install)")

ACTIONS = {
    "bill_80": {"action": "fill", "role": "textbox", "name": "Bill amount", "value": "80"},
    "tip_55": {"action": "fill", "role": "textbox", "name": "Tip percent", "value": "55"},
    "people_3": {"action": "fill", "role": "textbox", "name": "Number of people", "value": "3"},
    "round_up": {"action": "click", "role": "checkbox", "name": "Round up per person"},
    "calculate": {"action": "click", "role": "button", "name": "Calculate"},
    "reset": {"action": "click", "role": "button", "name": "Reset"},
}


def test_android_observe_probe_rule_release_verify(tmp_path):
    from teardown.project import Project

    project = Project(tmp_path / "p")
    project.open_target(f"android:{SERIAL}:com.example.tipper", purpose="research")
    project.define_actions(ACTIONS)
    outputs = project.session().run(["calculate"], use_cache=False)[0]
    assert outputs == ["DISABLED"]  # client-side: Calculate is disabled until a bill is entered
    result = project.probe_ui_field("tips", prefix=["bill_80"], role="textbox", name="Tip percent", submit="calculate",
                                    kind="number", classes={"empty": "", "zero": "0", "ten": "10", "fifty": "50",
                                                            "fifty_one": "51", "huge": "999"}, valid="ten",
                                    boundary=False)
    assert result["claims"] >= 2
    rules = [{"statement": "Rounding up changes the per-person share only when the split is uneven.", "checks": [
        {"kind": "differs", "a": {"actions": ["bill_80", "people_3", "calculate"]},
         "b": {"actions": ["bill_80", "people_3", "round_up", "calculate"]}, "keys": ["text"]},
        {"kind": "same", "a": {"actions": ["bill_80", "calculate"]},
         "b": {"actions": ["bill_80", "round_up", "calculate"]}, "keys": ["text"]}]},
        {"statement": "Reset empties every field.", "checks": [
            {"kind": "same", "a": {"actions": ["calculate"]}, "b": {"actions": ["bill_80", "reset", "calculate"]},
             "keys": ["controls"]}]}]
    assert [r["status"] for r in project.check_rules("tips", rules, workers=1)["rules"]] == ["corroborated"] * 2
    project.release_spec(project.compile_spec("tips").id)
    verifier = project.verifier()
    same = verifier.verify(f"android:{SERIAL}:com.example.tipper", repeats=1)
    variant = verifier.verify(f"android:{SERIAL}:com.example.tipper.b", repeats=1)  # tip limit 60 instead of 50
    assert same.failed == 0 and same.passed > 0
    assert variant.failed > 0
