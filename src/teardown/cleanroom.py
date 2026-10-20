"""Clean-room kit export: the released spec plus what an implementer needs to build and check a clone.

Phase 0/1 kits rely on the implementer's environment for isolation (separate agent, no web, no access to the
project directory). Phase 3 replaces this with the isolated clean runtime; the kit contents stay the same.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path

from teardown.gate.gate import load_release

README = """# Clean-room kit: {codename}

You are implementing a command-line tool from a **behavioral specification**. Build it only from `spec.json`.
Do not look for, recall or reuse any existing tool; do not use the network; do not read anything outside this
directory. Ask questions by writing them to `questions.md`.

- `spec.json` — the released specification (release `{release}`).
  - `actions`: every probe as an invocation (`argv`, `stdin`, `files` placed in the working directory, `env`,
    `stdin_mode`, `stdout_mode`).
  - `probe_table`: for each action, the expected behavior symbol (exit code, exact stdout, whether a diagnostic is
    written to stderr and its errno class, file-system effects).
  - `rules`: behavioral rules stated by the observer, each with checks and the original's observed symbols.
    `outcome` checks give an invocation and the expected part of its symbol; `same`/`differs` checks say two
    invocations must behave alike / differently (optionally on some `keys`). **Rules are the generalizations to build
    from; probes are worked examples.** The verifier tests the relations on your build, not only fixed outputs.
  - `claims`: generalizations mined from the probes (value classes, refusals), each with checks.
  - `interface`: option names, arity and value types.
  - `unknowns`: what the observer could not establish.
- Contract: {contract}
- Implement the tool so that `{command}` resolves on PATH inside the image built from `Dockerfile` (Python 3.12
  standard library only, code in `impl/`, entry point `impl/main.py`).
- `./verify.sh` builds the image and runs the conformance suite against your build and the original. It reports
  pass/fail counts and, for failing tests, the inputs plus expected and observed abstract symbols. Each call uses
  verification budget; batch your fixes.
"""

DOCKERFILE = """FROM python:3.12-slim
COPY impl/ /opt/clone/
RUN printf '#!/bin/sh\\nexec python3 /opt/clone/main.py "$@"\\n' > /usr/local/bin/{command} && \\
    chmod +x /usr/local/bin/{command}
"""

VERIFY = """#!/bin/sh
# Builds the clone image and asks the dirty-side verifier for an abstract verdict.
set -e
cd "$(dirname "$0")"
docker build -q -t {image} . >/dev/null
cd {repo}
uv run --quiet teardown verify --project {project} --clone cli:docker:{image} "$@"
"""


def export_kit(project_root: Path, out: Path) -> str:
    project_root, out = Path(project_root).resolve(), Path(out).resolve()
    rel = load_release(project_root / "releases")
    spec = rel.spec
    commands = sorted({a["argv"][0] for a in (spec.get("actions") or {}).values()})
    if len(commands) != 1:
        raise ValueError(f"kit export expects a single command, found {commands}")
    command = commands[0]
    image = f"teardown-clone/{rel.codename}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "impl").mkdir(exist_ok=True)
    (out / "spec.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "README.md").write_text(README.format(codename=rel.codename, release=rel.id, command=command,
                                                 contract=spec["testability_contract"]), encoding="utf-8")
    (out / "Dockerfile").write_text(DOCKERFILE.format(command=command), encoding="utf-8")
    repo = Path(__file__).resolve().parents[2]
    # The kit must not reveal the project's (possibly real-name) directory: route through a codenamed link.
    link = repo / ".teardown" / "verify" / rel.codename
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(project_root, target_is_directory=True)
    verify = out / "verify.sh"
    verify.write_text(VERIFY.format(image=image, repo=shlex.quote(str(repo)), project=shlex.quote(str(link))),
                      encoding="utf-8")
    verify.chmod(0o755)
    if not (out / "impl" / "main.py").exists():
        (out / "impl" / "main.py").write_text("import sys\n\nsys.exit('not implemented')\n", encoding="utf-8")
    _check_no_real_names(project_root, out)
    return str(out)


def _check_no_real_names(project_root: Path, out: Path) -> None:
    """Fail closed if any denylisted real name appears in the kit (file contents or the kit's own path)."""
    state = json.loads((project_root / "project.json").read_text(encoding="utf-8"))
    terms = [t.casefold() for t in state["gate"]["denylist"] if t]
    hits = [t for t in terms if t in str(out).casefold()]
    for path in out.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".sh", ".json", ""} | {"Dockerfile"}:
            text = path.read_text(encoding="utf-8", errors="replace").casefold()
            hits += [f"{t} in {path.name}" for t in terms if t in text]
    if hits:
        raise RuntimeError(f"clean-room kit leaks real names: {sorted(set(hits))}")
