"""Enforced clean room on one machine: `teardown cleanroom up | check | shell | down`.

The dirty zone is the host: the project, the original, and the gate (`gate-serve --kit`, which accepts only clones
built from the kit). The clean zone is a container that sees only the kit and an internal network whose only peer
is the egress proxy; the proxy forwards to an explicit allowlist (the gate, the model API, and an API the kit names)
and logs every attempt. State lives in ``<project>/.cleanroom/`` (dirty side: the token never enters the kit).
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

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "deploy" / "cleanroom.yaml"
HOST_ALIAS = "host.docker.internal"
MODEL_API = "api.anthropic.com:443"


def _dir(project: Path) -> Path:
    d = project / ".cleanroom"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load(project: Path) -> dict[str, Any]:
    path = _dir(project) / "state.json"
    if not path.exists():
        raise FileNotFoundError("no clean room is running for this project (teardown cleanroom up)")
    return json.loads(path.read_text())


def _compose(env: dict[str, str], *args: str, check: bool = True, capture: bool = False):
    return subprocess.run(["docker", "compose", "-f", str(COMPOSE), *args], env={**os.environ, **env}, check=check,
                          capture_output=capture, text=True)


def _wait_gate(url: str, token: str, timeout_s: float = 30) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(url + "/spec", headers={"Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(req, timeout=5):  # noqa: S310 - our own gate
                return
        except urllib.error.HTTPError:
            return  # it answers (e.g. no release yet)
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f"gate did not come up on {url}")


def up(project: Path, kit: Path, *, allow: list[str] | None = None, api: str | None = None, port: int = 8765,
       clone: str = "web:kit", model_api: bool = True, build: bool = True,
       claude_token_file: Path | None = None) -> dict[str, Any]:
    project, kit = project.resolve(), kit.resolve()
    if not (kit / "spec.json").exists():
        raise FileNotFoundError(f"{kit} is not a clean-room kit (no spec.json); run teardown export-clean first")
    if kit.is_relative_to(project) or project.is_relative_to(kit):
        raise ValueError("the kit must not contain, or be inside, the project directory")
    state_dir = _dir(project)
    token = secrets.token_hex(16)
    gate_log = (state_dir / "gate.log").open("a")
    gate = subprocess.Popen([sys.executable, "-m", "teardown.cli", "gate-serve", "--project", str(project), "--kit",
                             str(kit), "--host", "127.0.0.1", "--port", str(port), "--token", token],
                            stdout=gate_log, stderr=subprocess.STDOUT, start_new_session=True)
    _wait_gate(f"http://127.0.0.1:{port}", token)
    egress = [f"{HOST_ALIAS}:{port}", *([MODEL_API] if model_api else []), *(allow or [])]
    kit_api = ""
    if api:  # the backend API the kit names (e.g. http://127.0.0.1:8000/api), reachable from the clean shell
        u = urlsplit(api)
        host = HOST_ALIAS if u.hostname in ("127.0.0.1", "localhost") else u.hostname
        egress.append(f"{host}:{u.port or 80}")
        kit_api = api.replace(f"//{u.hostname}", f"//{host}", 1)
    env = {"KIT": str(kit), "GATE_URL": f"http://{HOST_ALIAS}:{port}", "GATE_TOKEN": token, "CLONE": clone,
           "EGRESS_ALLOW": " ".join(egress), "CLEANROOM_LOG": str(state_dir), "KIT_API_URL": kit_api}
    secrets_env = {}
    if claude_token_file:  # credentials go to the container's environment only, never into the kit or state.json
        secrets_env["CLAUDE_CODE_OAUTH_TOKEN"] = Path(claude_token_file).expanduser().read_text().strip()
    state = {"gate_pid": gate.pid, "port": port, "token": token, "kit": str(kit), "env": env, "started": time.time()}
    (state_dir / "state.json").write_text(json.dumps(state, indent=1))
    try:
        _compose({**env, **secrets_env}, "up", "-d", *(["--build"] if build else []))
    except subprocess.CalledProcessError:
        down(project)
        raise
    return {"gate": f"http://127.0.0.1:{port}", "egress_allow": egress, "kit": str(kit), "log": str(state_dir)}


# Probes run inside the clean container: each prints one JSON line {"probe": ..., "ok": bool, "detail": ...}.
_PROBES = r'''
import json, os, socket, urllib.request
def out(name, ok, detail=""):
    print(json.dumps({"probe": name, "ok": ok, "detail": str(detail)[:160]}))
def connect_via_proxy(host, port):
    s = socket.create_connection(("egress", 3128), timeout=10)
    s.sendall(f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
    line = s.recv(200).split(b"\r\n")[0].decode(); s.close(); return line
gate, token = os.environ["TEARDOWN_GATE_URL"], os.environ["TEARDOWN_GATE_TOKEN"]
try:
    req = urllib.request.Request(gate + "/spec", headers={"Authorization": "Bearer " + token})
    out("gate reachable through egress", urllib.request.urlopen(req, timeout=15).status == 200)
except Exception as e:
    out("gate reachable through egress", False, e)
for host, port in (("1.1.1.1", 443), ("host.docker.internal", ORIGINAL_PORT)):
    try:
        socket.create_connection((host, port), timeout=5).close(); out(f"no direct route to {host}:{port}", False)
    except OSError as e:
        out(f"no direct route to {host}:{port}", True, e)
for host, port in (("example.com", 443), ("host.docker.internal", ORIGINAL_PORT)):
    line = connect_via_proxy(host, port)
    out(f"egress refuses {host}:{port}", " 403 " in line + " ", line)
if MODEL_API:
    line = connect_via_proxy("api.anthropic.com", 443)
    out("egress allows the model API", " 200 " in line + " ", line)
mounts = open("/proc/mounts").read()
out("project directory not visible", not os.path.exists(PROJECT) and PROJECT not in mounts)
kit_mounts = [l.split()[1] for l in mounts.splitlines() if l.split()[1].startswith("/kit")]
out("kit is the only bind mount", kit_mounts == ["/kit"])
'''


def check(project: Path, original_port: int | None = None) -> list[dict[str, Any]]:
    project = project.resolve()
    state = _load(project)
    code = (_PROBES.replace("ORIGINAL_PORT", str(original_port or 4300))
            .replace("MODEL_API", repr(MODEL_API in state["env"]["EGRESS_ALLOW"]))
            .replace("PROJECT", repr(str(project))))
    cp = _compose(state["env"], "exec", "-T", "clean", "python", "-c", code, capture=True)
    return [json.loads(line) for line in cp.stdout.splitlines() if line.startswith("{")]


def shell(project: Path, command: list[str] | None = None) -> int:
    state = _load(project.resolve())
    return _compose(state["env"], "exec", "clean", *(command or ["bash"]), check=False).returncode


def down(project: Path) -> None:
    project = project.resolve()
    path = _dir(project) / "state.json"
    if not path.exists():
        return
    state = json.loads(path.read_text())
    _compose(state["env"], "down", check=False)
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(state["gate_pid"], signal.SIGTERM)
    path.unlink()
