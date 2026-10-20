"""Execute probes in fresh, isolated, deterministic containers and capture observations.

Isolation model (per batch = one container):
  docker run -i --rm --network none --read-only --user 65534 --tmpfs /w ...
  * root filesystem read-only  -> any write outside the probe dir fails loudly
  * /w is a tmpfs, populated from a tar streamed on stdin, streamed back on stdout
  * every probe gets its own pre-built dir p/<id>/{work/,tmp/,cmd.sh,stdin}
    (built on the host; the container only uses `tar` and shell builtins, never the
    coreutils under test, to set up or measure)
  * resource caps via shell builtins: ulimit -t (CPU s), ulimit -f (output size)
Side effects = host-side diff of p/<id>/work and p/<id>/tmp before vs after.
"""
from __future__ import annotations

import hashlib
import io
import json
import shlex
import subprocess
import tarfile
import time
import uuid
from dataclasses import dataclass, field

from .impls import BASE_ENV, Impl

CPU_LIMIT_S = 5
FSIZE_LIMIT_BLOCKS = 512  # 512-byte blocks => 256 KiB per output file
MTIME = 1_600_000_000     # fixed mtime for all input files (determinism)

DRIVER = r"""
cd /w/p || exit 99
for d in *; do
  [ -d "$d" ] || continue
  if [ -f "$d/stdin" ]; then in="/w/p/$d/stdin"; else in=/dev/null; fi
  ( cd "/w/p/$d/work" && ulimit -t %(cpu)d && ulimit -f %(fsz)d && exec sh ../cmd.sh <"$in" >../out 2>../err )
  echo $? > "/w/p/$d/rc"
done
""" % {"cpu": CPU_LIMIT_S, "fsz": FSIZE_LIMIT_BLOCKS}


@dataclass
class Probe:
    id: str
    cmd: str
    argv: list[str]                      # arguments after the command name
    stdin: bytes | None = None           # None -> /dev/null
    files: dict[str, bytes] = field(default_factory=dict)  # initial files in cwd
    env: dict[str, str] = field(default_factory=dict)      # extra env on top of BASE_ENV
    tags: list[str] = field(default_factory=list)          # generating factors (for clustering)

    def to_json(self) -> dict:
        return {
            "id": self.id, "cmd": self.cmd, "argv": self.argv,
            "stdin": None if self.stdin is None else self.stdin.decode("latin-1"),
            "files": {k: v.decode("latin-1") for k, v in self.files.items()},
            "env": self.env, "tags": self.tags,
        }

    @staticmethod
    def from_json(d: dict) -> "Probe":
        return Probe(d["id"], d["cmd"], d["argv"],
                     None if d["stdin"] is None else d["stdin"].encode("latin-1"),
                     {k: v.encode("latin-1") for k, v in d["files"].items()},
                     d["env"], d["tags"])


def _cmd_script(p: Probe) -> bytes:
    lines = [f"export {k}={shlex.quote(v)}" for k, v in {**BASE_ENV, **p.env}.items()]
    lines.append(f"export TMPDIR=/w/p/{p.id}/tmp")
    lines.append("exec " + " ".join(shlex.quote(a) for a in [p.cmd, *p.argv]))
    return ("\n".join(lines) + "\n").encode("utf-8", "surrogateescape")


def _add(tf: tarfile.TarFile, name: str, data: bytes | None, mode: int = 0o644) -> None:
    ti = tarfile.TarInfo(name)
    ti.mtime = MTIME
    ti.uid = ti.gid = 65534
    if data is None:
        ti.type, ti.mode = tarfile.DIRTYPE, 0o777
        tf.addfile(ti)
    else:
        ti.size, ti.mode = len(data), mode
        tf.addfile(ti, io.BytesIO(data))


