"""Clean-room kit export: the released spec plus what an implementer needs to build and check a clone.

Phase 0/1 kits rely on the implementer's environment for isolation (separate agent, no web, no access to the
project directory). Phase 3 replaces this with the isolated clean runtime; the kit contents stay the same.
"""

from __future__ import annotations

import json
import shlex
import sys
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
  verification budget; batch your fixes. Inside an enforced clean room (`teardown cleanroom`) the command is
  `verify` instead (same options): it asks the gate, which builds and runs your kit. `--only-failed` re-runs
  just the tests your build did not pass last time, which is much faster on a large spec; finish with a full
  run.
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
{teardown} verify --project {project} --clone cli:docker:{image} "$@"
"""


WEB_README = """# Clean-room kit: {codename} (web)

You are implementing a web frontend from a **behavioral specification**. Build it only from `spec.json` (and any
public documents placed in this directory). Do not look for, recall or reuse an existing implementation; do not use
the network beyond the backend API named below; do not read anything outside this directory.

- `spec.json` — the released specification (release `{release}`):
  - `actions`: UI actions by ARIA role and accessible name (`op`: click/fill/check/select/press/goto, `value`).
  - `rules`: behavioral rules with checks; UI checks run action sequences (`a_inputs`/`b_inputs`) and compare the
    structured accessibility view on the listed `keys`.
  - `probe_table` / `claims`: worked examples (field classes, refusals, which side refuses).
  - `api`: the backend contract observed through the UI (endpoints, statuses, value-free body shapes).
  - `model`: a learned state machine of a flow, if present.
- Contract: {contract}
- The backend is reachable at `{api}`; your frontend calls it directly from the browser.
- Put a static build in `impl/` with `impl/index.html` as the entry (any framework you write yourself; no CDN
  assets — third-party hosts are blocked). Unknown paths are served `index.html` (client-side routing).
- `./verify.sh` serves `impl/` and runs the conformance suite against your build and the original, reporting
  pass/fail per test with abstract symbols. If your accessible names differ from the spec's, pass an adapter:
  `./verify.sh --adapter adapter.json` with `{{"actions": {{name: action}}, "rules": [mapper rules]}}`.
- Inside an enforced clean room (`teardown cleanroom`) the command is `verify` instead (same options): it asks the
  gate, which serves your `impl/`. From the clean shell the backend is reachable at `$TEARDOWN_API_URL`; your app
  itself must still call the address above, because the gate runs it. `--only-failed` re-runs just the tests
  your build did not pass last time, which is much faster on a large spec; finish with a full run.
"""

WEB_VERIFY = """#!/bin/sh
set -e
cd "$(dirname "$0")"
KIT=$(pwd)
{teardown} verify-web --project {project} --dist "$KIT/impl" "$@"
"""


def export_web_kit(project_root: Path, out: Path, rel, api: str) -> str:
    import shlex as _shlex

    link = _verify_link(project_root, rel.codename)
    out.mkdir(parents=True, exist_ok=True)
    (out / "impl").mkdir(exist_ok=True)
    (out / "spec.json").write_text(json.dumps(rel.spec, indent=1, ensure_ascii=False), encoding="utf-8")
    readme = WEB_README.format(codename=rel.codename, release=rel.id, api=api,
                               contract=rel.spec["testability_contract"])
    from teardown.project import Project

    hosts = (Project(project_root).state.target_options.get("profile") or {}).get("asset_hosts") or []
    if hosts:  # layout-dependent observations (sizes, visibility) reflect these third-party assets
        readme += ("\n- The original was observed with stylesheets, fonts and images from these third-party hosts "
                   f"loaded: {', '.join(sorted(hosts))}. Sizes, visibility and accessible names (icon glyphs) "
                   "reflect them. Your build may not load them: reproduce their effect with your own assets.\n")
    (out / "README.md").write_text(readme, encoding="utf-8")
    verify = out / "verify.sh"
    verify.write_text(WEB_VERIFY.format(teardown=_teardown_command(), project=_shlex.quote(str(link))),
                      encoding="utf-8")
    verify.chmod(0o755)
    if not (out / "impl" / "index.html").exists():
        (out / "impl" / "index.html").write_text("<!doctype html><title>todo</title>", encoding="utf-8")
    _check_no_real_names(project_root, out)
    return str(out)


ANDROID_README = """# Clean-room kit: {codename} (Android)

