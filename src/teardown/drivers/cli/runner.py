"""Runners execute CLI invocations in an episode (a work directory that persists until the next reset).

``ContainerRunner`` keeps one locked-down container per runner and talks to a tiny shell loop over stdin/stdout,
so a reset costs a few milliseconds instead of a container start. The harness inside the container runs on a
private static busybox mounted at ``/.td``; it never uses the target image's own tools to set up or measure.

``LocalRunner`` runs on the host in a temporary directory with a clean environment. It provides no isolation and
is meant for development and for native CLIs that cannot run in a Linux container.

Observation shape (one per invocation)::

    {"exit": int | None, "signal": int | None, "timed_out": bool,
     "stdout": str (latin-1), "stderr": str (latin-1), "stdout_truncated": bool,
     "fs": [{"op": "create|modify|delete", "path": str, "kind": "file|dir|link", "sha256": str, "size": int,
             "content": str | None}]}
"""

from __future__ import annotations

import base64
import hashlib
import io
import os
import platform
import re
import selectors
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import time
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from teardown.drivers.cli.invocation import Invocation, from_bytes, to_bytes

OUTPUT_CAP = 1 << 20  # bytes kept per stream; ulimit -f stops runaway writers (they die with SIGXFSZ)
CONTENT_INLINE = 4096  # created/modified files at most this large are kept inline in the observation
MTIME = 1_600_000_000
TOOLBOX_IMAGE = "busybox:musl"

_LOOP = r"""
BB=/.td/busybox
mkdir -p /w/work /w/req /w/home
snap() {
  # tar of the given req files plus the work tree. Unreadable entries (seeded file modes, or the program's own
  # chmod) are recorded with their real modes, opened for the snapshot and restored afterwards.
  locked=$( cd /w && $BB find work ! -perm -u+r -o -type d ! -perm -u+x | $BB head -1 )
  extra=
  if [ -n "$locked" ]; then
    # pre-order: each directory's mode is recorded, then it is opened, then find descends into it
    ( cd /w && $BB find work -type d -exec $BB sh -c '$0 stat -c "%a %n" "$1"; $0 chmod u+rwx "$1"' $BB {} \; \
      ) > /w/req/modes_d 2>/dev/null
    ( cd /w && $BB find work ! -type d -exec $BB stat -c '%a %n' {} + ) > /w/req/modes_f 2>/dev/null
    ( cd /w && $BB find work -type f -exec $BB chmod u+r {} + ) 2>/dev/null
    $BB cat /w/req/modes_f /w/req/modes_d > /w/req/modes
    extra=req/modes
  fi
  printf 'R %s\n' "$($BB tar cf - -C /w "$@" $extra work | $BB base64 -w0)"
  if [ -n "$locked" ]; then
    ( cd /w && $BB sort -r -k2 /w/req/modes | while read -r m n; do $BB chmod "$m" "$n"; done ) 2>/dev/null
  fi
}
while read -r op data; do
  case "$op" in
    RESET)
      set -- $data
      $BB chmod -R u+rwx /w/work 2>/dev/null
      $BB rm -rf /w/work /w/home /w/req && $BB mkdir -p /w/work /w/home /w/req
      [ "$1" = "-" ] || echo "$1" | $BB base64 -d | $BB tar xf - -C /w/work
      if [ -n "$2" ]; then  # seeded modes, deepest first, applied after the contents are in place
        echo "$2" | $BB base64 -d > /w/req/seedmodes
        ( cd /w/work && while read -r m n; do $BB chmod "$m" "$n"; done < /w/req/seedmodes )
      fi
      snap ;;
    STEP)
      $BB rm -rf /w/req && $BB mkdir -p /w/req
      echo "$data" | $BB base64 -d | $BB tar xf - -C /w/req
      ( cd /w/work && . /w/req/run.sh )
      echo $? > /w/req/rc
      snap req/rc req/out req/err ;;
    QUIT) exit 0 ;;
  esac
done
"""


class Runner(ABC):
    isolation: str = "none"

    @abstractmethod
    def reset(self, files: dict[str, str] | None = None, modes: dict[str, str] | None = None) -> None: ...

    @abstractmethod
    def run(self, invocation: Invocation) -> dict[str, Any]: ...

    def fingerprint(self) -> dict[str, Any]:
        return {"isolation": self.isolation}

    def close(self) -> None:  # noqa: B027
        pass


