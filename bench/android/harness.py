"""Hidden-suite harness for Android apps: black-box scenarios over adb + `uiautomator dump`.

Deliberately independent of Teardown's Android driver and on-device agent, so a clone is not graded by the same
code that observed the original.

Scenario (one JSON object per line):

    {"id": "split_uneven",
     "steps": [{"type": {"field": "Bill amount", "text": "80"}}, {"tap": "Calculate"}, {"back": true},
               {"wait_ms": 300}, {"scroll": "down"}],
     "expect": [{"text": "26.67", "present": true}, {"text": "Error", "present": false},
                {"enabled": "Calculate", "value": false}, {"checked": "Round up", "value": true},
                {"field": "Bill amount", "value": ""}]}

- ``tap``: a node whose text or content description equals the string (first match on screen).
- ``type``: focus the field whose content description or hint equals ``field``, clear it, type ``text``.
- ``text``: ``present`` true/false: some node's text or content description *contains* the string.
- ``enabled`` / ``checked``: the node whose text or description equals the string has that state.
- ``field``: the field's current text (an empty field reads as ""). Text fields must have a content description
  equal to their hint: uiautomator reports an empty field's hint as its text.

Run:  python bench/android/harness.py --serial emulator-5554 --package com.example.app --suite tests.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ADB = shutil.which("adb") or str(Path.home() / "Library/Android/sdk/platform-tools/adb")


class Device:
    def __init__(self, serial: str, package: str):
        self.serial, self.package = serial, package

    def sh(self, *args: str, timeout: float = 30) -> str:
        return subprocess.run([ADB, "-s", self.serial, "shell", *args], capture_output=True, text=True,
                              timeout=timeout).stdout

    def launch(self) -> None:
        self.sh("am", "force-stop", self.package)
        self.sh("pm", "clear", self.package)
        out = self.sh("cmd", "package", "resolve-activity", "--brief", "-c", "android.intent.category.LAUNCHER",
                      self.package)
        component = [ln.strip() for ln in out.splitlines() if "/" in ln][-1]
        self.sh("am", "start", "-W", "-n", component, timeout=60)
        time.sleep(0.8)

    def nodes(self) -> list[dict]:
        for _ in range(5):
            out = subprocess.run([ADB, "-s", self.serial, "exec-out", "uiautomator", "dump", "/dev/tty"],
                                 capture_output=True, text=True, timeout=60).stdout
            if "<hierarchy" in out:
                xml = out[out.find("<?xml"): out.rfind("</hierarchy>") + len("</hierarchy>")]
                break
            time.sleep(0.3)
        else:
            return []
        nodes = []
        for el in ET.fromstring(xml).iter("node"):
            if el.get("package") != self.package:
                continue
            b = [int(x) for x in re.findall(r"\d+", el.get("bounds", "[0,0][0,0]"))]
            nodes.append({"text": el.get("text", ""), "desc": el.get("content-desc", ""),
                          "hint": el.get("hint", "") or "", "class": el.get("class", ""),
                          "enabled": el.get("enabled") == "true", "checked": el.get("checked") == "true",
                          # uiautomator reports an empty field's hint as its text; apps under test set a field's
                          # content description equal to its hint, so text == description reads as empty
                          "showing_hint": "EditText" in el.get("class", "") and bool(el.get("text")) and (
                              el.get("text") in (el.get("hint") or None, el.get("content-desc"))),
                          "center": ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2) if len(b) == 4 else (0, 0)})
        return nodes

    def find(self, label: str, nodes: list[dict] | None = None) -> dict | None:
        for n in nodes if nodes is not None else self.nodes():
            if label in (n["text"], n["desc"], n["hint"]):
                return n
        return None

    def tap(self, label: str) -> bool:
        n = self.find(label)
        if n is None:
            return False
        self.sh("input", "tap", str(n["center"][0]), str(n["center"][1]))
        time.sleep(0.5)
        return True

    def type(self, field: str, text: str) -> bool:
        n = self.find(field)
        if n is None:
            return False
        x, y = n["center"]
        current = "" if n["showing_hint"] else n["text"]
        deletes = " ".join(["KEYCODE_DEL"] * (len(current) + 2))
        self.sh(f"input tap {x} {y}; input keyevent KEYCODE_MOVE_END; input keyevent {deletes}")
        if text:
            escaped = text.replace("\\", "\\\\").replace(" ", "%s").replace("'", "\\'").replace('"', '\\"')
            self.sh(f"input text '{escaped}'")
        time.sleep(0.4)
        return True


def check(dev: Device, expect: list[dict]) -> list[str]:
    nodes = dev.nodes()
    problems = []
    for e in expect:
        if "text" in e:
            seen = any(e["text"] in n["text"] or e["text"] in n["desc"] for n in nodes
                       if not n["showing_hint"] or e["text"] in n["desc"])
            if seen != e.get("present", True):
                problems.append(f"text {e['text']!r} present={seen}")
        elif "enabled" in e or "checked" in e:
            key = "enabled" if "enabled" in e else "checked"
            n = dev.find(e[key], nodes)
            if n is None or n[key] != e["value"]:
                problems.append(f"{key} {e[key]!r} is {None if n is None else n[key]}")
        elif "field" in e:
            n = dev.find(e["field"], nodes)
            value = None if n is None else ("" if n["showing_hint"] else n["text"])
            if value != e["value"]:
                problems.append(f"field {e['field']!r} reads {value!r}")
    return problems


def run(serial: str, package: str, suite: Path, rename: tuple[str, str] | None = None) -> dict:
    dev = Device(serial, package)
    failures = []
    tests = [json.loads(line) for line in suite.read_text(encoding="utf-8").splitlines() if line.strip()]
    for t in tests:
        if rename:  # the clone shows its codename where the original shows its real name
            t = json.loads(json.dumps(t).replace(rename[0], rename[1]))
        dev.launch()
        problem = None
        for step in t.get("steps", []):
            if "tap" in step and not dev.tap(step["tap"]):
                problem = f"cannot tap {step['tap']!r}"
            elif "type" in step and not dev.type(step["type"]["field"], step["type"]["text"]):
                problem = f"cannot type into {step['type']['field']!r}"
            elif step.get("back"):
                dev.sh("input", "keyevent", "KEYCODE_BACK")
                time.sleep(0.4)
            elif "wait_ms" in step:
                time.sleep(step["wait_ms"] / 1000)
            elif "scroll" in step:
                dev.sh("input", "swipe", "540", "1500" if step["scroll"] == "down" else "600", "540",
                       "600" if step["scroll"] == "down" else "1500", "300")
                time.sleep(0.4)
            if problem:
                break
        problems = [problem] if problem else check(dev, t.get("expect", []))
        if problems:
            failures.append({"id": t["id"], "problems": problems})
    dev.sh("am", "force-stop", package)
    return {"passed": len(tests) - len(failures), "total": len(tests), "failures": failures}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", required=True)
    ap.add_argument("--package", required=True)
    ap.add_argument("--suite", required=True, type=Path)
    ap.add_argument("--rename", nargs=2, metavar=("FROM", "TO"))
    args = ap.parse_args()
    result = run(args.serial, args.package, args.suite, tuple(args.rename) if args.rename else None)
    print(json.dumps(result, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
