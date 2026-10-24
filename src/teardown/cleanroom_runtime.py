"""Enforced rooms on one machine: the clean room and the observer room.

Both follow one pattern. A Teardown server runs on the host and holds the privileges: the gate (`gate-serve --kit`)
for the clean room, or the observe MCP server over HTTP for the observer room. An agent container sees one
directory and an internal network whose only peer is an egress proxy. The proxy forwards to an explicit allowlist
(that server, the model API, and for the clean room an API the kit names) and logs every attempt.

- **clean room**: the implementer sees only the kit; the gate verifies clones built from it.
- **observer room**: the observer sees only its scratch workspace; it observes the target exclusively through the
  observe MCP tools (drivers run on the host), so it cannot read the target's source, bundles or files.

State lives in ``<project>/.cleanroom/`` or ``<project>/.observerroom/`` (dirty side: tokens never enter the
mounted directory).
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from teardown.resources import PACKAGE, in_checkout, room_root

# what the rooms must not see: the checkout (target sources, references) or, installed, the package itself
REPO = Path(__file__).resolve().parents[2] if in_checkout() else PACKAGE
HOST_ALIAS = "host.docker.internal"
MODEL_API = "api.anthropic.com:443"
ROOMS = {
    "clean": {"compose": "cleanroom.yaml", "dir": ".cleanroom", "service": "clean",
              "mount": "/kit", "cmd": "teardown cleanroom up"},
    "observer": {"compose": "observerroom.yaml", "dir": ".observerroom", "service": "observer",
                 "mount": "/work", "cmd": "teardown observerroom up"},
}


def _dir(project: Path, room: str) -> Path:
    d = project / ROOMS[room]["dir"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load(project: Path, room: str) -> dict[str, Any]:
    path = _dir(project, room) / "state.json"
    if not path.exists():
        raise FileNotFoundError(f"no {room} room is running for this project ({ROOMS[room]['cmd']})")
    return json.loads(path.read_text())


def _compose(room: str, env: dict[str, str], *args: str, check: bool = True, capture: bool = False):
    compose = room_root() / "deploy" / ROOMS[room]["compose"]  # built from the checkout or the installed package
    return subprocess.run(["docker", "compose", "-f", str(compose), *args], env={**os.environ, **env},
                          check=check, capture_output=capture, text=True)


def _wait_http(url: str, token: str, timeout_s: float = 30) -> None:
    deadline = time.monotonic() + timeout_s
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # loopback: never via a system proxy
    while time.monotonic() < deadline:
        try:
            with opener.open(urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"}), timeout=5):
                return
        except urllib.error.HTTPError:
            return  # it answers
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"server did not come up on {url}")


def _start(project: Path, room: str, argv: list[str], log_name: str) -> subprocess.Popen:
    log = (_dir(project, room) / log_name).open("a")
    return subprocess.Popen([sys.executable, "-m", "teardown.cli", *argv], stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)


def _bring_up(project: Path, room: str, server: subprocess.Popen, env: dict[str, str], extra: dict[str, Any],
              claude_token_file: Path | None, build: bool) -> None:
    secrets_env = {}
    if claude_token_file:  # credentials go to the container's environment only, never into a mount or state.json
        secrets_env["CLAUDE_CODE_OAUTH_TOKEN"] = Path(claude_token_file).expanduser().read_text().strip()
    state = {"room": room, "server_pid": server.pid, "env": env, "started": time.time(), **extra}
    (_dir(project, room) / "state.json").write_text(json.dumps(state, indent=1))
    try:
        _compose(room, {**env, **secrets_env}, "up", "-d", *(["--build"] if build else []))
    except subprocess.CalledProcessError:
        down(project, room)
        raise


def up(project: Path, kit: Path, *, allow: list[str] | None = None, api: str | None = None, port: int = 8765,
       clone: str = "web:kit", model_api: bool = True, build: bool = True,
       claude_token_file: Path | None = None) -> dict[str, Any]:
    """Clean room: the gate on the host (kit-only clones), the implementer's container with the kit."""
    project, kit = project.resolve(), kit.resolve()
    if not (kit / "spec.json").exists():
        raise FileNotFoundError(f"{kit} is not a clean-room kit (no spec.json); run teardown export-clean first")
    if kit.is_relative_to(project) or project.is_relative_to(kit):
        raise ValueError("the kit must not contain, or be inside, the project directory")
    state_dir = _dir(project, "clean")
    token = secrets.token_hex(16)
    gate = _start(project, "clean", ["gate-serve", "--project", str(project), "--kit", str(kit), "--host",
                                     "127.0.0.1", "--port", str(port), "--token", token], "gate.log")
    _wait_http(f"http://127.0.0.1:{port}/spec", token)
    egress = [f"{HOST_ALIAS}:{port}", *([MODEL_API] if model_api else []), *(allow or [])]
    kit_api = ""
    if api:  # the backend API the kit names (e.g. http://127.0.0.1:8000/api), reachable from the clean shell
        u = urlsplit(api)
        host = HOST_ALIAS if u.hostname in ("127.0.0.1", "localhost") else u.hostname
        egress.append(f"{host}:{u.port or 80}")
        kit_api = api.replace(f"//{u.hostname}", f"//{host}", 1)
    env = {"KIT": str(kit), "GATE_URL": f"http://{HOST_ALIAS}:{port}", "GATE_TOKEN": token, "CLONE": clone,
           "EGRESS_ALLOW": " ".join(egress), "CLEANROOM_LOG": str(state_dir), "KIT_API_URL": kit_api}
    if clone == "android:kit":  # javac in the container compiles against the SDK's public stub
        from teardown.drivers.android.build import sdk_paths

        env["ANDROID_PLATFORM"] = str(sdk_paths()[1].parent)
    _bring_up(project, "clean", gate, env, {"port": port, "token": token, "kit": str(kit)}, claude_token_file, build)
    return {"gate": f"http://127.0.0.1:{port}", "egress_allow": egress, "kit": str(kit), "log": str(state_dir)}


