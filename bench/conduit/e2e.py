"""Run the RealWorld E2E suite (hidden oracle) against a frontend build served on :4200 with the local API."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from teardown.drivers.web.driver import LocalSite

ROOT = Path(__file__).resolve().parents[2]
SUITE = ROOT / "refs/rw-angular"  # holds @playwright/test and the realworld specs submodule


def run(dist: str, grep_invert: str = "@security") -> dict:
    subprocess.run([str(ROOT / "bench/conduit/reset_db.sh")], check=True)
    site = LocalSite(dist, spa=True, port=4200)
    try:
        env = {**os.environ, "API_BASE": "http://127.0.0.1:8000/api", "TEST_MODE": "spa", "CI": ""}
        out = subprocess.run(["bunx", "playwright", "test", "--reporter=json", "--retries=0",
                              "--grep-invert", grep_invert], cwd=SUITE, env=env, capture_output=True, text=True,
                             timeout=3600)
    finally:
        site.close()
    report = json.loads(out.stdout[out.stdout.index("{"):])
    stats = report["stats"]
    failed = []

    def walk(suite, path=""):
        for spec in suite.get("specs", []):
            for t in spec["tests"]:
                if t["results"] and t["results"][-1]["status"] not in ("passed", "skipped"):
                    failed.append(f"{path}{spec['title']}")
        for child in suite.get("suites", []):
            walk(child, f"{path}{child['title']} > ")

    for s in report["suites"]:
        walk(s, f"{s['title']} > ")
    return {"expected": stats["expected"], "unexpected": stats["unexpected"], "skipped": stats["skipped"],
            "flaky": stats.get("flaky", 0), "failed": failed}


if __name__ == "__main__":
    result = run(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "refs/rw-angular/dist/angular-conduit/browser"))
    print(json.dumps(result, indent=1))