# -- shared helpers --------------------------------------------------------------------------------------------
def _run_script(inv: Invocation, *, busybox: str, cpu_s: int, fsize_blocks: int, out_dir: str) -> str:
    env_vars = inv.full_env()
    path = shlex.quote(f"PATH={env_vars.pop('PATH')}") if "PATH" in env_vars else '"PATH=$PATH"'
    env = " ".join([path, *(shlex.quote(f"{k}={v}") for k, v in sorted(env_vars.items()))])
    stdin = {"pipe": f"<{out_dir}/stdin", "null": "</dev/null", "closed": "<&-"}[inv.stdin_mode]
    stdout = {"pipe": f">{out_dir}/out", "null": ">/dev/null", "closed": ">&-", "full": ">/dev/full"}[inv.stdout_mode]
    argv = " ".join(shlex.quote(a) for a in inv.argv)
    return (
        f": >{out_dir}/out; : >{out_dir}/err\n"
        f"ulimit -t {cpu_s}; ulimit -f {fsize_blocks}\n"
        f"{busybox} timeout -s KILL {max(1, int(inv.timeout_s))} {busybox} env -i {env} {argv} "
        f"{stdin} {stdout} 2>{out_dir}/err\n"
    )


def _tar(entries: dict[str, bytes | None]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.mtime = MTIME
            if data is None:
                info.type, info.mode = tarfile.DIRTYPE, 0o777
                tf.addfile(info)
            else:
                info.size, info.mode = len(data), 0o644
                tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _check_modes(files: dict[str, str], modes: dict[str, str]) -> dict[str, int]:
    out = {}
    dirs = {"/".join(Path(n).parts[:i]) for n in files for i in range(1, len(Path(n).parts))}
    for name, mode in modes.items():
        if name not in files and name not in dirs:
            raise ValueError(f"file_modes names a path that is not seeded: {name!r}")
        if not re.fullmatch(r"[0-7]{3,4}", mode):
            raise ValueError(f"file mode must be octal, e.g. '000' or '555': {mode!r}")
        out[name] = int(mode, 8)
    return out


def _seed_tar(files: dict[str, str], modes: dict[str, str] | None = None) -> bytes:
    entries: dict[str, bytes | None] = {}
    for name, text in sorted(files.items()):
        parts = Path(name).parts
        if Path(name).is_absolute() or ".." in parts:
            raise ValueError(f"seed file path must be relative: {name!r}")
        for i in range(1, len(parts)):
            entries.setdefault("/".join(parts[:i]), None)
        entries[name] = to_bytes(text)
    _check_modes(files, modes or {})
    return _tar(entries)


def _open_tree(root: Path) -> dict[Path, int]:
    """Make every entry under root readable by its owner; returns the original modes (pre-order, so locked
    directories are opened before they are listed)."""
    modes: dict[Path, int] = {}
    stack = [root]
    while stack:
        cur = stack.pop()
        for entry in sorted(cur.iterdir()):
            if entry.is_symlink():
                continue
            mode = entry.stat().st_mode & 0o7777
            want = mode | (0o700 if entry.is_dir() else 0o400)
            if want != mode:
                modes[entry] = mode
                os.chmod(entry, want)
            if entry.is_dir():
                stack.append(entry)
    return modes


def _snapshot_tree(root: Path) -> dict[str, tuple[str, int, str, int, bytes | None]]:
    locked = _open_tree(root)  # seeded file modes or the program's own chmod; restored below
    snap = {}
    try:
        for dirpath, dirnames, filenames in os.walk(root):
            for name in sorted(dirnames) + sorted(filenames):
                path = Path(dirpath) / name
                rel = path.relative_to(root).as_posix()
                mode = locked.get(path, path.lstat().st_mode & 0o7777)
                if path.is_symlink():
                    target = os.readlink(path).encode()
                    snap[rel] = ("link", 0, hashlib.sha256(target).hexdigest(), len(target), target)
                elif path.is_dir():
                    snap[rel] = ("dir", mode, "", 0, None)
                else:
                    data = path.read_bytes()
                    snap[rel] = ("file", mode, hashlib.sha256(data).hexdigest(), len(data), data)
    finally:
        for path, mode in sorted(locked.items(), key=lambda kv: -len(kv[0].parts)):
            os.chmod(path, mode)
    return snap


def _snapshot_tar(data: bytes, prefix: str) -> tuple[dict[str, tuple], dict[str, bytes]]:
    snap, files = {}, {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
        for m in tf:
            name = m.name.removeprefix("./")
            if not name.startswith(prefix):
                if m.isfile():
                    files[name] = tf.extractfile(m).read()
                continue
            rel = name[len(prefix):].lstrip("/")
            if not rel:
                continue
            if m.isfile():
                blob = tf.extractfile(m).read()
                snap[rel] = ("file", m.mode & 0o7777, hashlib.sha256(blob).hexdigest(), len(blob), blob)
            elif m.isdir():
                snap[rel] = ("dir", m.mode & 0o7777, "", 0, None)
            elif m.issym():
                target = m.linkname.encode()
                snap[rel] = ("link", 0, hashlib.sha256(target).hexdigest(), len(target), target)
    return snap, files


def _parse_snapshot(reply: bytes) -> tuple[dict[str, tuple], dict[str, bytes]]:
    """A container ``R <base64 tar>`` reply: the work tree, with the real modes of entries that had to be opened
    for the snapshot."""
    snap, files = _snapshot_tar(base64.b64decode(reply[2:]), "work")
    for line in files.get("req/modes", b"").decode("utf-8", "replace").splitlines():
        mode, _, name = line.partition(" ")
        rel = name.removeprefix("work").lstrip("/")
        if rel in snap and mode.isdigit():
            snap[rel] = (snap[rel][0], int(mode, 8), *snap[rel][2:])
    return snap, files


def fs_diff(before: dict[str, tuple], after: dict[str, tuple]) -> list[dict[str, Any]]:
    out = []
    for path in sorted(set(before) | set(after)):
        b, a = before.get(path), after.get(path)
        if b is not None and a is not None and b[:4] == a[:4]:
            continue
        if a is None:
            out.append({"op": "delete", "path": path})
            continue
        kind, mode, sha, size, blob = a
        entry = {"op": "create" if b is None else "modify", "path": path, "kind": kind, "mode": oct(mode),
                 "sha256": sha, "size": size, "content": None}
        if kind == "dir":
            entry.pop("sha256"), entry.pop("size"), entry.pop("content")
        elif blob is not None and size <= CONTENT_INLINE:
            entry["content"] = from_bytes(blob)
        out.append(entry)
    return out


def _decode_rc(rc: int | None) -> tuple[int | None, int | None, bool]:
    """Shell exit status -> (exit code, signal, timed out). busybox timeout -s KILL yields 137."""
    if rc is None:
        return None, None, False
    if rc > 128:
        return None, rc - 128, rc - 128 == 9
    return rc, None, False


_TRACE_START = re.compile(
    rb"^(Traceback \(most recent call last\):"  # Python
    rb"|Exception in thread \S+|\s+at [\w$.<>]+\(.*\)$"  # Java / JVM
    rb"|goroutine \d+ \[|panic: |stack backtrace:"  # Go, Rust
    rb"|\s+at .+ \(.+:\d+:\d+\)$"  # Node
    rb"|   at [\w.]+\(.*\) in )",  # .NET
    re.M)


def redact_traces(stderr: bytes) -> bytes:
    """Stack traces expose source paths, line numbers and code: implementation tier, never captured. Everything
    from the first trace marker on is replaced; that a diagnostic was written stays visible."""
    m = _TRACE_START.search(stderr)
    if not m:
        return stderr
    lines = stderr[m.start():].count(b"\n")
    return stderr[: m.start()] + b"[stack trace redacted by teardown: %d lines]\n" % lines


def _observation(rc, out: bytes, err: bytes, fs: list[dict[str, Any]], timed_out=False) -> dict[str, Any]:
    exit_code, signal, killed = _decode_rc(rc)
    err = redact_traces(err)
    return {
        "exit": exit_code,
        "signal": signal,
        "timed_out": timed_out or killed,
        "stdout": from_bytes(out[:OUTPUT_CAP]),
        "stdout_truncated": len(out) > OUTPUT_CAP,
        "stderr": from_bytes(err[:OUTPUT_CAP]),
        "fs": fs,
    }


# -- container runner ------------------------------------------------------------------------------------------
def toolbox_path() -> Path:
    """Static busybox for the harness, extracted once from the official image for this machine's architecture."""
    arch = {"x86_64": "amd64", "AMD64": "amd64", "arm64": "arm64", "aarch64": "arm64"}.get(platform.machine(), "x")
    path = Path(os.environ.get("TEARDOWN_CACHE", Path.home() / ".cache" / "teardown")) / f"busybox-musl-{arch}"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["docker", "pull", "-q", TOOLBOX_IMAGE], check=True, capture_output=True)
        cid = subprocess.run(["docker", "create", TOOLBOX_IMAGE], check=True, capture_output=True, text=True).stdout
        try:
            subprocess.run(["docker", "cp", f"{cid.strip()}:/bin/busybox", str(path)], check=True, capture_output=True)
        finally:
            subprocess.run(["docker", "rm", cid.strip()], capture_output=True)
    return path


class ContainerRunner(Runner):
    isolation = "container"

    def __init__(self, image: str, *, cpu_s: int = 5, fsize_blocks: int = 4096, memory: str = "512m",
                 step_timeout_s: float = 30.0):
        self.image = image
        self.cpu_s, self.fsize_blocks, self.memory = cpu_s, fsize_blocks, memory
        self.step_timeout_s = step_timeout_s
        self._proc: subprocess.Popen | None = None
        self._snap: dict[str, tuple] = {}
        self._seed: dict[str, str] = {}
        self._modes: dict[str, str] = {}
        self._name = ""
        self._buffer = b""

    def fingerprint(self) -> dict[str, Any]:
        digest = subprocess.run(["docker", "image", "inspect", "-f", "{{.Id}}", self.image],
                                capture_output=True, text=True).stdout.strip()
        return {"isolation": self.isolation, "image": self.image, "image_id": digest}

    def _start(self) -> None:
        self._name = f"teardown-cli-{uuid.uuid4().hex[:10]}"
        cmd = [
            "docker", "run", "-i", "--rm", "--name", self._name, "--network", "none", "--read-only",
            "--user", "65534:65534", "--tmpfs", "/w:rw,exec,mode=1777,size=512m", "--workdir", "/w",
            "--pids-limit", "256", "--memory", self.memory, "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "-v", f"{toolbox_path()}:/.td/busybox:ro",
            self.image, "/.td/busybox", "sh", "-c", _LOOP,
        ]
        self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self._buffer = b""

    def _request(self, line: bytes, timeout: float) -> bytes | None:
        if self._proc is None or self._proc.poll() is not None:
            self._start()
        assert self._proc and self._proc.stdin and self._proc.stdout
        self._proc.stdin.write(line + b"\n")
        self._proc.stdin.flush()
        deadline = time.monotonic() + timeout
        sel = selectors.DefaultSelector()
        sel.register(self._proc.stdout, selectors.EVENT_READ)
        try:
            while b"\n" not in self._buffer:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not sel.select(remaining):
                    return None
                chunk = os.read(self._proc.stdout.fileno(), 1 << 20)
                if not chunk:
                    return None
                self._buffer += chunk
        finally:
            sel.close()
        line_out, _, self._buffer = self._buffer.partition(b"\n")
        return line_out

    def _restart(self) -> None:
        subprocess.run(["docker", "rm", "-f", self._name], capture_output=True)
        self._proc = None

    def reset(self, files: dict[str, str] | None = None, modes: dict[str, str] | None = None) -> None:
        self._seed, self._modes = dict(files or {}), dict(modes or {})
        payload = base64.b64encode(_seed_tar(self._seed, self._modes)).decode() if self._seed else "-"
        order = sorted(_check_modes(self._seed, self._modes).items(), key=lambda kv: -len(Path(kv[0]).parts))
        if order:
            lines = "".join(f"{mode:o} {name}\n" for name, mode in order)
            payload += " " + base64.b64encode(lines.encode()).decode()
        reply = self._request(f"RESET {payload}".encode(), self.step_timeout_s)
        if reply is None or not reply.startswith(b"R "):
            self._restart()
            reply = self._request(f"RESET {payload}".encode(), self.step_timeout_s)
            if reply is None or not reply.startswith(b"R "):
                raise RuntimeError(f"could not reset container session for {self.image}")
        # the starting state as the container has it (umask, seeded modes), not as the seed tar describes it
        self._snap = _parse_snapshot(reply)[0]

    def run(self, invocation: Invocation) -> dict[str, Any]:
        if invocation.files:
            raise ValueError("per-invocation seed files are applied at reset; pass them to reset()")
        script = _run_script(invocation, busybox="/.td/busybox", cpu_s=self.cpu_s, fsize_blocks=self.fsize_blocks,
                             out_dir="/w/req")
        req = {"run.sh": script.encode(), "stdin": to_bytes(invocation.stdin or "")}
        line = f"STEP {base64.b64encode(_tar(req)).decode()}".encode()
        reply = self._request(line, invocation.timeout_s + self.step_timeout_s)
        if reply is None or not reply.startswith(b"R "):
            self._restart()
            self.reset(self._seed, self._modes)
            return _observation(None, b"", b"", [], timed_out=True)
        snap, files = _parse_snapshot(reply)
        diff = fs_diff(self._snap, snap)
        self._snap = snap
        rc_raw = files.get("req/rc", b"").strip()
        rc = int(rc_raw) if rc_raw.lstrip(b"-").isdigit() else None
        return _observation(rc, files.get("req/out", b""), files.get("req/err", b""), diff)

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._request(b"QUIT -", 2)
            finally:
                self._restart()
        self._proc = None


# -- local runner ----------------------------------------------------------------------------------------------
class LocalRunner(Runner):
    """No isolation: runs on the host in a scratch directory with a clean environment."""

    isolation = "none"

    def __init__(self):
        self._root = Path(tempfile.mkdtemp(prefix="teardown-cli-"))
        self._work = self._root / "work"
        self._snap: dict[str, tuple] = {}

    def reset(self, files: dict[str, str] | None = None, modes: dict[str, str] | None = None) -> None:
        if self._work.exists():
            _open_tree(self._work)
        shutil.rmtree(self._work, ignore_errors=True)
        self._work.mkdir(parents=True)
        (self._root / "home").mkdir(exist_ok=True)
        for name, text in (files or {}).items():
            path = self._work / name
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise ValueError(f"seed file path must be relative: {name!r}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(to_bytes(text) or b"")
        # deepest first, so a locked directory does not stop its contents from getting their modes
        checked = _check_modes(files or {}, modes or {})
        for name, mode in sorted(checked.items(), key=lambda kv: -len(Path(kv[0]).parts)):
            os.chmod(self._work / name, mode)
        self._snap = _snapshot_tree(self._work)

    def run(self, invocation: Invocation) -> dict[str, Any]:
        env = {**invocation.full_env(), "HOME": str(self._root / "home"), "PATH": os.environ.get("PATH", "")}
        piped = invocation.stdin_mode == "pipe"
        sink = None
        if invocation.stdout_mode == "full" and os.path.exists("/dev/full"):
            sink = open("/dev/full", "wb")  # noqa: SIM115 - closed in finally
        stdout = {"pipe": subprocess.PIPE, "null": subprocess.DEVNULL, "closed": subprocess.DEVNULL,
                  "full": sink or subprocess.DEVNULL}[invocation.stdout_mode]
        try:
            cp = subprocess.run(invocation.argv, cwd=self._work, env=env, timeout=invocation.timeout_s,
                                input=to_bytes(invocation.stdin or "") if piped else None,
                                stdin=None if piped else subprocess.DEVNULL, stdout=stdout, stderr=subprocess.PIPE)
            rc = cp.returncode if cp.returncode >= 0 else 128 - cp.returncode
            out, err, timed_out = cp.stdout or b"", cp.stderr or b"", False
        except subprocess.TimeoutExpired as exc:
            rc, out, err, timed_out = None, exc.stdout or b"", exc.stderr or b"", True
        except FileNotFoundError:
            rc, out, err, timed_out = 127, b"", b"command not found\n", False
        finally:
            if sink:
                sink.close()
        snap = _snapshot_tree(self._work)
        diff = fs_diff(self._snap, snap)
        self._snap = snap
        return _observation(rc, out, err, diff, timed_out=timed_out)

    def close(self) -> None:
        shutil.rmtree(self._root, ignore_errors=True)
