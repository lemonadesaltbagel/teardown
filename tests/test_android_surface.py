"""The Android surface audit on the emulator (skipped when no device is attached)."""

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
    return next((line.split("\t")[0] for line in out.splitlines()[1:] if line.endswith("\tdevice")), None)


SERIAL = _device()
pytestmark = pytest.mark.skipif(not SERIAL, reason="needs an emulator or device (adb)")


def test_android_a11y_v3_records_the_user_facing_espresso_surface():
    from teardown.drivers.android.surface import CASES, SAME, audit

    result = audit(["android.a11y/v1", "android.a11y/v2", "android.a11y/v3"], serial=SERIAL)
    assert [c.id for c in CASES if not result[c.id]["android.a11y/v3"]] == []  # every user-facing difference
    assert [c.id for c in SAME if result[c.id]["android.a11y/v3"]] == []  # no implementation difference
    assert [c.id for c in CASES if not result[c.id]["android.a11y/v2"]] == ["text-and-desc", "keyboard"]  # v2 as was
    assert sum(result[c.id]["android.a11y/v1"] for c in CASES) < len(CASES)  # v1 misses several (9-12 of 23)
