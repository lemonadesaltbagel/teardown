"""Built-in abstractions a mapper version can start from, before its rules run.

``cli.behavior/v1`` turns a CLI observation into its behavior-level form: exit status, stdout bytes (inline when
small, digest otherwise), whether a diagnostic was written and its errno class, and filesystem effects. Diagnostic
*wording* is deliberately dropped: it is expression, and in the CLI spike text normalization recovered only 1.5
points of agreement while behavior-level comparison recovered 20.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from typing import Any

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

ERRNO_TEXT = {
    "No such file or directory": "ENOENT",
    "Permission denied": "EACCES",
    "Is a directory": "EISDIR",
    "Not a directory": "ENOTDIR",
    "No space left on device": "ENOSPC",
    "Broken pipe": "EPIPE",
    "Bad file descriptor": "EBADF",
    "File exists": "EEXIST",
    "Invalid argument": "EINVAL",
    "Read-only file system": "EROFS",
    "Too many open files": "EMFILE",
    "Operation not permitted": "EPERM",
    "Directory not empty": "ENOTEMPTY",
    "Input/output error": "EIO",
    "File too large": "EFBIG",
    "Numerical result out of range": "ERANGE",
}


def _readable(latin1: str) -> str | dict[str, str]:
    """Bytes (carried as latin-1) shown as text when they are valid UTF-8; otherwise kept byte-exact and marked."""
    raw = latin1.encode("latin-1")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return {"bytes_latin1": latin1}


def errno_class(stderr: str) -> str | None:
    """The libc error-string class mentioned in a diagnostic (standard strings, not the tool's own prose)."""
    for text, name in ERRNO_TEXT.items():
        if text.casefold() in stderr.casefold():
            return name
    return None


def cli_behavior(observation: Any, params: dict[str, Any]) -> Any:
    if not isinstance(observation, dict) or "exit" not in observation:
        return observation
    inline = int(params.get("stdout_inline", 4096))
    out: dict[str, Any] = {"exit": observation["exit"]}
    if observation.get("signal") is not None:
        out["signal"] = observation["signal"]
    if observation.get("timed_out"):
        out["timed_out"] = True
    stdout = observation.get("stdout") or ""
    if params.get("strip_ansi", True):
        stdout = _ANSI.sub("", stdout)
    if len(stdout) <= inline:
        out["stdout"] = _readable(stdout)
    else:
        raw = stdout.encode("latin-1", "replace")
        out["stdout"] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    if observation.get("stdout_truncated"):
        out["stdout_truncated"] = True
    stderr = observation.get("stderr") or ""
    out["diagnostic"] = bool(stderr.strip())
    errno = errno_class(stderr)
    if errno:
        out["errno"] = errno
    effects = []
    for change in observation.get("fs") or []:
        effect = {"op": change["op"], "path": change["path"]}
        if change.get("kind") and change["kind"] != "file":
            effect["kind"] = change["kind"]
        if change.get("content") is not None and len(change["content"]) <= inline:
            effect["content"] = _readable(change["content"])
        elif change.get("sha256"):
            effect["sha256"] = change["sha256"]
        effects.append(effect)
    if effects:
        out["fs"] = effects
    return out


BUILTINS: dict[str, Callable[[Any, dict[str, Any]], Any]] = {"cli.behavior/v1": cli_behavior}


# -- web ---------------------------------------------------------------------------------------------------------
_ARIA_LINE = re.compile(r"^(?P<indent>\s*)- (?P<body>.*)$")
_ARIA_ROLE = re.compile(r'^(?P<role>[a-z/][a-zA-Z/]*)(?: "(?P<name>(?:[^"\\]|\\.)*)")?(?P<attrs>(?:\s*\[[^\]]*\])*)'
                        r"(?::\s*(?P<text>.*))?$")
_VALUE_ROLES = {"textbox", "searchbox", "combobox", "spinbutton"}
_CONTROL_ROLES = _VALUE_ROLES | {"button", "checkbox", "radio", "switch", "link", "slider", "tab", "menuitem"}


def _yaml_scalar(text: str) -> str:
    """Unquote a YAML scalar as Playwright writes it ('single' with '' escapes, "double" with backslash
    escapes); anything else is returned as is."""
    t = text.strip()
    if len(t) >= 2 and t[0] == t[-1] == "'":
        return t[1:-1].replace("''", "'")
    if len(t) >= 2 and t[0] == t[-1] == '"':
        try:
            return json.loads(t)
        except ValueError:
            return t[1:-1]
    return t


def parse_aria(snapshot: str, yaml_strings: bool = False) -> list[dict[str, Any]]:
    """``yaml_strings`` (web.aria/v2): undo Playwright's YAML quoting. An entry whose name holds ``#``, ``:`` or
    quotes is written as one single-quoted scalar, and quoted text values keep their quotes otherwise."""
    nodes = []
    for raw in snapshot.splitlines():
        m = _ARIA_LINE.match(raw)
        if not m:
            continue
        body = m.group("body")
        if yaml_strings:
            body = body.rstrip()
            colon = body.endswith(":") and body.startswith("'") and body[:-1].endswith("'")
            if body.startswith("'") and (body.endswith("'") or colon):
                body = _yaml_scalar(body[:-1] if colon else body)
        body = body.rstrip(":")
        r = _ARIA_ROLE.match(body)
        if not r:
            depth = len(m.group("indent")) // 2
            nodes.append({"depth": depth, "role": "text", "name": None, "attrs": [], "text": body})
            continue
        attrs = re.findall(r"\[([^\]]*)\]", r.group("attrs") or "")
        name, text = r.group("name"), r.group("text")
        if yaml_strings:
            name = json.loads(f'"{name}"') if name is not None else None  # names use JSON-style escapes
            text = _yaml_scalar(text) if text is not None else None
        nodes.append({"depth": len(m.group("indent")) // 2, "role": r.group("role"), "name": name,
                      "attrs": attrs, "text": text})
    return nodes


_MONTHS = ("January|February|March|April|May|June|July|August|September|October|November|December|"
           "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec")
CALENDAR_DATE = re.compile(rf"\b(?:(?:{_MONTHS})\.? \d{{1,2}}(?:st|nd|rd|th)?,? \d{{4}}"
                           rf"|\d{{1,2}} (?:{_MONTHS})\.? \d{{4}}"
                           r"|\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?Z?)?)\b")


_TABLE_ROLES = {"cell", "gridcell", "rowheader", "columnheader"}
# v10 with mask_dates: times of day ("UTC Timezone (14:03:27)" would otherwise be a new control every second) and
# relative times ("3 seconds ago", "just now", "in 5 minutes")
TIME_OF_DAY = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?(?:\s?[AaPp][Mm])?\b")
# and numeric dates ("10/26/2026", "26.10.2026"; not versions like "1.6.10"). Older versions keep their symbols,
# so only v10 masks these.
NUMERIC_DATE = re.compile(r"(?<![\d./])(?:\d{1,2}/\d{1,2}/(?:\d{4}|\d{2})|\d{1,2}\.\d{1,2}\.\d{4})"
                          r"(?![\d./]*\d)")
RELATIVE_TIME = re.compile(r"\b(?:(?:\d+|an?|a few)\s+(?:second|minute|hour|day|week|month|year)s?\s+ago|just now|"
                           r"in\s+(?:\d+|an?|a few)\s+(?:second|minute|hour|day|week|month|year)s?)\b", re.IGNORECASE)


def web_aria(observation: Any, params: dict[str, Any], version: int = 1) -> Any:
    """Structured, wording-agnostic view of an accessibility snapshot.

    Output keys: ``path`` (URL path), ``headings`` (h1-h2 names), ``alerts`` (alert texts), ``text`` (other
    visible text), ``network`` (API exchanges since the last observation: method, path template, status),
    ``controls`` (role:name -> state flags; textbox values reduced to
    filled/empty so secrets never reach symbols), ``invalid`` (form controls failing constraint validation) and
    ``contract`` (state of each selector named by a public markup contract, when the target supplies one).
    ``mask_dates`` (param) replaces calendar dates in headings, alerts and text with ``<date>``: dates shown from a
    server clock (creation times) drift between observation and verification.
    Mapper rules then classify the remaining text into semantic classes.
    """
    if not isinstance(observation, dict) or "aria" not in observation:
        return observation
    # v1 dropped live regions (role=status) as noise; v2 keeps them: flash and confirmation messages are behavior
    drop_roles = set(params.get("drop_roles", ["status"] if version < 2 else []))
    out: dict[str, Any] = {"path": observation.get("path", "/"), "headings": [], "alerts": [], "text": [],
                           "controls": {}}
    skip_depth = None
    combobox = None  # v2: options belong to the combobox above them
    table: dict[str, Any] | None = None  # v3: the table being read, with its depth
    term: str | None = None  # v3: a term waiting for its definition
    groups: list[tuple[int, str]] = []  # v7: named groups open around the current node
    outline: list[str] = []  # v8: the whole tree, field values left out
    for n in parse_aria(observation["aria"], yaml_strings=version >= 2):
        if skip_depth is not None and n["depth"] > skip_depth:
            continue
        skip_depth = None
        role = n["role"]
        if version >= 8 and role != "/url":  # link targets are not part of what a user-facing test reads
            line = "  " * n["depth"] + role + (f' "{n["name"]}"' if n["name"] is not None else "")
            line += "".join(f" [{a}]" for a in n["attrs"])
            if n["text"] and role not in _VALUE_ROLES:  # values (secrets among them) come from `properties`
                line += f": {n['text'].strip()}"
            outline.append(line)
        if version >= 7:
            while groups and n["depth"] <= groups[-1][0]:
                groups.pop()
            if role in ("group", "radiogroup", "toolbar") and n["name"]:
                key = f"{role}:{n['name']}"
                out.setdefault("groups", {}).setdefault(key, [])
                groups.append((n["depth"], key))
        if version >= 3:  # structure: tables (columns and rows of cells) and description lists
            if table is not None and n["depth"] <= table["depth"]:
                table = None
            if role == "table":
                name = n["name"] or f"table {len(out.setdefault('tables', {})) + 1}"
                out.setdefault("tables", {})[name] = {"columns": [], "rows": []}
                table = {"depth": n["depth"], "data": out["tables"][name]}
                continue
            if table is not None:
                if role == "row":
                    table["data"]["rows"].append([])
                    continue
                if role == "columnheader":
                    table["data"]["columns"].append((n["name"] or n["text"] or "").strip())
                    if table["data"]["rows"] and not table["data"]["rows"][-1]:
                        table["data"]["rows"].pop()  # the header row is not a data row
                    continue
                if role in ("cell", "gridcell", "rowheader"):
                    if not table["data"]["rows"]:
                        table["data"]["rows"].append([])
                    table["data"]["rows"][-1].append((n["name"] or n["text"] or "").strip())
                    if version >= 7 and role == "rowheader":  # v7: which cells head their row
                        table["data"].setdefault("row_headers", []).append(table["data"]["rows"][-1][-1])
                    continue
            if role == "term":
                term = (n["name"] or n["text"] or "").strip()
                continue
            if role == "definition":
                out.setdefault("definitions", []).append([term or "", (n["name"] or n["text"] or "").strip()])
                term = None
                continue
        if role in drop_roles:
            skip_depth = n["depth"]
            continue
        if version >= 2 and role == "status":
            if (n["name"] or n["text"] or "").strip():
                out.setdefault("status", []).append((n["name"] or n["text"]).strip())
            continue
        if version >= 2 and role in ("dialog", "alertdialog"):
            # v6 keeps the role: an alertdialog (a confirmation) is not a dialog
            out.setdefault("dialogs", []).append(f"{role}:{n['name'] or ''}" if version >= 6 else n["name"] or "")
        if version >= 2 and role == "option" and n["name"] is not None and combobox is not None:
            out.setdefault("options", {}).setdefault(combobox, []).append(
                n["name"] + (" [selected]" if "selected" in n["attrs"] else ""))
            continue
        if version >= 2 and role == "combobox":
            combobox = f"combobox:{n['name'] or ''}"
        if role == "heading" and any(a in ("level=1", "level=2") for a in n["attrs"]):
            out["headings"].append(n["name"] or n["text"] or "")
        elif role == "alert":
            out["alerts"].append(n["name"] or n["text"] or "")
        elif role in ("paragraph", "text", "strong", "emphasis", "listitem") and (n["text"] or "").strip():
            out["text"].append(n["text"].strip())
        elif version == 2 and role in _TABLE_ROLES and (n["name"] or n["text"] or "").strip():
            out["text"].append((n["name"] or n["text"]).strip())  # table contents are shown values
        elif role in _CONTROL_ROLES:
            flags = sorted(a for a in n["attrs"] if a in ("checked", "disabled", "expanded", "pressed", "selected"))
            if role in _VALUE_ROLES:
                flags.append("filled" if (n["text"] or "").strip() else "empty")
            out["controls"][f"{role}:{n['name'] or ''}"] = flags
            for _, group in groups:
                out["groups"][group].append(f"{role}:{n['name'] or ''}")
    invalid = sorted(f["name"] for f in observation.get("form", []) if not f.get("valid", True))
    if invalid:
        out["invalid"] = invalid
    if observation.get("network"):
        out["network"] = [f"{m} {p} {s}" for m, p, s in observation["network"]]
    if observation.get("contract"):  # public-contract selectors: absent | hidden | empty | content
        out["contract"] = dict(sorted(observation["contract"].items()))
    if version >= 4 and observation.get("landmarks"):  # landmark text as text assertions read it
        out["landmarks"] = dict(sorted(observation["landmarks"].items()))
    if version >= 5 and observation.get("generated"):  # CSS-inserted text: "before|element text|after"
        out["generated"] = list(observation["generated"])
    if version >= 8:
        if outline:
            out["outline"] = outline
        if observation.get("properties"):
            out["properties"] = dict(sorted(observation["properties"].items()))
    if version >= 6 and observation.get("descriptions"):  # aria-describedby / aria-description per control
        out["descriptions"] = dict(sorted(observation["descriptions"].items()))
    if version >= 2:  # what the accessibility snapshot leaves out
        if observation.get("title"):
            out["title"] = observation["title"]
        if version >= 9 and "focus_named" in observation:  # v9: headings and landmarks named too
            if observation["focus_named"]:
                out["focus"] = observation["focus_named"]
        elif observation.get("focus"):
            out["focus"] = observation["focus"]
        for marked in observation.get("current") or []:
            if marked in out["controls"] and "current" not in out["controls"][marked]:
                out["controls"][marked] = sorted([*out["controls"][marked], "current"])
    if version >= 7:  # aria-invalid: a control flag; marked elements that are not controls are listed
        for marked in observation.get("flagged") or []:
            if marked in out["controls"]:
                if "invalid" not in out["controls"][marked]:
                    out["controls"][marked] = sorted([*out["controls"][marked], "invalid"])
            else:
                out.setdefault("flagged", []).append(marked)
    if version >= 10 and observation.get("fragment", "").startswith(("/", "!/")):  # a hash route is the route
        out["path"] = f"{out['path']}#{observation['fragment']}"
    patterns = [re.compile(p) for p in params.get("mask_patterns") or []] if version >= 10 else []
    if version >= 10 and (params.get("mask_dates") or patterns):
        def clock(t: str) -> str:
            if params.get("mask_dates"):  # dates first: an ISO timestamp is one date, not a date and a time
                t = NUMERIC_DATE.sub("<date>", CALENDAR_DATE.sub("<date>", t))
                t = RELATIVE_TIME.sub("<ago>", TIME_OF_DAY.sub("<time>", t))
            for pattern in patterns:  # the observer's own (a one-time token, an id shown in text)
                t = pattern.sub("<masked>", t)
            return t

        out["controls"] = {clock(k): v for k, v in out["controls"].items()}
        for key in ("headings", "alerts", "text", "status", "outline"):
            if key in out:
                out[key] = [clock(t) for t in out[key]]
        if "options" in out:
            out["options"] = {clock(k): [clock(o) for o in v] for k, v in out["options"].items()}
        if "landmarks" in out:
            out["landmarks"] = {k: clock(v) for k, v in out["landmarks"].items()}
        for data in out.get("tables", {}).values():
            data["rows"] = [[clock(c) for c in row] for row in data["rows"]]
        if "properties" in out:  # keyed by control name; a title or value can carry the clock too
            out["properties"] = {clock(k): {p: clock(v) if isinstance(v, str) else v for p, v in props.items()}
                                 for k, props in out["properties"].items()}
        if isinstance(out.get("focus"), str):
            out["focus"] = clock(out["focus"])
        if "flagged" in out:
            out["flagged"] = [clock(t) for t in out["flagged"]]
    if params.get("mask_dates"):
        def date(t: str) -> str:
            t = CALENDAR_DATE.sub("<date>", t)
            return NUMERIC_DATE.sub("<date>", t) if version >= 10 else t

        for key in ("headings", "alerts", "text", "status"):
            if key in out:
                out[key] = [date(t) for t in out[key]]
        for data in out.get("tables", {}).values():
            data["rows"] = [[date(c) for c in row] for row in data["rows"]]
            if "row_headers" in data:
                data["row_headers"] = [date(c) for c in data["row_headers"]]
        if "definitions" in out:
            out["definitions"] = [[t, date(d)] for t, d in out["definitions"]]
        if "landmarks" in out:
            out["landmarks"] = {k: date(v) for k, v in out["landmarks"].items()}
        if "outline" in out:
            out["outline"] = [date(line) for line in out["outline"]]
        for props in out.get("properties", {}).values():
            if isinstance(props.get("value"), str):
                props["value"] = date(props["value"])
    for key in ("alerts", "text"):
        if not out[key]:
            out.pop(key)
    return out


BUILTINS["web.aria/v1"] = web_aria
# v2: Playwright's YAML quoting undone (names with '#', ':' or quotes), table cells and headers in `text`.
# v1 stays as it was so that specs released under it keep verifying against their recorded symbols.
BUILTINS["web.aria/v2"] = lambda observation, params: web_aria(observation, params, version=2)
# v3: structure. Tables become {name: {columns, rows}} (cells no longer in `text`); description lists become
# `definitions` ([term, definition] pairs). v2 stays as it was for specs released under it.
BUILTINS["web.aria/v3"] = lambda observation, params: web_aria(observation, params, version=3)
# v4: `landmarks` — banner, contentinfo, navigation, complementary, search and named regions/forms, each with its
# text as text assertions read it (whitespace-collapsed textContent: inline joins kept, block splits visible).
BUILTINS["web.aria/v4"] = lambda observation, params: web_aria(observation, params, version=4)
# v5: `generated` — text CSS inserts with ::before/::after (icons, separators), which accessible names include
# and element text does not; a clone writing it literally into the DOM differs from one generating it.
BUILTINS["web.aria/v5"] = lambda observation, params: web_aria(observation, params, version=5)
# v6: dialogs carry their role ("alertdialog:Remove HB-102?"), and `descriptions` gives each control's accessible
# description (aria-describedby / aria-description).
BUILTINS["web.aria/v6"] = lambda observation, params: web_aria(observation, params, version=6)
# v7: `invalid` control flag for fields the app marks with aria-invalid (the browser's own constraint validation
# stays in the `invalid` key); tables list their `row_headers`; `groups` maps each named group, radiogroup or
# toolbar to the controls inside it.
BUILTINS["web.aria/v7"] = lambda observation, params: web_aria(observation, params, version=7)
# v8: the user-facing Playwright surface (`teardown.drivers.web.surface`). `outline` is the accessibility tree
# (roles, names, levels, states, nesting, counts; field values left out), and `properties` holds what the tree
# reduces or omits: field values (never a password's), required, readonly, masked, error message, sort state,
# progress values and title attributes.
BUILTINS["web.aria/v8"] = lambda observation, params: web_aria(observation, params, version=8)
# v9: `focus` names whatever has focus by role and name, headings and landmarks included ("heading:Programme");
# v8 recorded a focused heading as its bare tag ("h2:").
BUILTINS["web.aria/v9"] = lambda observation, params: web_aria(observation, params, version=9)
# v10: hash-routed apps record their route in `path` ("/#/namespaces/default/flags"); with mask_dates, times of day
# and relative times ("3 seconds ago") are masked too, in control names, options and the outline as well.
BUILTINS["web.aria/v10"] = lambda observation, params: web_aria(observation, params, version=10)


# -- desktop -----------------------------------------------------------------------------------------------------
_DESK_VALUE_ROLES = {"text", "entry", "password text", "spin button", "combo box"}
_DESK_CONTROL_ROLES = _DESK_VALUE_ROLES | {"push button", "button", "toggle button", "check box", "radio button",
                                          "menu item", "check menu item", "radio menu item", "link", "slider",
                                          "page tab"}


def desktop_a11y(observation: Any, params: dict[str, Any]) -> Any:
    """Structured view of an AT-SPI tree: window titles, dialogs, control states, visible text, list items."""
    if not isinstance(observation, dict) or "tree" not in observation:
        return observation
    out: dict[str, Any] = {"windows": [], "controls": {}, "text": [], "items": []}
    item_depth = None  # labels nested under a list item / table cell are that item's text
    for n in observation["tree"]:
        role, name, states = n["role"], n.get("name") or "", n.get("states", [])
        if item_depth is not None and n["depth"] <= item_depth:
            item_depth = None
        if role in ("list item", "table cell") and not name.strip():
            item_depth = n["depth"]
            continue
        if item_depth is not None and role == "label" and name.strip():
            out["items"].append(name.strip())
            continue
        if role in ("frame", "window", "dialog", "alert"):
            out["windows"].append(f"{role}:{name}" + (":modal" if "modal" in states else ""))
        elif role in _DESK_CONTROL_ROLES:
            flags = sorted(s for s in states if s in ("checked", "selected", "expanded", "focused"))
            if "sensitive" not in states and "enabled" not in states:
                flags.append("disabled")
            if role in _DESK_VALUE_ROLES:
                flags.append("filled" if (n.get("text") or "").strip() else "empty")
            out["controls"][f"{role}:{name}"] = sorted(flags)
        elif role == "label" and name.strip():
            out["text"].append(name.strip())
        elif role in ("list item", "table cell") and name.strip():
            out["items"].append(name.strip())
    for key in ("text", "items"):
        if not out[key]:
            out.pop(key)
    return out


BUILTINS["desktop.a11y/v1"] = desktop_a11y


# -- android -----------------------------------------------------------------------------------------------------
_AND_CONTROL_ROLES = {"button", "textbox", "checkbox", "switch", "radio", "togglebutton", "combobox", "slider"}


def android_a11y(observation: Any, params: dict[str, Any]) -> Any:
    """Structured view of an Android accessibility dump: controls (role:name -> flags), visible text, dialogs."""
    if not isinstance(observation, dict) or "nodes" not in observation:
        return observation
    out: dict[str, Any] = {"controls": {}, "text": []}
    for n in observation["nodes"]:
        role, name = n["role"], (n.get("desc") or n.get("text") or "").strip()
        if n.get("package") == "android":  # system UI (permission dialogs, ANR/crash dialogs) is behavior too
            out.setdefault("system", []).append(f"{role}:{name}")
            continue
        if role in _AND_CONTROL_ROLES:
            label = (n.get("desc") or "").strip() if role == "textbox" else name
            flags = [f for f in ("checked", "selected", "focused") if n.get(f)]
            if not n.get("enabled", True):
                flags.append("disabled")
            if role == "textbox":
                # uiautomator reports an empty field's hint as its text; the hint usually equals the field's
                # content description, so text == description counts as empty (heuristic, see driver docs).
                text = (n.get("text") or "").strip()
                if n.get("showing_hint") is not None:  # on-device agent: exact
                    empty = n["showing_hint"] or not text
                else:
                    empty = not text or text == (n.get("desc") or "").strip()
                flags.append("empty" if empty else "filled")
            out["controls"][f"{role}:{label}"] = sorted(flags)
        elif role == "text" and name:
            out["text"].append(name)
    if not out["text"]:
        out.pop("text")
    return out


BUILTINS["android.a11y/v1"] = android_a11y

_AND_INPUT_METHOD = 2  # AccessibilityWindowInfo.TYPE_INPUT_METHOD: the keyboard is not the app's UI
_AND_APPLICATION = 1


def android_a11y_v2(observation: Any, params: dict[str, Any], version: int = 2) -> Any:
    """v2: the user-facing Espresso/UiAutomator surface (``teardown.drivers.android.surface``).

    Keeps v1's ``controls``, ``text`` and ``system``, and adds:

    - ``outline``: every meaningful node in screen order (controls, text, described images, progress bars), with
      its state flags; no layout depth, so wrappers do not matter but counts and order do;
    - ``properties``: role:name -> value (never a password's), hint, error, masked, range, heading, state;
    - ``dialogs``: nodes in an application window above the page (an AlertDialog), titled by the window or its
      first text. The keyboard's window is left out.
    """
    if not isinstance(observation, dict) or "nodes" not in observation:
        return observation
    base = android_a11y({"nodes": [n for n in observation["nodes"] if n.get("wtype") != _AND_INPUT_METHOD]}, params)
    app = [n for n in observation["nodes"] if n.get("wtype", _AND_APPLICATION) == _AND_APPLICATION
           and n.get("package") not in ("android", "")]
    page_layer = min((n.get("wlayer", 0) for n in app), default=0)
    outline: list[str] = []
    properties: dict[str, dict[str, Any]] = {}
    dialogs: dict[int, list[str]] = {}
    for n in app:
        role = n["role"]
        name = ((n.get("desc") or "").strip() if role == "textbox" else
                (n.get("desc") or n.get("text") or "").strip())
        meaningful = role in _AND_CONTROL_ROLES or (role == "text" and name) or (
            role in ("image", "progressbar") and name) or n.get("heading") or n.get("state") or n.get("range")
        if not meaningful:
            continue
        flags = [f for f in ("checked", "selected", "focused", "heading") if n.get(f)]
        if not n.get("enabled", True):
            flags.append("disabled")
        in_dialog = n.get("wlayer", 0) > page_layer
        key = f"{role}:{name}"
        outline.append(key + "".join(f" [{f}]" for f in sorted(flags)) + (" [dialog]" if in_dialog else ""))
        if in_dialog:
            dialogs.setdefault(n.get("window", 0), [n.get("wtitle") or ""]).append(key)
        props: dict[str, Any] = {}
        if role == "textbox":
            text = (n.get("text") or "").strip()
            if n.get("password"):
                props["masked"] = True
            elif text and not n.get("showing_hint"):
                props["value"] = text
            # an empty field reports its hint as its text (showing_hint); a filled one through getHintText
            hint = (n.get("hint") or "").strip() or (text if n.get("showing_hint") else "")
            if hint:
                props["hint"] = hint
        if version >= 3 and role in _AND_CONTROL_ROLES and role != "textbox":
            text, desc = (n.get("text") or "").strip(), (n.get("desc") or "").strip()
            if text and desc and text != desc:  # named by its description, showing other text (withText sees it)
                props["text"] = text
        if n.get("error"):
            props["error"] = n["error"]
        if n.get("state"):
            props["state"] = n["state"]
        if n.get("range"):
            props["range"] = n["range"]
        if props:
            properties.setdefault(key, props)
    out = dict(base)
    if version >= 3 and (observation.get("keyboard") or
                         any(n.get("wtype") == _AND_INPUT_METHOD for n in observation["nodes"])):
        out["keyboard"] = "shown"  # the soft keyboard is up: the next Back closes it rather than the screen
    if outline:
        out["outline"] = outline
    if properties:
        out["properties"] = dict(sorted(properties.items()))
    if dialogs:
        out["dialogs"] = [f"dialog:{title or next((k.split(':', 1)[1] for k in keys if k.startswith('text:')), '')}"
                          for title, *keys in dialogs.values()]
    return out


BUILTINS["android.a11y/v2"] = android_a11y_v2
# v3: a control named by its content description but showing other text ("Open" described as "Open North") records
# that text in `properties`, since Espresso's withText and UiAutomator's By.text match it; `keyboard: shown` when the
# soft keyboard is up (it takes the next Back press, so it changes what Back does).
BUILTINS["android.a11y/v3"] = lambda observation, params: android_a11y_v2(observation, params, version=3)


# Top-level keys each built-in abstraction can produce (some are omitted when empty). Rule checks that name other
# keys would compare nothing; see ``unknown_keys``.
KNOWN_KEYS = {
    "cli.behavior/v1": {"exit", "signal", "timed_out", "stdout", "stdout_truncated", "diagnostic", "errno", "fs"},
    "web.aria/v1": {"path", "headings", "alerts", "text", "controls", "invalid", "network", "contract"},
    "web.aria/v2": {"path", "headings", "alerts", "text", "controls", "invalid", "network", "contract", "title",
                    "focus", "status", "dialogs", "options"},
    "web.aria/v3": {"path", "headings", "alerts", "text", "controls", "invalid", "network", "contract", "title",
                    "focus", "status", "dialogs", "options", "tables", "definitions"},
    "web.aria/v4": {"path", "headings", "alerts", "text", "controls", "invalid", "network", "contract", "title",
                    "focus", "status", "dialogs", "options", "tables", "definitions", "landmarks"},
    "web.aria/v5": {"path", "headings", "alerts", "text", "controls", "invalid", "network", "contract", "title",
                    "focus", "status", "dialogs", "options", "tables", "definitions", "landmarks", "generated"},
    "web.aria/v6": {"path", "headings", "alerts", "text", "controls", "invalid", "network", "contract", "title",
                    "focus", "status", "dialogs", "options", "tables", "definitions", "landmarks", "generated",
                    "descriptions"},
    "web.aria/v7": {"path", "headings", "alerts", "text", "controls", "invalid", "network", "contract", "title",
                    "focus", "status", "dialogs", "options", "tables", "definitions", "landmarks", "generated",
                    "descriptions", "groups", "flagged"},
    "web.aria/v8": {"path", "headings", "alerts", "text", "controls", "invalid", "network", "contract", "title",
                    "focus", "status", "dialogs", "options", "tables", "definitions", "landmarks", "generated",
                    "descriptions", "groups", "flagged", "outline", "properties"},
    "web.aria/v9": {"path", "headings", "alerts", "text", "controls", "invalid", "network", "contract", "title",
                    "focus", "status", "dialogs", "options", "tables", "definitions", "landmarks", "generated",
                    "descriptions", "groups", "flagged", "outline", "properties"},
    "web.aria/v10": {"path", "headings", "alerts", "text", "controls", "invalid", "network", "contract", "title",
                     "focus", "status", "dialogs", "options", "tables", "definitions", "landmarks", "generated",
                     "descriptions", "groups", "flagged", "outline", "properties"},
    "desktop.a11y/v1": {"windows", "controls", "text", "items"},
    "android.a11y/v1": {"controls", "text", "system"},
    "android.a11y/v2": {"controls", "text", "system", "outline", "properties", "dialogs"},
    "android.a11y/v3": {"controls", "text", "system", "outline", "properties", "dialogs", "keyboard"},
}
