"""Android driver (adb only): observe the accessibility hierarchy, act by role and accessible name.

Target spec::

    android:<serial>:<package>        e.g. android:emulator-5554:com.example.app
    target_options: {"activity": ".MainActivity"?}   (launcher activity is used otherwise)

Reset is ``pm clear`` (wipes app data and runtime permissions) plus a cold launch; the device's determinism settings
(animations off) are applied once per driver. Observation is ``uiautomator dump`` (the AccessibilityNodeInfo tree):
class, text, content description and state flags. Resource ids and activity names are implementation identifiers:
they are never put into observations (steering tier at most).

Hard refusals hold here as everywhere: no Frida/objection, no repackaging, no pinning, root-detection, attestation or
FLAG_SECURE bypasses. A screen that cannot be observed becomes an unknown.
"""

from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from teardown.core.ids import content_id
from teardown.drivers.base import Action, DeviceLost, Driver, DriverCapabilities

ROLE_BY_CLASS = {
    "Button": "button", "ImageButton": "button", "MaterialButton": "button", "EditText": "textbox",
    "AutoCompleteTextView": "textbox", "CheckBox": "checkbox", "Switch": "switch", "SwitchCompat": "switch",
    "RadioButton": "radio", "ToggleButton": "togglebutton", "Spinner": "combobox", "SeekBar": "slider",
    "TextView": "text", "ImageView": "image", "ListView": "list", "RecyclerView": "list", "ScrollView": "scroll",
    "TabWidget": "tablist", "ProgressBar": "progressbar",
}


def adb_path() -> str:
    found = shutil.which("adb")
    if found:
        return found
    candidate = Path.home() / "Library/Android/sdk/platform-tools/adb"
    if candidate.exists():
        return str(candidate)
    raise FileNotFoundError("adb not found (install Android platform-tools)")


def role_of(cls: str) -> str:
    return ROLE_BY_CLASS.get(cls.rsplit(".", 1)[-1], "view")


class AndroidAction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action: Literal["click", "fill", "key", "back", "longclick", "network"]
    role: str | None = None
    name: str | None = None
    value: str | None = Field(default=None, description="fill: text (ASCII: adb cannot type other characters); key: "
                              "keycode; network: 'off' | 'on' (airplane mode, restored at every reset)")

    @model_validator(mode="after")
    def _typeable(self) -> AndroidAction:
        if self.action == "fill" and self.value and not self.value.isascii():
            raise ValueError(f"Android input types ASCII only (adb `input text`); {self.value!r} would arrive empty. "
                             "Record what non-ASCII input does as an unknown instead")
        return self


def parse_dump(xml_text: str) -> list[dict[str, Any]]:
    start = xml_text.find("<?xml")
    root = ET.fromstring(xml_text[start:] if start >= 0 else xml_text)
    nodes = []

    def walk(el, depth):
        if el.tag == "node":
            b = [int(x) for x in re.findall(r"\d+", el.get("bounds", "[0,0][0,0]"))]
            nodes.append({"depth": depth, "role": role_of(el.get("class", "")), "text": el.get("text", ""),
                          "desc": el.get("content-desc", ""), "package": el.get("package", ""),
                          "checkable": el.get("checkable") == "true", "checked": el.get("checked") == "true",
                          "enabled": el.get("enabled") == "true", "focused": el.get("focused") == "true",
                          "selected": el.get("selected") == "true", "password": el.get("password") == "true",
                          "clickable": el.get("clickable") == "true",
                          "center": ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2) if len(b) == 4 else (0, 0)})
        for child in el:
            walk(child, depth + 1)

    walk(root, 0)
    return nodes


def agent_apk() -> Path:
    """The on-device agent: built in the checkout, or by `teardown install-android-agent` for an installed copy."""
    from teardown.resources import CHECKOUT, in_checkout, state_dir

    if in_checkout():
        return CHECKOUT / "deploy" / "android-agent" / "build" / "agent.apk"
    return state_dir() / "android-agent" / "agent.apk"


AGENT_APK = agent_apk()
AGENT_PACKAGE = "dev.teardown.agent"
AGENT_VERSION = 2  # deploy/android-agent/AndroidManifest.xml versionCode; an older agent on the device is replaced


