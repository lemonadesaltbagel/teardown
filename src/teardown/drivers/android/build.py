"""Build an APK from Java sources and a manifest, without Gradle (aapt2 + javac + d8 + zipalign + apksigner).

Used by the gate for Android clones (`android:kit`): the implementer writes ``AndroidManifest.xml`` and
``src/**/*.java`` (UI built in code, no resources); the gate builds, installs and verifies. Compiler errors are
about the clone's own code, so they are returned to the clean side as they are.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


class BuildFailed(ValueError):
    pass


def sdk_paths() -> tuple[Path, Path]:
    sdk = Path(os.environ.get("ANDROID_HOME", Path.home() / "Library/Android/sdk"))
    build_tools = sorted((sdk / "build-tools").glob("*"))
    platforms = sorted((sdk / "platforms").glob("android-*"), key=lambda p: int(p.name.split("-")[1]))
    if not build_tools or not platforms:
        raise FileNotFoundError(f"Android SDK build-tools/platforms not found under {sdk}")
    return build_tools[-1], platforms[-1] / "android.jar"


def manifest_package(manifest: Path) -> str:
    m = re.search(r'package="([A-Za-z0-9_.]+)"', manifest.read_text(encoding="utf-8"))
    if not m:
        raise BuildFailed("AndroidManifest.xml has no package attribute")
    return m.group(1)


def _keystore() -> Path:
    path = Path(os.environ.get("TEARDOWN_CACHE", Path.home() / ".cache" / "teardown")) / "android-debug.keystore"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["keytool", "-genkeypair", "-keystore", str(path), "-storepass", "android", "-keypass",
                        "android", "-alias", "debug", "-keyalg", "RSA", "-keysize", "2048", "-validity", "10000",
                        "-dname", "CN=Teardown clone"], check=True, capture_output=True)
    return path


def _run(cmd: list[str], what: str) -> None:
    cp = subprocess.run(cmd, capture_output=True, text=True)
    if cp.returncode != 0:
        raise BuildFailed(f"{what} failed:\n{(cp.stderr or cp.stdout)[-4000:]}")


def build_apk(root: Path, out_apk: Path) -> Path:
    """``root`` holds AndroidManifest.xml and src/; returns the signed APK."""
    root = Path(root)
    manifest = root / "AndroidManifest.xml"
    sources = sorted(str(p) for p in (root / "src").rglob("*.java"))
    if not manifest.exists() or not sources:
        raise BuildFailed("the kit needs AndroidManifest.xml and at least one src/**/*.java file")
    bt, jar = sdk_paths()
    with tempfile.TemporaryDirectory(prefix="teardown-apk-") as tmp:
        t = Path(tmp)
        (t / "classes").mkdir()
        (t / "dex").mkdir()
        _run([str(bt / "aapt2"), "link", "-o", str(t / "unsigned.apk"), "--manifest", str(manifest), "-I", str(jar)],
             "aapt2 link (manifest)")
        _run(["javac", "--release", "11", "-cp", str(jar), "-d", str(t / "classes"), *sources], "javac")
        classes = [str(p) for p in (t / "classes").rglob("*.class")]
        _run([str(bt / "d8"), "--lib", str(jar), "--min-api", "26", "--output", str(t / "dex"), *classes], "d8")
        shutil.copy(t / "unsigned.apk", t / "app.apk")
        _run(["zip", "-q", "-j", str(t / "app.apk"), str(t / "dex" / "classes.dex")], "zip")
        _run([str(bt / "zipalign"), "-f", "4", str(t / "app.apk"), str(t / "aligned.apk")], "zipalign")
        out_apk.parent.mkdir(parents=True, exist_ok=True)
        _run([str(bt / "apksigner"), "sign", "--ks", str(_keystore()), "--ks-pass", "pass:android", "--out",
              str(out_apk), str(t / "aligned.apk")], "apksigner")
    return out_apk