You are implementing an Android app from a **behavioral specification**. Build it only from `spec.json` (and any
public documents placed in this directory). Do not look for, recall or reuse an existing implementation.

- `spec.json` — the released specification (release `{release}`):
  - `actions`: UI actions by accessibility role and accessible name (`action`: click/fill/key/back/longclick/network,
    `value`); `network` turns the device's network off/on (airplane mode).
  - `rules`, `probe_table`, `claims`: observed behavior with the original's abstract symbols (controls by role and
    name with state flags, visible text); `model`, `unknowns`.
- Contract: {contract}
- Write the app in Java (UI built in code; no resource files, no Gradle, no third-party libraries) under
  `src/{package_path}/`, with `Main` as the launcher activity. `AndroidManifest.xml` is given: keep its package
  (`{package}`) and launcher; add permissions or activities you need. Android API 26–34; `android.*` only.
- `verify` (inside the enforced clean room) or `./verify.sh` builds the APK, installs it on the verification
  device and runs the conformance suite against your build and the original. Build errors are reported back.
  `--only-failed` re-runs just the tests your build did not pass last time, which is much faster on a large
  spec; finish with a full run.
- To compile-check locally (in the clean room): `javac --release 11 -cp /opt/android/android.jar -d /tmp/classes
  $(find src -name '*.java')`. There is no device or emulator on the clean side.
"""

ANDROID_MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="{package}"
    android:versionCode="1" android:versionName="1.0">
    <uses-sdk android:minSdkVersion="26" android:targetSdkVersion="34" />
    <application android:label="{codename}" android:allowBackup="false">
        <activity android:name=".Main" android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
"""

ANDROID_MAIN = """package {package};

import android.app.Activity;
import android.os.Bundle;
import android.widget.TextView;

public class Main extends Activity {{
    @Override
    protected void onCreate(Bundle state) {{
        super.onCreate(state);
        TextView todo = new TextView(this);
        todo.setText("todo");
        setContentView(todo);
    }}
}}
"""


def clone_package(codename: str) -> str:
    return "clone." + codename.replace("-", "_")


def _teardown_command() -> str:
    """How a kit's verify.sh calls Teardown: the checkout's environment, or the interpreter it is installed in."""
    from teardown.resources import CHECKOUT, in_checkout

    if in_checkout():
        return f"cd {shlex.quote(str(CHECKOUT))} && uv run --quiet teardown"
    return f"{shlex.quote(sys.executable)} -m teardown.cli"


def _verify_link(project_root: Path, codename: str) -> Path:
    """Kits name the project through a codenamed link, never by its (possibly real-name) directory."""
    from teardown.resources import state_dir

    link = state_dir() / "verify" / codename
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(project_root, target_is_directory=True)
    return link


