"""UI discovery: a bounded crawl that clicks every enabled control reachable from the start screen.

Screens are identified by what the user sees: route (web), headings, and the set of controls. The crawl replays
an action path from a fresh reset for every transition, so each observation is reproducible. Its output is the
observer's starting inventory: every screen with the path that reaches it, every control and field on it, and
(web) which API calls each transition made.

With ``fill`` it also fills every field on a screen with a plausible value for its kind before clicking that
screen's controls, so the crawl gets past forms. The fill actions become part of the recorded path.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from teardown.core.ids import content_id

CLICKABLE = {"button", "link", "checkbox", "tab", "menuitem", "switch", "radio", "togglebutton", "push button",
             "toggle button", "check box", "radio button", "menu item", "page tab"}
FIELDS = {"textbox", "searchbox", "combobox", "spinbutton", "text", "entry", "password text"}


def _controls(symbol: Any) -> dict[str, list[str]]:
    return symbol.get("controls", {}) if isinstance(symbol, dict) else {}


def screen_key(symbol: Any) -> str:
    """Identity of a UI state: route, headings, control names and which of them are enabled (so ticking a box
    that enables a button is a new state to explore). Text and field contents are not part of it."""
    if not isinstance(symbol, dict):
        return content_id("scr", {"value": symbol})[:20]
    controls = _controls(symbol)
    return content_id("scr", {"path": (symbol.get("path") or "").split("?")[0], "headings": symbol.get("headings"),
                              "controls": sorted(controls),
                              "disabled": sorted(k for k, f in controls.items() if "disabled" in f)})[:20]


def route_template(path: str) -> str:
    """REST-like routes: every second segment is data (/article/<slug>, /profile/<name>/favorites)."""
    parts = [p for p in path.split("?")[0].split("/") if p]
    return "/" + "/".join("*" if i % 2 == 1 else p for i, p in enumerate(parts))


def signature(symbol: Any) -> str:
    """Template identity: the route template and the non-link controls with numbers masked. Screens that differ
    only in data (one article page vs another, a tag page per tag) share a signature and are explored once."""
    if not isinstance(symbol, dict):
        return screen_key(symbol)
    parts = [p for p in (symbol.get("path") or "").split("?")[0].split("/") if p]
    data = [p for i, p in enumerate(parts) if i % 2 == 1 and len(p) >= 3]

    def generic(key: str) -> str:
        for value in data:  # route data shown in names ("Follow janedoe" on /profile/janedoe)
            key = key.replace(value, "*")
        return re.sub(r"\d+", "#", key)

    # navigation links (short names) shape a screen; long link names are data (list previews, article titles)
    controls = sorted({generic(k) for k in _controls(symbol)
                       if not (k.startswith("link:") and len(split_control(k)[1].split()) > 4)})
    return content_id("sig", {"route": route_template(symbol.get("path") or ""), "controls": controls,
                              "headings": [] if symbol.get("path") else symbol.get("headings")})[:20]


def split_control(key: str) -> tuple[str, str]:
    role, _, name = key.partition(":")
    return role, name


def guess_kind(name: str) -> str:
    low = name.lower()
    if "mail" in low:
        return "email"
    if "password" in low:
        return "password"
    if any(w in low for w in ("amount", "count", "number", "age", "price", "percent", "quantity", "size", "diameter",
                              "height", "width", "load", "margin", "tip", "people")):
        return "number"
    return "text"


SAMPLE = {"email": "jane.doe@example.com", "password": "Correct7horse!", "number": "12", "text": "sample"}


def fill_action(platform: str, role: str, name: str) -> tuple[str, dict[str, Any]]:
    value = SAMPLE[guess_kind(name)]
    if platform == "web":
        return f"fill[{name}]=sample", {"op": "fill", "role": role, "name": name, "value": value}
    return f"fill[{name}]=sample", {"action": "fill", "role": role, "name": name, "value": value}


def click_action(platform: str, role: str, name: str) -> tuple[str, dict[str, Any]]:
    if platform == "web":
        return f"click[{role}:{name}]", {"op": "click", "role": role, "name": name}
    return f"click[{role}:{name}]", {"action": "click", "role": role, "name": name}


def summarize(symbol: Any) -> dict[str, Any]:
    controls = _controls(symbol)
    return {
        "path": symbol.get("path") if isinstance(symbol, dict) else None,
        "headings": (symbol.get("headings") or [])[:4] if isinstance(symbol, dict) else [],
        "clickable": sorted(k for k, flags in controls.items()
                            if split_control(k)[0] in CLICKABLE and "disabled" not in flags and split_control(k)[1]),
        "disabled": sorted(k for k, flags in controls.items() if "disabled" in flags),
        "fields": sorted(k for k in controls if split_control(k)[0] in FIELDS),
    }


def crawl(open_session: Callable[[], Any], platform: str, *, start: list[tuple[str, dict[str, Any]]] | None = None,
          max_states: int = 25, max_depth: int = 4, max_episodes: int = 200, fill: bool = True,
          describe: Callable[[str], Any]) -> dict[str, Any]:
    """Breadth-first over screens. ``start``: (name, spec) actions that lead to where the crawl begins (e.g. a
    sign-in). Returns {screens: {key: {...summary, via}}, transitions: [...], episodes, truncated}."""
    session = open_session()
    start = list(start or [])
    screens: dict[str, dict[str, Any]] = {}
    transitions: list[dict[str, Any]] = []
    episodes = 0

    def replay(path: list[tuple[str, dict[str, Any]]]) -> tuple[Any, Any] | None:
        nonlocal episodes
        episodes += 1
        session.reset()
        symbol = None
        for name, spec in path:
            _, raw = session.step(name, params=spec)
            symbol = describe(raw)
        return symbol

    try:
        session.reset()
        first = describe(session.observe()[1]) if not start else replay(start)
        key = screen_key(first)
        screens[key] = {**summarize(first), "via": [n for n, _ in start]}
        signatures = {signature(first): key}
        queue = [(key, list(start))]
        truncated = False
        while queue:
            key, path = queue.pop(0)
            if sum(1 for n, _ in path[len(start):] if n.startswith("click[")) >= max_depth:  # depth counts clicks
                continue
            here = path
            if fill and screens[key]["fields"]:  # get past the form: fill every field, then try the controls
                here = [*path, *(fill_action(platform, *split_control(f)) for f in screens[key]["fields"])]
                filled = replay(here)
                if isinstance(filled, dict):  # controls that a filled form enables
                    enabled = summarize(filled)["clickable"]
                    screens[key]["clickable_when_filled"] = sorted(set(enabled) - set(screens[key]["clickable"]))
            for control in sorted(set(screens[key]["clickable"]) | set(screens[key].get("clickable_when_filled", []))):
                if episodes >= max_episodes or len(screens) >= max_states:
                    truncated = True
                    break
                step = click_action(platform, *split_control(control))
                symbol = replay([*here, step])
                if symbol is None or symbol in ("NA", "DISABLED"):
                    continue
                target = screen_key(symbol)
                sig = signature(symbol)
                if target not in screens and sig in signatures:  # same template, other data: explored already
                    screens[signatures[sig]]["instances"] = screens[signatures[sig]].get("instances", 1) + 1
                    target = signatures[sig]
                signatures.setdefault(sig, target)
                network = symbol.get("network", []) if isinstance(symbol, dict) else []
                transitions.append({"from": key, "action": step[0], "to": target, "network": network})
                if target not in screens:
                    screens[target] = {**summarize(symbol), "via": [n for n, _ in [*here, step]]}
                    queue.append((target, [*here, step]))
            if truncated:
                break
    finally:
        session.close()
    actions = {name: spec for s in screens.values()
               for c in [*s["clickable"], *s.get("clickable_when_filled", []), *s["disabled"]]
               if split_control(c)[0] in CLICKABLE
               for name, spec in [click_action(platform, *split_control(c))]}
    actions.update({name: spec for s in screens.values() for f in s["fields"]
                    for name, spec in [fill_action(platform, *split_control(f))]})
    return {"screens": screens, "transitions": transitions, "episodes": episodes, "truncated": truncated,
            "actions": actions}


def as_json(result: dict[str, Any]) -> str:
    return json.dumps(result, indent=1, ensure_ascii=False, sort_keys=True)
