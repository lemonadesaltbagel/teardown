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