def export_android_kit(project_root: Path, out: Path, rel) -> str:
    package = clone_package(rel.codename)
    out.mkdir(parents=True, exist_ok=True)
    (out / "spec.json").write_text(json.dumps(rel.spec, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "README.md").write_text(ANDROID_README.format(
        codename=rel.codename, release=rel.id, package=package, package_path=package.replace(".", "/"),
        contract=rel.spec["testability_contract"]), encoding="utf-8")
    if not (out / "AndroidManifest.xml").exists():
        (out / "AndroidManifest.xml").write_text(ANDROID_MANIFEST.format(package=package, codename=rel.codename),
                                                 encoding="utf-8")
    main = out / "src" / package.replace(".", "/") / "Main.java"
    if not main.exists():
        main.parent.mkdir(parents=True, exist_ok=True)
        main.write_text(ANDROID_MAIN.format(package=package), encoding="utf-8")
    link = _verify_link(project_root, rel.codename)
    verify = out / "verify.sh"
    verify.write_text(f"#!/bin/sh\nset -e\nKIT=$(cd \"$(dirname \"$0\")\" && pwd)\n"
                      f"{_teardown_command()} verify-kit --project {shlex.quote(str(link))} --kit \"$KIT\" "
                      f"--clone android:kit \"$@\"\n", encoding="utf-8")
    verify.chmod(0o755)
    _check_no_real_names(project_root, out)
    return str(out)


class CloneError(ValueError):
    """A problem with the clone itself (build or install output): safe to report to the clean side verbatim."""


def verify_kit(project, kit: Path, clone: str, adapter: dict | None = None, only: str | None = None) -> dict:
    """Verify a clone built from the kit: ``web:kit`` (static site from impl/), ``android:kit`` (APK from the kit's
    manifest and sources, installed on the original's device), ``cli:build:/kit`` (the kit's Dockerfile)."""
    kit = Path(kit).resolve()
    if clone == "web:kit":
        from teardown.drivers.web.driver import LocalSite

        site = LocalSite(kit / "impl", spa=True)
        try:
            return project.verifier().verify("web:" + site.url(""), adapter=adapter, only=only).model_dump(mode="json")
        finally:
            site.close()
    if clone == "android:kit":
        import subprocess
        import tempfile

        from teardown.drivers.android.build import BuildFailed, build_apk, manifest_package
        from teardown.drivers.android.driver import adb_path

        _, serial, _ = project.state.target_spec.split(":", 2)
        try:
            package = manifest_package(kit / "AndroidManifest.xml")
        except BuildFailed as exc:
            raise CloneError(str(exc)) from exc
        if not package.startswith("clone."):
            raise CloneError("the clone's package must start with 'clone.' (it must not replace the original)")
        with tempfile.TemporaryDirectory(prefix="teardown-clone-") as tmp:
            try:
                apk = build_apk(kit, Path(tmp) / "clone.apk")
            except BuildFailed as exc:
                raise CloneError(str(exc)) from exc
            cp = subprocess.run([adb_path(), "-s", serial, "install", "-r", "-t", str(apk)], capture_output=True,
                                text=True, timeout=300)
            if cp.returncode != 0 or "Success" not in cp.stdout:
                # adb's own output about installing the clone's APK (no original's data in it)
                raise CloneError(f"install failed: {(cp.stdout + cp.stderr)[-600:]}")
        options = {k: v for k, v in project.state.target_options.items() if k != "activity"}
        adapter = {**(adapter or {}), "target_options": options}
        verdict = project.verifier().verify(f"android:{serial}:{package}", adapter=adapter, only=only)
        return verdict.model_dump(mode="json")
    if clone in ("cli:build:/kit", "cli:build:kit"):
        return project.verifier().verify(f"cli:build:{kit}", adapter=adapter, only=only).model_dump(mode="json")
    raise PermissionError(f"only clones built from the kit are accepted (web:kit, android:kit, cli:build:/kit), "
                          f"not {clone!r}")


def export_kit(project_root: Path, out: Path, api: str = "") -> str:
    project_root, out = Path(project_root).resolve(), Path(out).resolve()
    rel = load_release(project_root / "releases")
    spec = rel.spec
    state = json.loads((project_root / "project.json").read_text(encoding="utf-8"))
    if state["target_spec"].startswith("web:"):
        return export_web_kit(project_root, out, rel, api)
    if state["target_spec"].startswith("android:"):
        return export_android_kit(project_root, out, rel)
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
    link = _verify_link(project_root, rel.codename)
    verify = out / "verify.sh"
    verify.write_text(VERIFY.format(image=image, teardown=_teardown_command(), project=shlex.quote(str(link))),
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
        if path.is_file() and path.suffix in {".md", ".sh", ".json", ".html", ""}:
            text = path.read_text(encoding="utf-8", errors="replace").casefold()
            hits += [f"{t} in {path.name}" for t in terms if t in text]
    if hits:
        raise RuntimeError(f"clean-room kit leaks real names: {sorted(set(hits))}")