def observer_up(project: Path, workspace: Path, *, port: int = 8766, model_api: bool = True, build: bool = True,
                claude_token_file: Path | None = None) -> dict[str, Any]:
    """Observer room: the observe MCP server on the host (drivers keep their privileges there), the observer's
    container with only its scratch workspace. The target itself is never in the allowlist."""
    project, workspace = project.resolve(), workspace.resolve()
    if workspace.is_relative_to(project) or project.is_relative_to(workspace):
        raise ValueError("the observer workspace must not contain, or be inside, the project directory")
    if REPO.is_relative_to(workspace):
        raise ValueError("the observer workspace must not contain the Teardown repository")
    workspace.mkdir(parents=True, exist_ok=True)
    state_dir = _dir(project, "observer")
    token = secrets.token_hex(16)
    server = _start(project, "observer", ["observe", "--project", str(project), "--host", "127.0.0.1", "--port",
                                          str(port), "--token", token, "--allowed-host", HOST_ALIAS], "observe.log")
    _wait_http(f"http://127.0.0.1:{port}/mcp", token)
    egress = [f"{HOST_ALIAS}:{port}", *([MODEL_API] if model_api else [])]
    env = {"WORKSPACE": str(workspace), "OBSERVE_URL": f"http://{HOST_ALIAS}:{port}/mcp", "OBSERVE_TOKEN": token,
           "EGRESS_ALLOW": " ".join(egress), "ROOM_LOG": str(state_dir)}
    _bring_up(project, "observer", server, env, {"port": port, "token": token, "workspace": str(workspace)},
              claude_token_file, build)
    return {"observe": f"http://127.0.0.1:{port}/mcp", "egress_allow": egress, "workspace": str(workspace),
            "log": str(state_dir)}


