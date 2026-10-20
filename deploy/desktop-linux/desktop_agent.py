"""Teardown desktop agent (runs inside the Linux target container).

Starts Xvfb, a D-Bus session and the AT-SPI registry, then serves line-delimited JSON commands on stdin/stdout:

    {"op": "reset", "app": [argv...]}                      kill the app, wipe app state under $HOME, relaunch, wait
    {"op": "act", "action": "click|fill|toggle|key", "role": ..., "name": ..., "value": ...}
    {"op": "observe"}                                      accessibility tree of the app's windows

Elements are addressed by accessibility role and name only. The agent never reads the app's files.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time

DISPLAY = ":99"
os.environ["DISPLAY"] = DISPLAY
HOME = os.path.expanduser("~")
KEEP = {".dbus", ".cache"}


def _start_session() -> None:
    subprocess.Popen(["Xvfb", DISPLAY, "-screen", "0", "1280x800x24", "-nolisten", "tcp"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        if os.path.exists(f"/tmp/.X11-unix/X{DISPLAY[1:]}"):
            break
        time.sleep(0.05)
    out = subprocess.run(["dbus-launch", "--sh-syntax"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if "=" in line and line.startswith("DBUS_"):
            key, _, value = line.partition("=")
            os.environ[key] = value.strip().rstrip(";").strip("'")
    for launcher in ("/usr/libexec/at-spi-bus-launcher", "/usr/lib/at-spi2-core/at-spi-bus-launcher"):
        if os.path.exists(launcher):
            subprocess.Popen([launcher, "--launch-immediately"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            break
    time.sleep(0.5)


_start_session()

import gi  # noqa: E402

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi  # noqa: E402

APP: subprocess.Popen | None = None
APP_NAME: str | None = None


def _wipe_home() -> None:
    for entry in os.listdir(HOME):
        if entry in KEEP:
            continue
        path = os.path.join(HOME, entry)
        shutil.rmtree(path, ignore_errors=True) if os.path.isdir(path) else os.remove(path)


def _app_node():
    desktop = Atspi.get_desktop(0)
    for i in range(desktop.get_child_count()):
        child = desktop.get_child_at_index(i)
        if child is not None and APP is not None and child.get_process_id() == APP.pid:
            return child
    return None


def reset(app: list[str]) -> dict:
    global APP
    if APP is not None:
        APP.kill()
        APP.wait()
    _wipe_home()
    APP = subprocess.Popen(app, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, cwd=HOME)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        node = _app_node()
        if node is not None and node.get_child_count() > 0:
            time.sleep(0.15)
            return {"ok": True}
        if APP.poll() is not None:
            return {"ok": False, "reason": "app exited", "exit": APP.returncode}
        time.sleep(0.05)
    return {"ok": False, "reason": "no accessible window"}


def _states(node) -> list[str]:
    s = node.get_state_set()
    names = []
    for state, label in ((Atspi.StateType.CHECKED, "checked"), (Atspi.StateType.ENABLED, "enabled"),
                         (Atspi.StateType.SENSITIVE, "sensitive"), (Atspi.StateType.FOCUSED, "focused"),
                         (Atspi.StateType.SELECTED, "selected"), (Atspi.StateType.EXPANDED, "expanded"),
                         (Atspi.StateType.EDITABLE, "editable"), (Atspi.StateType.SHOWING, "showing"),
                         (Atspi.StateType.MODAL, "modal"), (Atspi.StateType.ACTIVE, "active")):
        if s.contains(state):
            names.append(label)
    return names


def _text(node) -> str | None:
    try:
        return Atspi.Text.get_text(node, 0, Atspi.Text.get_character_count(node))
    except Exception:  # noqa: BLE001 - not a text object
        return None


def _walk(node, depth=0, limit=2000, out=None):
    out = out if out is not None else []
    if node is None or len(out) >= limit or depth > 40:
        return out
    try:
        role = node.get_role_name()
        name = node.get_name() or ""
        states = _states(node)
    except Exception:  # noqa: BLE001 - nodes can vanish while walking
        return out
    if "showing" in states or depth <= 1:
        entry = {"depth": depth, "role": role, "name": name, "states": states}
        text = _text(node) if role in ("text", "entry", "label", "password text", "paragraph", "terminal") else None
        if text is not None and role != "label":
            entry["text"] = text
        if role == "label" and not name and text:
            entry["name"] = text
        out.append(entry)
        for i in range(node.get_child_count()):
            _walk(node.get_child_at_index(i), depth + 1, limit, out)
    return out


def observe() -> dict:
    node = _app_node()
    if node is None:
        return {"ok": False, "reason": "app not running", "exit": APP.poll() if APP else None}
    return {"ok": True, "tree": _walk(node)}


def _find(node, role: str, name: str):
    stack = [node]
    while stack:
        cur = stack.pop()
        try:
            if cur.get_role_name() == role and (cur.get_name() or "") == name and "showing" in _states(cur):
                return cur
            stack.extend(cur.get_child_at_index(i) for i in range(cur.get_child_count() - 1, -1, -1))
        except Exception:  # noqa: BLE001
            continue
    return None


def act(cmd: dict) -> dict:
    root = _app_node()
    if root is None:
        return {"ok": False, "reason": "app not running"}
    if cmd["action"] == "key":
        Atspi.generate_keyboard_event(0, cmd.get("value", "Return"), Atspi.KeySynthType.STRING)
        time.sleep(0.1)
        return {"ok": True}
    node = _find(root, cmd["role"], cmd["name"])
    if node is None:
        return {"ok": False, "reason": "absent"}
    if "sensitive" not in _states(node) and "enabled" not in _states(node):
        return {"ok": False, "reason": "disabled"}
    action = cmd["action"]
    if action == "fill":
        Atspi.EditableText.set_text_contents(node, cmd.get("value", ""))
    else:  # click / toggle: the first accessible action ("click", "press", "toggle", "activate")
        Atspi.Action.do_action(node, 0)
    time.sleep(cmd.get("settle_ms", 120) / 1000)
    return {"ok": True}


def main() -> None:
    print(json.dumps({"ok": True, "ready": True}), flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            cmd = json.loads(line)
            op = cmd.get("op")
            if op == "reset":
                reply = reset(cmd["app"])
            elif op == "act":
                reply = act(cmd)
            elif op == "observe":
                reply = observe()
            elif op == "quit":
                break
            else:
                reply = {"ok": False, "reason": f"unknown op {op}"}
        except Exception as exc:  # noqa: BLE001 - report, keep serving
            reply = {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}
        print(json.dumps(reply), flush=True)


if __name__ == "__main__":
    main()
