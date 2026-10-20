"""Built-in abstractions a mapper version can start from, before its rules run.

``cli.behavior/v1`` turns a CLI observation into its behavior-level form: exit status, stdout bytes (inline when
small, digest otherwise), whether a diagnostic was written and its errno class, and filesystem effects. Diagnostic
*wording* is deliberately dropped: it is expression, and in the CLI spike text normalization recovered only 1.5
points of agreement while behavior-level comparison recovered 20.
"""

from __future__ import annotations

import hashlib
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


def parse_aria(snapshot: str) -> list[dict[str, Any]]:
    nodes = []
    for raw in snapshot.splitlines():
        m = _ARIA_LINE.match(raw)
        if not m:
            continue
        body = m.group("body").rstrip(":")
        r = _ARIA_ROLE.match(body)
        if not r:
            depth = len(m.group("indent")) // 2
            nodes.append({"depth": depth, "role": "text", "name": None, "attrs": [], "text": body})
            continue
        attrs = re.findall(r"\[([^\]]*)\]", r.group("attrs") or "")
        nodes.append({"depth": len(m.group("indent")) // 2, "role": r.group("role"), "name": r.group("name"),
                      "attrs": attrs, "text": r.group("text")})
    return nodes


def web_aria(observation: Any, params: dict[str, Any]) -> Any:
    """Structured, wording-agnostic view of an accessibility snapshot.

    Output keys: ``path`` (URL path), ``headings`` (h1-h2 names), ``alerts`` (alert texts), ``text`` (other
    visible text), ``controls`` (role:name -> state flags; textbox values reduced to
    filled/empty so secrets never reach symbols) and ``invalid`` (form controls failing constraint validation).
    Mapper rules then classify the remaining text into semantic classes.
    """
    if not isinstance(observation, dict) or "aria" not in observation:
        return observation
    drop_roles = set(params.get("drop_roles", ["status"]))
    out: dict[str, Any] = {"path": observation.get("path", "/"), "headings": [], "alerts": [], "text": [],
                           "controls": {}}
    skip_depth = None
    for n in parse_aria(observation["aria"]):
        if skip_depth is not None and n["depth"] > skip_depth:
            continue
        skip_depth = None
        role = n["role"]
        if role in drop_roles:
            skip_depth = n["depth"]
            continue
        if role == "heading" and any(a in ("level=1", "level=2") for a in n["attrs"]):
            out["headings"].append(n["name"] or n["text"] or "")
        elif role == "alert":
            out["alerts"].append(n["name"] or n["text"] or "")
        elif role in ("paragraph", "text", "strong", "emphasis", "listitem") and (n["text"] or "").strip():
            out["text"].append(n["text"].strip())
        elif role in _CONTROL_ROLES:
            flags = sorted(a for a in n["attrs"] if a in ("checked", "disabled", "expanded", "pressed", "selected"))
            if role in _VALUE_ROLES:
                flags.append("filled" if (n["text"] or "").strip() else "empty")
            out["controls"][f"{role}:{n['name'] or ''}"] = flags
    invalid = sorted(f["name"] for f in observation.get("form", []) if not f.get("valid", True))
    if invalid:
        out["invalid"] = invalid
    for key in ("alerts", "text"):
        if not out[key]:
            out.pop(key)
    return out


BUILTINS["web.aria/v1"] = web_aria