def build_tar(probes: list[Probe]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tf:
        _add(tf, "driver.sh", DRIVER.encode())
        _add(tf, "p", None)
        for p in probes:
            base = f"p/{p.id}"
            _add(tf, base, None)
            _add(tf, f"{base}/work", None)
            _add(tf, f"{base}/tmp", None)
            _add(tf, f"{base}/cmd.sh", _cmd_script(p))
            if p.stdin is not None:
                _add(tf, f"{base}/stdin", p.stdin)
            for name, data in p.files.items():
                _add(tf, f"{base}/work/{name}", data)
    return buf.getvalue()


def _tree(members: dict[str, tuple], prefix: str) -> dict[str, tuple]:
    return {k[len(prefix):]: v for k, v in members.items() if k.startswith(prefix) and k != prefix.rstrip("/")}


def _fsdiff(before: dict[str, tuple], after: dict[str, tuple]) -> list[dict]:
    out = []
    for k in sorted(set(before) | set(after)):
        b, a = before.get(k), after.get(k)
        if b == a:
            continue
        if b is None:
            out.append({"op": "create", "path": k, "kind": a[0], "sha": a[2], "size": a[3]})
        elif a is None:
            out.append({"op": "delete", "path": k})
        else:
            out.append({"op": "modify", "path": k, "kind": a[0], "mode": oct(a[1]), "sha": a[2], "size": a[3]})
    return out


def _members(tar_bytes: bytes) -> tuple[dict[str, tuple], dict[str, bytes]]:
    meta, data = {}, {}
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:*") as tf:
        for m in tf:
            name = m.name.lstrip("./")
            if m.isfile():
                b = tf.extractfile(m).read()
                data[name] = b
                meta[name] = ("file", m.mode & 0o7777, hashlib.sha256(b).hexdigest()[:16], len(b))
            elif m.isdir():
                meta[name] = ("dir", m.mode & 0o7777, None, 0)
            else:
                meta[name] = (m.type.decode(errors="replace"), m.mode & 0o7777, m.linkname, 0)
    return meta, data


def run_batch(impl: Impl, probes: list[Probe], timeout_s: float = 600) -> tuple[list[dict], dict]:
    """Run `probes` in ONE fresh container. Returns (observations, timing)."""
    in_tar = build_tar(probes)
    before, _ = _members(in_tar)
    name = f"teardown-{impl.key}-{uuid.uuid4().hex[:8]}"
    docker = [
        "docker", "run", "-i", "--rm", "--name", name, "--network", "none",
        "--read-only", "--user", "65534:65534", "--tmpfs", "/w:rw,exec,mode=1777,size=1g",
        "--workdir", "/w", "--pids-limit", "256", "--memory", "1g",
        impl.image, "sh", "-c", "tar xf - && sh driver.sh && tar cf - p",
    ]
    t0 = time.perf_counter()
    try:
        cp = subprocess.run(docker, input=in_tar, capture_output=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        raise
    wall = time.perf_counter() - t0
    if cp.returncode != 0:
        raise RuntimeError(f"batch failed on {impl.key}: rc={cp.returncode} {cp.stderr[:500]!r}")
    after, data = _members(cp.stdout)
    obs = []
    for p in probes:
        base = f"p/{p.id}/"
        rc_raw = data.get(base + "rc", b"").strip()
        fs = _fsdiff(_tree(before, base + "work/"), _tree(after, base + "work/"))
        fs += [{**d, "path": "$TMPDIR/" + d["path"]} for d in
               _fsdiff(_tree(before, base + "tmp/"), _tree(after, base + "tmp/"))]
        obs.append({
            "probe": p.id, "impl": impl.key,
            "rc": int(rc_raw) if rc_raw.lstrip(b"-").isdigit() else None,
            "stdout": data.get(base + "out", b"").decode("latin-1"),
            "stderr": data.get(base + "err", b"").decode("latin-1"),
            "fs": fs,
        })
    return obs, {"impl": impl.key, "n": len(probes), "wall_s": wall,
                 "tar_in_kb": len(in_tar) // 1024, "tar_out_kb": len(cp.stdout) // 1024}


def run_probes(impl: Impl, probes: list[Probe], batch_size: int = 400) -> tuple[list[dict], list[dict]]:
    obs, timings = [], []
    for i in range(0, len(probes), batch_size):
        o, t = run_batch(impl, probes[i:i + batch_size])
        obs += o
        timings.append(t)
    return obs, timings


def save_jsonl(path: str, rows: list[dict]) -> None:
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_jsonl(path: str) -> list[dict]:
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]
