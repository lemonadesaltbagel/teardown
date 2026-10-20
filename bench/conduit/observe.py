"""Observer script for the self-hosted Conduit target (what an observer agent would do through teardown-observe)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from teardown.drivers.web.driver import LocalSite
from teardown.project import Project

ROOT = Path(__file__).resolve().parents[2]
DIST = ROOT / "refs/rw-angular/dist/angular-conduit/browser"

ACTIONS = {
    "goto_register": {"op": "click", "role": "link", "name": "Sign up"},
    "goto_login": {"op": "click", "role": "link", "name": "Sign in"},
    "user_ok": {"op": "fill", "role": "textbox", "name": "Username", "value": "ada"},
    "email_ok": {"op": "fill", "role": "textbox", "name": "Email", "value": "ada@example.com"},
    "pw_ok": {"op": "fill", "role": "textbox", "name": "Password", "value": "correct-horse-7"},
    "signup": {"op": "click", "role": "button", "name": "Sign up"},
    "signin": {"op": "click", "role": "button", "name": "Sign in"},
}


def main(root: str) -> None:
    site = LocalSite(DIST, spa=True)
    project = Project(root)
    project.open_target("web:" + site.url(""), purpose="research", jurisdiction="EU",
                        real_names=["Conduit", "RealWorld", "Realworld"],
                        target_options={"reset_command": [str(ROOT / "bench/conduit/reset_db.sh")],
                                        "reset_check_url": "http://127.0.0.1:8000/api/articles"})
    project.define_actions(ACTIONS)
    for field, kind, prefix in [("Email", "email", ["goto_register", "user_ok", "pw_ok"]),
                                ("Username", "text", ["goto_register", "email_ok", "pw_ok"]),
                                ("Password", "password", ["goto_register", "user_ok", "email_ok"])]:
        t = time.perf_counter()
        r = project.probe_web_field("signup", prefix=prefix, role="textbox", name=field, submit="signup", kind=kind,
                                    boundary=field != "Password")
        r.pop("nondeterministic", None) if not r.get("nondeterministic") else None
        print(field, round(time.perf_counter() - t, 1), "s", {k: v for k, v in r.items() if k != "table"})
    for c in project.ledger.all().values():
        print(" -", c.identity.kind, c.identity.statement[:170])
    site.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / ".teardown/conduit/project"))