_AVDS: dict[str, str] = {}  # serial -> AVD name, learned when a driver first configures an emulator
EMULATOR_ARGS = ["-no-window", "-no-audio", "-no-boot-anim", "-gpu", "swiftshader_indirect", "-no-snapshot-save"]


def emulator_path() -> str:
    found = shutil.which("emulator")
    if found:
        return found
    candidate = Path.home() / "Library/Android/sdk/emulator/emulator"
    if candidate.exists():
        return str(candidate)
    raise FileNotFoundError("emulator not found (install the Android emulator)")


def agent_nodes(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize the on-device agent's dump to the driver's node shape."""
    nodes = []
    for n in raw.get("nodes", []):
        b = n.get("bounds") or [0, 0, 0, 0]
        nodes.append({"depth": n["depth"], "role": role_of(n.get("class") or ""), "text": n.get("text") or "",
                      "desc": n.get("desc") or "", "hint": n.get("hint") or "", "showing_hint": n.get("showing_hint"),
                      "package": n.get("package") or "", "checkable": n["checkable"], "checked": n["checked"],
                      "enabled": n["enabled"], "focused": n["focused"], "selected": n["selected"],
                      "password": n["password"], "clickable": n["clickable"],
                      # agent v2: error text, heading, state description, range, and the window the node is in
                      **{k: n[k] for k in ("editable", "heading", "error", "state", "range", "window", "wtype",
                                           "wlayer", "wtitle") if k in n},
                      "center": ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2)})
    return nodes


class AndroidDriver(Driver):
    name = "android"

    def __init__(self, target_spec: str, actions: dict[str, AndroidAction] | None = None,
                 options: dict[str, Any] | None = None):
        _, self.serial, self.package = target_spec.split(":", 2)
        self.table = dict(actions or {})
        self.options = dict(options or {})
        self.adb = adb_path()
        self._configured = False
        self._agent_file = None
        self._agent_proc: subprocess.Popen | None = None
        self._use_agent = self.options.get("agent", True)
        self._network_off = False

    def _sh(self, *args: str, timeout: float = 30) -> str:
        cp = subprocess.run([self.adb, "-s", self.serial, *args], capture_output=True, text=True, timeout=timeout)
        return cp.stdout

    def target_fingerprint(self) -> str:
        info = self._sh("shell", "dumpsys", "package", self.package)
        version = re.search(r"versionName=(\S+)", info)
        code = re.search(r"versionCode=(\d+)", info)
        return content_id("tgt", {"platform": "android", "package": self.package,
                                  "version": version.group(1) if version else None,
                                  "code": code.group(1) if code else None})

    def capabilities(self) -> DriverCapabilities:
        return DriverCapabilities(platform="android", reset_cost_ms=1500.0, soft_reset=True, snapshots=True,
                                  parallelism=1)

    def _configure(self) -> None:
        for key in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
            self._sh("shell", "settings", "put", "global", key, "0")
        if self.serial.startswith("emulator-") and self.serial not in _AVDS:  # remember it, to restart it
            name = self._sh("emu", "avd", "name", timeout=10).strip().splitlines()
            if name and name[0] and "error" not in name[0].lower():
                _AVDS[self.serial] = name[0].strip()
        self._configured = True

    def device_state(self) -> str:
        try:
            cp = subprocess.run([self.adb, "-s", self.serial, "get-state"], capture_output=True, text=True,
                                timeout=15)
        except subprocess.TimeoutExpired:
            return "unknown"
        return cp.stdout.strip() or "absent"

    def ensure_device(self, timeout_s: float = 300) -> None:
        """Bring an emulator that crashed back (same AVD, same port, so the serial stays the same): the gate keeps
        verifying instead of failing every later call. Physical devices and unknown AVDs are left alone."""
        if self.device_state() == "device":
            return
        avd = (self.options.get("emulator") or {}).get("avd") or _AVDS.get(self.serial)
        port = self.serial.removeprefix("emulator-")
        if not avd or not port.isdigit():
            raise DeviceLost(f"device {self.serial} is not available and cannot be restarted here")
        subprocess.run([self.adb, "-s", self.serial, "emu", "kill"], capture_output=True, timeout=30)
        args = (self.options.get("emulator") or {}).get("args") or EMULATOR_ARGS
        log = Path.home() / ".teardown" / f"emulator-{port}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("ab") as out:
            subprocess.Popen([emulator_path(), "-avd", avd, "-port", port, *args], stdout=out, stderr=out,
                             start_new_session=True)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.device_state() == "device" and self._sh(
                    "shell", "getprop", "sys.boot_completed", timeout=15).strip() == "1":
                break
            time.sleep(3)
        else:
            raise DeviceLost(f"device {self.serial} did not come back within {timeout_s:.0f} s")
        self._agent_file, self._configured = None, False  # a fresh device: reconnect the agent, configure again
        if self._agent_proc is not None:
            self._agent_proc.kill()
            self._agent_proc = None
        self._configure()

    def reset(self) -> Any:
        self.ensure_device()
        if not self._configured:
            self._configure()
        self._sh("shell", "am", "force-stop", self.package)
        if self._network_off:  # a network fault never outlives its episode
            self._set_network(True)
        self._sh("shell", "pm", "clear", self.package)
        component = self._launcher()
        self._sh("shell", "am", "start", "-W", "-n", component, timeout=60)
        return self._wait_settled()

    def _launcher(self) -> str:
        """The component to launch: target_options['activity'], or the package's resolved launcher activity."""
        activity = self.options.get("activity")
        if activity:
            return f"{self.package}/{activity}"
        out = self._sh("shell", "cmd", "package", "resolve-activity", "--brief", "-c",
                       "android.intent.category.LAUNCHER", self.package)
        lines = [line.strip() for line in out.splitlines() if "/" in line]
        if not lines:
            raise RuntimeError(f"no launcher activity for {self.package}")
        return lines[-1]

    def _start_agent(self) -> bool:
        """Install/start the on-device observer (UiAutomation over a forwarded socket). ~5 ms per dump instead of
        ~2 s for `uiautomator dump`. Falls back to uiautomator when unavailable."""
        if not AGENT_APK.exists():
            return False
        installed = re.search(r"versionCode=(\d+)", self._sh("shell", "dumpsys", "package", AGENT_PACKAGE))
        if AGENT_PACKAGE not in self._sh("shell", "pm", "list", "instrumentation") or (
                installed is None or int(installed.group(1)) < AGENT_VERSION):
            cp = subprocess.run([self.adb, "-s", self.serial, "install", "-r", "-t", str(AGENT_APK)],
                                capture_output=True, text=True, timeout=120)
            if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in cp.stdout + cp.stderr:  # built with another signing key
                self._sh("uninstall", AGENT_PACKAGE)
                subprocess.run([self.adb, "-s", self.serial, "install", "-t", str(AGENT_APK)], capture_output=True,
                               timeout=120)
        self._sh("shell", "am", "force-stop", AGENT_PACKAGE)
        self._agent_proc = subprocess.Popen([self.adb, "-s", self.serial, "shell", "am", "instrument", "-w",
                                             f"{AGENT_PACKAGE}/.Agent"], stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL)
        port = self._sh("forward", "tcp:0", "tcp:9008").strip()
        for _ in range(50):
            try:
                sock = socket.create_connection(("127.0.0.1", int(port)), timeout=10)
                self._agent_file = sock.makefile("rwb")
                self._agent_call("idle")
                return True
            except (OSError, ValueError, json.JSONDecodeError):
                self._agent_file = None
                time.sleep(0.1)
        return False

    def _agent_call(self, cmd: str) -> dict[str, Any]:
        assert self._agent_file is not None
        self._agent_file.write((cmd + "\n").encode())
        self._agent_file.flush()
        line = self._agent_file.readline()
        if not line:
            raise OSError("agent connection closed")
        return json.loads(line)

    def _dump(self) -> list[dict[str, Any]]:
        if self._use_agent:
            try:
                if self._agent_file is None and not self._start_agent():
                    self._use_agent = False
                if self._agent_file is not None:
                    self._agent_call("idle")
                    return agent_nodes(self._agent_call("dump"))
            except (OSError, json.JSONDecodeError):
                self._agent_file = None
        out = ""
        for _ in range(5):  # "could not get idle state" on busy screens: retry briefly
            out = self._sh("exec-out", "uiautomator", "dump", "/dev/tty", timeout=30)
            if "<hierarchy" in out:
                break
            time.sleep(0.3)
        if "<hierarchy" not in out:
            if self.device_state() != "device":  # not an empty screen: the device is gone
                raise DeviceLost(f"device {self.serial} went away")
            return []
        return parse_dump(out[: out.rfind("</hierarchy>") + len("</hierarchy>")])

    def _wait_settled(self, before: Any = None) -> Any:
        """Two equal consecutive dumps (each dump already waits for UI idle), at most four. With ``before`` (the
        screen just before the action), first wait up to 0.6 s for the screen to change: right after a tap, two
        quick dumps can both still show the old screen."""
        time.sleep(0.15 if not self._agent_file else 0.05)
        last = self.observe()
        if before is not None:
            deadline = time.monotonic() + 0.6
            while last == before and time.monotonic() < deadline:
                time.sleep(0.05)
                last = self.observe()
        for _ in range(3):
            obs = self.observe()
            if obs == last:
                return obs
            last = obs
        return last

    def observe(self) -> Any:
        dump = self._dump()
        nodes = [n for n in dump if n["package"] in (self.package, "android")]
        keyboard = any(n.get("wtype") == 2 for n in dump)  # the soft keyboard's window: whether it is up, not its keys
        return {"nodes": [{k: v for k, v in n.items() if k not in ("center", "hint")} for n in nodes],
                **({"keyboard": True} if keyboard else {})}

    def _find(self, role: str | None, name: str | None) -> dict[str, Any] | None:
        for n in self._dump():
            if n["package"] != self.package:
                continue
            if (role is None or n["role"] == role) and (name is None or name in (n["text"], n["desc"])):
                return n
        return None

    def step(self, action: Action) -> Any | None:
        spec = AndroidAction.model_validate(action.params) if action.params else self.table.get(action.name)
        if spec is None:
            return None
        if spec.action == "network":
            self._set_network((spec.value or "on") != "off")
            return self._wait_settled()
        if spec.action == "back":
            before = self.observe()
            self._sh("shell", "input", "keyevent", "KEYCODE_BACK")
            return self._wait_settled(before)
        if spec.action == "key":
            before = self.observe()
            self._sh("shell", "input", "keyevent", spec.value or "KEYCODE_ENTER")
            return self._wait_settled(before)
        node = self._find(spec.role, spec.name)
        if node is None:
            return None
        if not node["enabled"]:
            return "DISABLED"
        x, y = node["center"]
        before = self.observe()
        if spec.action in ("click", "longclick"):
            if spec.action == "click":
                self._sh("shell", "input", "tap", str(x), str(y))
            else:
                self._sh("shell", "input", "swipe", str(x), str(y), str(x), str(y), "800")
        elif spec.action == "fill":
            escaped = (spec.value or "").replace("\\", "\\\\").replace(" ", "%s").replace("'", "\\'")
            escaped = escaped.replace('"', '\\"')
            deletes = " ".join(["KEYCODE_DEL"] * max(1, len(node["text"]) + 2))
            # one shell round trip: focus, clear, type
            script = f"input tap {x} {y}; input keyevent KEYCODE_MOVE_END; input keyevent {deletes}"
            if spec.value:
                script += f"; input text '{escaped}'"
            self._sh("shell", script)
        return self._wait_settled(before)

    def _set_network(self, on: bool) -> None:
        """Fault injection for observation: airplane mode on the device (the app's own network calls fail)."""
        self._sh("shell", "cmd", "connectivity", "airplane-mode", "disable" if on else "enable")
        self._network_off = not on
        time.sleep(0.5)

    def actions(self) -> list[str]:
        return sorted(self.table)

    def close(self) -> None:
        if self._network_off:
            self._set_network(True)
        if self._agent_proc is not None:
            self._agent_proc.kill()
            self._agent_proc = None
        self._agent_file = None
