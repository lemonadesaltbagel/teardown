"""Desktop driver (Linux backend): an X11/AT-SPI session inside a locked-down container.

Target spec::

    desktop:docker:<image>       target_options: {"app": [argv], "mount": "<host dir>:<container dir>"}

The container runs Teardown's desktop agent (``deploy/desktop-linux``): Xvfb, D-Bus and the AT-SPI registry, with
the app launched under a fresh $HOME on every reset. Actions address elements by accessibility role and name;
observations are accessibility-tree snapshots. No network, read-only image, unprivileged user.

macOS (AX) and Windows (UIA) backends speak the same action/observation shapes (ROADMAP Phase 5).
"""

from __future__ import annotations

import json
import selectors
import subprocess
import time
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from teardown.core.ids import content_id
from teardown.drivers.base import Action, Driver, DriverCapabilities


class DesktopAction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action: Literal["click", "fill", "toggle", "key"]
    role: str | None = None
    name: str | None = None
    value: str | None = None


class DesktopDriver(Driver):
    name = "desktop"

    def __init__(self, target_spec: str, actions: dict[str, DesktopAction] | None = None,
                 options: dict[str, Any] | None = None):
        self.image = target_spec.removeprefix("desktop:docker:")
        self.table = dict(actions or {})
        self.options = dict(options or {})
        if not self.options.get("app"):
            raise ValueError("desktop targets need target_options['app'] (the app's argv inside the container)")
        self._proc: subprocess.Popen | None = None
        self._buffer = b""

    def target_fingerprint(self) -> str:
        image_id = subprocess.run(["docker", "image", "inspect", "-f", "{{.Id}}", self.image],
                                  capture_output=True, text=True).stdout.strip()
        return content_id("tgt", {"platform": "desktop-linux", "image": self.image, "image_id": image_id,
                                  "app": self.options.get("app")})

    def capabilities(self) -> DriverCapabilities:
        return DriverCapabilities(platform="desktop", reset_cost_ms=600.0, soft_reset=True, parallelism=4)

    # -- container session -------------------------------------------------------------------------------------
    def _start(self) -> None:
        cmd = ["docker", "run", "-i", "--rm", "--name", f"teardown-desk-{uuid.uuid4().hex[:8]}", "--network", "none",
               "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "1g", "--pids-limit", "512"]
        if self.options.get("mount"):
            cmd += ["-v", f"{self.options['mount']}:ro"]
        cmd.append(self.image)
        self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self._buffer = b""
        hello = self._read(30)
        if not hello or not hello.get("ready"):
            raise RuntimeError("desktop agent did not start")

    def _read(self, timeout: float) -> dict | None:
        assert self._proc and self._proc.stdout
        sel = selectors.DefaultSelector()
        sel.register(self._proc.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + timeout
        try:
            while b"\n" not in self._buffer:
                left = deadline - time.monotonic()
                if left <= 0 or not sel.select(left):
                    return None
                chunk = self._proc.stdout.read1(1 << 20)
                if not chunk:
                    return None
                self._buffer += chunk
        finally:
            sel.close()
        line, _, self._buffer = self._buffer.partition(b"\n")
        return json.loads(line)

    def _call(self, cmd: dict, timeout: float = 30) -> dict:
        if self._proc is None or self._proc.poll() is not None:
            self._start()
        assert self._proc and self._proc.stdin
        self._proc.stdin.write((json.dumps(cmd) + "\n").encode())
        self._proc.stdin.flush()
        reply = self._read(timeout)
        if reply is None:
            self.close()
            raise RuntimeError(f"desktop agent did not answer {cmd.get('op')}")
        return reply

    # -- driver contract ---------------------------------------------------------------------------------------
    def reset(self) -> Any:
        reply = self._call({"op": "reset", "app": self.options["app"]}, timeout=40)
        if not reply.get("ok"):
            raise RuntimeError(f"app did not start: {reply}")
        return self.observe()

    def step(self, action: Action) -> Any | None:
        spec = DesktopAction.model_validate(action.params) if action.params else self.table.get(action.name)
        if spec is None:
            return None
        reply = self._call({"op": "act", **spec.model_dump(exclude_none=True)})
        if not reply.get("ok"):
            if reply.get("reason") == "absent":
                return None
            if reply.get("reason") == "disabled":
                return "DISABLED"
            raise RuntimeError(f"desktop action failed: {reply}")
        return self.observe()

    def observe(self) -> Any:
        reply = self._call({"op": "observe"})
        if not reply.get("ok"):
            return {"exited": True, "exit": reply.get("exit")}
        return {"tree": reply["tree"]}

    def actions(self) -> list[str]:
        return sorted(self.table)

    def close(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.stdin.write(b'{"op": "quit"}\n')
                self._proc.stdin.flush()
                self._proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                self._proc.kill()
        self._proc = None
