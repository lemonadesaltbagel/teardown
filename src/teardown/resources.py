"""Where Teardown's non-Python files and its local state live.

Running from a source checkout, both are the checkout: room images build from the repository, and verification
links go under its `.teardown/`. Installed from a wheel, the package carries the room files (`_room/`). The same
build context is assembled once per version under the user's Teardown directory (`TEARDOWN_HOME`, default
`~/.teardown`), so the unchanged Dockerfiles and compose files work from an installed copy too.
"""

from __future__ import annotations

import os
import shutil
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
CHECKOUT = PACKAGE.parents[1]


def in_checkout() -> bool:
    return (CHECKOUT / "pyproject.toml").is_file() and (CHECKOUT / "deploy" / "cleanroom.yaml").is_file() \
        and (CHECKOUT / "src" / "teardown").is_dir()


def state_dir() -> Path:
    """Local runtime state (verification links, assembled room contexts)."""
    if in_checkout():
        return CHECKOUT / ".teardown"
    return Path(os.environ.get("TEARDOWN_HOME") or Path.home() / ".teardown")


def room_root() -> Path:
    """The build context of the room images: the checkout, or one assembled from the installed package."""
    if in_checkout():
        return CHECKOUT
    try:
        current = version("teardown")
    except PackageNotFoundError:  # pragma: no cover - an unpackaged, non-checkout copy
        current = "local"
    root = state_dir() / "room" / current
    if (root / ".complete").exists():
        return root
    shipped = PACKAGE / "_room"
    if not shipped.is_dir():
        raise FileNotFoundError("this Teardown installation does not include the room files (teardown/_room)")
    tmp = root.with_name(root.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(shipped, tmp)  # pyproject.toml, README.md, LICENSE, NOTICE, deploy/
    shutil.copytree(PACKAGE, tmp / "src" / "teardown",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "_room", "observer-playbook.md"))
    (tmp / "docs").mkdir(exist_ok=True)
    shutil.copy2(PACKAGE / "observer-playbook.md", tmp / "docs" / "observer-playbook.md")
    (tmp / ".complete").write_text(current, encoding="utf-8")
    shutil.rmtree(root, ignore_errors=True)
    tmp.rename(root)
    return root
