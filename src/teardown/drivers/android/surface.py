"""The user-facing Android test surface as screen pairs: what an Espresso or UiAutomator suite can tell apart.

The audit app (``teardown/examples/android-surface``) draws one screen per case and side. In each CASES entry the
two sides differ in exactly one thing a role/text/description-based matcher or assertion can check. In each SAME
entry they differ only in implementation (wrappers, view ids, colors, padding), which an abstraction must not
record. ``audit`` runs every case under the given abstraction versions on a connected device.

Not part of the surface, by design: resource ids, class names beyond the role they give, layout parameters and
styling. A user-facing suite does not depend on them, and a clone is free to differ there.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

APP = Path(__file__).resolve().parents[2] / "examples" / "android-surface"
PACKAGE = "dev.teardown.surface"


@dataclass(frozen=True)
class Case:
    id: str
    checks: str  # the matcher or assertion that tells the sides apart


CASES = [
    Case("role", 'withText("Save") + isAssignableFrom(Button)  /  By.text("Save").clazz(Button)'),
    Case("text", 'withText("Active")'),
    Case("image-desc", 'withContentDescription("Hawk photo")'),
    Case("hint", 'withHint("e.g. 520")'),
    Case("value", 'withText("Quill") on the field  /  UiObject2.getText()'),
    Case("checked", "isChecked()"),
    Case("switch", "isChecked() on a switch"),
    Case("enabled", "isEnabled()"),
    Case("password", "UiObject2.isPassword() / the field masks its input"),
    Case("error", 'hasErrorText("Too heavy")'),
    Case("count", 'onView(withText("Delete")) matches one view (AmbiguousViewMatcherException otherwise)'),
    Case("order", 'hasSibling(withText("Ash"))  /  the order of items'),
    Case("progress", "the progress value (RangeInfo)"),
    Case("heading", "isHeading() (accessibility heading)"),
    Case("state", 'the state description ("Fly-ready")'),
    Case("selected", "isSelected()"),
    Case("focused", "hasFocus()"),
    Case("hidden", "isDisplayed()"),
    Case("spinner", 'withSpinnerText("Kestrel")'),
    Case("dialog", "isDialog() / inRoot(isDialog())"),
    Case("desc-name", 'withContentDescription("Close")'),
    Case("text-and-desc", 'withText("Open") on a button described as "Open North"'),
    Case("keyboard", "the soft keyboard is up (pressBack closes it instead of the screen)"),
]
SAME = [
    Case("same-wrapper", "(implementation)"),
    Case("same-id", "(implementation)"),
    Case("same-color", "(implementation)"),
    Case("same-padding", "(implementation)"),
]


def build_app() -> Path:
    apk = APP / "build" / "surface.apk"
    if not apk.exists():
        subprocess.run(["sh", str(APP / "build.sh")], check=True, capture_output=True)
    return apk


def audit(versions: list[str], *, serial: str = "emulator-5554") -> dict[str, dict[str, bool]]:
    """{case id: {version: the two sides give different symbols}}. Every CASES entry should differ and every
    SAME entry should not."""
    from teardown.drivers.android.driver import AndroidDriver, adb_path
    from teardown.engine.abstractions import BUILTINS

    adb = adb_path()
    subprocess.run([adb, "-s", serial, "install", "-r", "-t", str(build_app())], check=True, capture_output=True,
                   timeout=180)
    driver = AndroidDriver(f"android:{serial}:{PACKAGE}", options={"activity": ".Main"})
    observations: dict[str, Any] = {}
    try:
        driver.reset()
        for case in [*CASES, *SAME]:
            for side in ("a", "b"):
                subprocess.run([adb, "-s", serial, "shell", "am", "force-stop", PACKAGE], capture_output=True)
                subprocess.run([adb, "-s", serial, "shell", "am", "start", "-W", "-n", f"{PACKAGE}/.Main",
                                "--es", "case", case.id, "--es", "side", side], capture_output=True, timeout=60)
                time.sleep(0.3)  # then the screen as it settles (dialogs and error popups arrive a moment later)
                observations[f"{case.id}.{side}"] = driver._wait_settled()
    finally:
        driver.close()
    out: dict[str, dict[str, bool]] = {}
    for case in [*CASES, *SAME]:
        a, b = observations[f"{case.id}.a"], observations[f"{case.id}.b"]
        out[case.id] = {v: BUILTINS[v](a, {}) != BUILTINS[v](b, {}) for v in versions}
    return out
