"""Spike: read the AX tree of a running macOS app (default: Calculator).

Usage: .venv/bin/python ax_dump.py [AppName] [out.json]
Read-only. Does not change system settings. Requires the *host process*
(Terminal / the Claude Code binary) to hold the Accessibility TCC grant.
"""
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter

from ApplicationServices import (
    AXIsProcessTrusted,
    AXUIElementCopyAttributeNames,
    AXUIElementCopyAttributeValue,
    AXUIElementCopyActionNames,
    AXUIElementCreateApplication,
)
from AppKit import NSWorkspace

APP = sys.argv[1] if len(sys.argv) > 1 else "Calculator"
OUT = sys.argv[2] if len(sys.argv) > 2 else "calculator_tree.json"

KEEP = ["AXRole", "AXSubrole", "AXRoleDescription", "AXTitle", "AXDescription",
        "AXIdentifier", "AXValue", "AXHelp", "AXEnabled", "AXMenuItemCmdChar",
        "AXMenuItemCmdModifiers"]


def attr(el, name):
    err, val = AXUIElementCopyAttributeValue(el, name, None)
    return val if err == 0 else None


def node(el, depth=0, max_depth=40, stats=None):
    d = {}
    for k in KEEP:
        v = attr(el, k)
        if v is not None:
            d[k] = v if isinstance(v, (str, int, float, bool)) else str(v)
    err, acts = AXUIElementCopyActionNames(el, None)
    if err == 0 and acts:
        d["actions"] = list(acts)
    stats["nodes"] += 1
    stats["roles"][d.get("AXRole", "?")] += 1
    if d.get("AXIdentifier"):
        stats["with_id"] += 1
    if d.get("AXTitle") or d.get("AXDescription") or d.get("AXValue"):
        stats["labelled"] += 1
    stats["max_depth"] = max(stats["max_depth"], depth)
    kids = attr(el, "AXChildren") or []
    if depth < max_depth:
        d["children"] = [node(c, depth + 1, max_depth, stats) for c in kids]
    return d


def main():
    print("AXIsProcessTrusted() =", AXIsProcessTrusted())
    subprocess.run(["open", "-a", APP], check=True)
    time.sleep(2.5)
    pid = None
    for a in NSWorkspace.sharedWorkspace().runningApplications():
        if a.localizedName() == APP:
            pid = a.processIdentifier()
    print("pid =", pid)
    app = AXUIElementCreateApplication(pid)
    err, names = AXUIElementCopyAttributeNames(app, None)
    print("AXUIElementCopyAttributeNames err =", err, "names =", names and list(names))
    err, wins = AXUIElementCopyAttributeValue(app, "AXWindows", None)
    print("AXWindows err =", err)
    stats = {"nodes": 0, "roles": Counter(), "with_id": 0, "labelled": 0, "max_depth": 0}
    t0 = time.time()
    tree = node(app, stats=stats)
    dt = time.time() - t0
    # menu inventory
    mstats = {"nodes": 0, "roles": Counter(), "with_id": 0, "labelled": 0, "max_depth": 0}
    menubar = attr(app, "AXMenuBar")
    menu_items = []
    if menubar is not None:
        def walk(el, path):
            t = attr(el, "AXTitle")
            r = attr(el, "AXRole")
            if r == "AXMenuItem" and t:
                menu_items.append((" > ".join(path + [t]), attr(el, "AXMenuItemCmdChar"),
                                   attr(el, "AXMenuItemCmdModifiers"), attr(el, "AXEnabled")))
            for c in attr(el, "AXChildren") or []:
                walk(c, path + ([t] if t and r in ("AXMenuBarItem", "AXMenuItem") else []))
        walk(menubar, [])
    canon = json.dumps(tree, sort_keys=True, default=str)
    print(json.dumps({
        "elapsed_s": round(dt, 3),
        "nodes": stats["nodes"], "max_depth": stats["max_depth"],
        "with_AXIdentifier": stats["with_id"], "labelled": stats["labelled"],
        "top_roles": stats["roles"].most_common(12),
        "menu_items": len(menu_items),
        "menu_items_with_shortcut": sum(1 for m in menu_items if m[1]),
        "tree_sha256_16": hashlib.sha256(canon.encode()).hexdigest()[:16],
    }, indent=1, default=str))
    for m in menu_items[:25]:
        print("  menu:", m)
    with open(OUT, "w") as f:
        f.write(json.dumps({"tree": tree, "menu": menu_items}, indent=1, default=str))
    subprocess.run(["osascript", "-e", f'quit app "{APP}"'])


if __name__ == "__main__":
    main()
