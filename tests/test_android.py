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


def test_android_kit_clone_is_built_installed_and_verified_and_network_fault_resets(tmp_path):
    import re

    from teardown.cleanroom import clone_package, export_kit, verify_kit
    from teardown.drivers.android.driver import AndroidAction, AndroidDriver
    from teardown.drivers.base import Action
    from teardown.project import Project

    project = Project(tmp_path / "p")
    project.open_target(f"android:{SERIAL}:com.example.tipper", purpose="research", real_names=["Tipper"])
    project.define_actions(ACTIONS)
    rules = [{"statement": "Reset empties every field.", "checks": [
        {"kind": "same", "a": {"actions": ["calculate"]}, "b": {"actions": ["bill_80", "reset", "calculate"]},
         "keys": ["controls"]}]}]
    project.check_rules("tips", rules, workers=1)
    rel = project.release_spec(project.compile_spec("tips").id)
    kit = tmp_path / "kit"
    export_kit(tmp_path / "p", kit)
    package = clone_package(rel.codename)
    source = (Path(__file__).parents[1] / "src/teardown/examples/android/src/com/example/tipper/Main.java").read_text()
    target = kit / "src" / package.replace(".", "/") / "Main.java"
    target.write_text(re.sub(r"^package [\w.]+;", f"package {package};", source, flags=re.M))
    verdict = verify_kit(project, kit, "android:kit")
    assert verdict["failed"] == 0 and verdict["passed"] > 0
    with pytest.raises(PermissionError):
        verify_kit(project, kit, f"android:{SERIAL}:com.example.tipper")

    driver = AndroidDriver(f"android:{SERIAL}:com.example.tipper")
    try:
        driver.reset()
        driver.step(Action(name="x", params=AndroidAction(action="network", value="off").model_dump()))
        assert subprocess.run([ADB, "-s", SERIAL, "shell", "settings", "get", "global", "airplane_mode_on"],
                              capture_output=True, text=True).stdout.strip() == "1"
        driver.reset()
        assert subprocess.run([ADB, "-s", SERIAL, "shell", "settings", "get", "global", "airplane_mode_on"],
                              capture_output=True, text=True).stdout.strip() == "0"
    finally:
        driver.close()


def test_field_probe_with_observer_defined_acceptance(tmp_path):
    from teardown.project import Project

    project = Project(tmp_path / "p")
    project.open_target(f"android:{SERIAL}:com.example.tipper", purpose="research")
    project.define_actions(ACTIONS)
    # every accepted bill amount gives a different total, so 'same outcome as the reference' cannot decide
    result = project.probe_ui_field("bill", prefix=[], role="textbox", name="Bill amount", submit="calculate",
                                    kind="number", classes={"small": "1", "typical": "80", "max": "10000",
                                                            "over": "10001", "zero": "0"},
                                    valid="typical", accepted_if={"text_contains": "total"})
    assert result["boundary"] is None  # numbers: no length search
    statements = [c.identity.statement for c in project.ledger.all().values()]
    accepted = [s for s in statements if "is accepted" in s]
    refused = [s for s in statements if "is refused" in s]
    assert any("max" in s for s in accepted) and any("small" in s for s in accepted)
    assert any("over" in s for s in refused) and any("zero" in s for s in refused)
