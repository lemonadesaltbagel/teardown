"""End-to-end Phase 0 round trip on the fake signup target: observe -> claims -> gate -> clean -> verdict.

This scripts what an observer agent and a clean implementer would do through the two MCP servers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from teardown.core.model import MapperRule
from teardown.examples.signup import signup_mapper
from teardown.mcp.clean_server import CleanRoom
from teardown.project import Project

ALPHABET = ["email_ok", "email_bad", "email_long", "pw_ok", "pw_weak", "terms", "next", "back", "submit", "restart"]
FEATURE = "signup"


def run_demo(root: str | Path, *, walks_per_state: int = 100, walk_len: int = 20, log=print) -> dict[str, Any]:
    project = Project(root)
    _, notes = project.open_target(
        "fake:signup-a", purpose="substitute", jurisdiction="EU", terms_text="(demo terms)", real_names=["Acme"]
    )
    log(f"intake recorded; {len(notes)} warning(s)")

    # 1. First mapper draft. It keeps the terms checkbox's label as a key, which is the target's own prose.
    rules = list(signup_mapper(project.state.target).rules)
    project.set_mapper(rules, note="first draft")
    project.learn(FEATURE, ALPHABET, walks_per_state=walks_per_state, walk_len=walk_len)
    _, report = project.review_spec(project.compile_spec(FEATURE).id)
    leaks = [f.matched for f in report.findings]
    log(f"gate review of draft 1: {len(report.findings)} finding(s): {leaks}")

    # 2. Refine the mapper so the abstraction names the checkbox itself, then re-learn.
    rename = MapperRule(path="checkbox.*", op="rename", value="terms")
    project.set_mapper([*rules[:-1], rename, MapperRule(path="checkbox.*", op="classify",
                        classes=[(r"true", "checked")], default="unchecked")], note="rename terms checkbox")
    record, result = project.learn(FEATURE, ALPHABET, walks_per_state=walks_per_state, walk_len=walk_len)
    log(f"learned {len(record.model.states)} states; {record.completeness}")

    # 3. Claims, stated from what the observer saw, then attacked with fresh probes.
    persist = ["email_ok", "next", "pw_ok", "next", "back"]
    observed = project.session().run(persist, use_cache=False)[0]
    keep_pw = project.propose_claim(
        feature=FEATURE, kind="sequence", strictness="must",
        statement="Going back from the terms step keeps the password the user entered.",
        inputs=persist, expect=[None, None, None, None, observed[-1]],
    )
    no_submit = project.propose_claim(
        feature=FEATURE, kind="refusal", strictness="must",
        statement="Submit is not available until the user agrees to the terms.",
        inputs=["email_ok", "next", "pw_ok", "next", "submit"], expect=[None, None, None, None, "NA"],
    )
    for claim in (keep_pw, no_submit):
        claim = project.falsify_claim(claim.id, repeats=3)
        log(f"claim {claim.identity.kind}: {claim.status} ({claim.confirming}/{claim.probes})")

    # 4. Gate and release.
    draft = project.compile_spec(FEATURE)
    rel = project.release_spec(draft.id)
    log(f"released {rel.id[:16]}… as '{rel.codename}' with {len(rel.report.findings)} finding(s)")

    # 5. Clean side: read the spec, ask a question, verify two implementations.
    room = CleanRoom(
        project.releases_dir,
        project.tickets_dir,
        lambda clone: project.verifier().verify(clone).model_dump(mode="json"),
    )
    spec = room.get_spec()
    ticket = room.ask_question("Is there a maximum email length?")
    project.answer_ticket(ticket["ticket"], "Yes: overly long addresses are refused with the email-too-long alert.")
    good = room.verify_against_original("fake:py:teardown.examples.signup_clone:CleanSignup")
    bad = room.verify_against_original("fake:py:teardown.examples.signup_clone:BuggySignup")
    log(f"clean clone: {good['passed']} pass / {good['failed']} fail / {good['inconclusive']} inconclusive")
    log(f"buggy clone: {bad['passed']} pass / {bad['failed']} fail / {bad['inconclusive']} inconclusive")
    first_fail = next(r for r in bad["results"] if r["status"] == "fail")
    log(f"first failure: {json.dumps({k: first_fail[k] for k in ('inputs', 'step', 'expected', 'observed')})}")

    entries = project.audit.verify()
    log(f"audit chain ok: {entries} entries")
    return {"project": project, "spec": spec, "release": rel, "good": good, "bad": bad, "draft1_leaks": leaks,
            "ticket": room.get_ticket(ticket["ticket"])}
