"""A crashed emulator is restarted by the driver (skipped when no emulator is attached)."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import pytest

ADB = shutil.which("adb") or str(Path.home() / "Library/Android/sdk/platform-tools/adb")


def _emulator() -> str | None:
    try:
        out = subprocess.run([ADB, "devices"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    return next((line.split("\t")[0] for line in out.splitlines()[1:]
                 if line.startswith("emulator-") and line.endswith("\tdevice")), None)


SERIAL = _emulator()
pytestmark = pytest.mark.skipif(not SERIAL, reason="needs a running emulator (it is killed and restarted)")


def test_the_driver_restarts_an_emulator_that_crashed():
    from teardown.drivers.android.driver import AndroidDriver

    driver = AndroidDriver(f"android:{SERIAL}:dev.teardown.surface", options={"activity": ".Main"})
    try:
        assert driver.reset()["nodes"]  # learns the AVD while the emulator is up
        subprocess.run([ADB, "-s", SERIAL, "emu", "kill"], capture_output=True, timeout=30)
        for _ in range(30):
            if driver.device_state() != "device":
                break
            time.sleep(1)
        assert driver.device_state() != "device"  # the emulator is gone
        assert driver.reset()["nodes"]  # brought back, and the app observed again
        assert driver.device_state() == "device"
    finally:
        driver.close()