# Probes run inside the room's container: each prints one JSON line {"probe": ..., "ok": bool, "detail": ...}.
_PROBES = r'''
import json, os, socket, urllib.request
def out(name, ok, detail=""):
    print(json.dumps({"probe": name, "ok": ok, "detail": str(detail)[:160]}))
def connect_via_proxy(host, port):
    s = socket.create_connection(("egress", 3128), timeout=10)
    s.sendall(f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
    line = s.recv(200).split(b"\r\n")[0].decode(); s.close(); return line
try:
    if ROOM == "clean":
        req = urllib.request.Request(os.environ["TEARDOWN_GATE_URL"] + "/spec",
                                     headers={"Authorization": "Bearer " + os.environ["TEARDOWN_GATE_TOKEN"]})
    else:
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "probe", "version": "1"}}})
        req = urllib.request.Request(os.environ["TEARDOWN_OBSERVE_URL"], data=body.encode(), method="POST", headers={
            "Authorization": "Bearer " + os.environ["TEARDOWN_OBSERVE_TOKEN"], "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"})
    out("room server reachable through egress", urllib.request.urlopen(req, timeout=15).status == 200)
except Exception as e:
    out("room server reachable through egress", False, e)
for host, port in [("1.1.1.1", 443)] + [("host.docker.internal", p) for p in TARGET_PORTS]:
    try:
        socket.create_connection((host, port), timeout=5).close(); out(f"no direct route to {host}:{port}", False)
    except OSError as e:
        out(f"no direct route to {host}:{port}", True, e)
for host, port in [("example.com", 443)] + [("host.docker.internal", p) for p in TARGET_PORTS]:
    line = connect_via_proxy(host, port)
    out(f"egress refuses {host}:{port}", " 403 " in line + " ", line)
if MODEL_API:
    line = connect_via_proxy("api.anthropic.com", 443)
    out("egress allows the model API", " 200 " in line + " ", line)
mounts = open("/proc/mounts").read()
for name, path in (("project directory", PROJECT), ("Teardown repository (target sources, references)", REPO)):
    out(f"{name} not visible", not os.path.exists(path) and path not in mounts)
binds = [l.split()[1] for l in mounts.splitlines() if l.split()[1].startswith(MOUNT)]
out(f"{MOUNT} is the only bind mount", binds == [MOUNT])
'''


def check(project: Path, original_port: int | None = None, room: str = "clean",
          target_ports: list[int] | None = None) -> list[dict[str, Any]]:
    project = project.resolve()
    state = _load(project, room)
    ports = sorted(set(target_ports or []) | ({original_port} if original_port else set()) or {4300})
    code = (_PROBES.replace("ROOM", repr(room)).replace("TARGET_PORTS", repr(ports))
            .replace("MODEL_API", repr(MODEL_API in state["env"]["EGRESS_ALLOW"]))
            .replace("PROJECT", repr(str(project))).replace("REPO", repr(str(REPO)))
            .replace("MOUNT", repr(ROOMS[room]["mount"])))
    cp = _compose(room, state["env"], "exec", "-T", ROOMS[room]["service"], "python", "-c", code, capture=True)
    return [json.loads(line) for line in cp.stdout.splitlines() if line.startswith("{")]


def shell(project: Path, command: list[str] | None = None, room: str = "clean") -> int:
    state = _load(project.resolve(), room)
    tty = [] if sys.stdin.isatty() else ["-T"]  # no TTY when driven by a script or an agent
    return _compose(room, state["env"], "exec", *tty, ROOMS[room]["service"], *(command or ["bash"]),
                    check=False).returncode


def down(project: Path, room: str = "clean") -> None:
    project = project.resolve()
    path = _dir(project, room) / "state.json"
    if not path.exists():
        return
    state = json.loads(path.read_text())
    _compose(room, state["env"], "down", check=False)
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(state.get("server_pid") or state.get("gate_pid"), signal.SIGTERM)
    path.unlink()
