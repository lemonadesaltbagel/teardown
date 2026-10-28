"""``teardown`` command line: run the MCP servers (stdio), the demo, or an audit check."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="teardown", description=__doc__)
    parser.add_argument("--version", action="version", version=f"teardown {_version()}")
    sub = parser.add_subparsers(dest="command", required=True)

    observe = sub.add_parser("observe", help="run the dirty-side observe MCP server (stdio, or HTTP with --port)")
    observe.add_argument("--project", required=True, type=Path)
    observe.add_argument("--port", type=int, help="serve streamable HTTP on this port instead of stdio")
    observe.add_argument("--host", default="127.0.0.1")
    observe.add_argument("--token", help="(HTTP) required bearer token")
    observe.add_argument("--allowed-host", action="append", default=["127.0.0.1", "localhost"],
                         help="(HTTP) Host header values accepted (DNS-rebinding protection)")

    clean = sub.add_parser("clean", help="run the clean-side MCP server on stdio")
    where = clean.add_mutually_exclusive_group(required=True)
    where.add_argument("--gate-url", help="URL of the gate service (the clean side needs nothing else)")
    where.add_argument("--project", type=Path, help="development only: run the verifier in-process")
    clean.add_argument("--token", help="bearer token for the gate service")

    rv = sub.add_parser("remote-verify", help="clean side: ask the gate service to verify a clone")
    rv.add_argument("--gate-url", default=None, help="defaults to $TEARDOWN_GATE_URL")
    rv.add_argument("--token", default=None, help="defaults to $TEARDOWN_GATE_TOKEN")
    rv.add_argument("--clone", required=True, help="e.g. cli:build:/kit")
    rv.add_argument("--max-failures", type=int, default=40)
    rv.add_argument("--adapter", type=Path, help="JSON adapter: {actions, rules} mapping your UI onto the spec")
    rv.add_argument("--only-failed", action="store_true",
                    help="re-run only the tests your build did not pass last time (fast); finish with a full run")

    gate = sub.add_parser("gate-serve", help="serve the verifier/spec/tickets over HTTP for the clean side")
    gate.add_argument("--project", required=True, type=Path)
    gate.add_argument("--host", default="127.0.0.1")
    gate.add_argument("--port", type=int, default=8765)
    gate.add_argument("--token", help="require this bearer token")
    gate.add_argument("--kit", type=Path, help="the clean-room kit directory: only clones built from it are accepted "
                      "(web:kit serves <kit>/impl; cli:build:/kit builds it)")

    demo = sub.add_parser("demo", help="run the scripted observe -> gate -> clean -> verdict round trip")
    demo.add_argument("--project", type=Path, default=Path(".teardown/demo"))

    verify = sub.add_parser("verify", help="verify a clone against the original; prints an abstract verdict")
    verify.add_argument("--project", required=True, type=Path)
    verify.add_argument("--clone", required=True, help="clone target spec, e.g. cli:docker:my/clone-image")
    verify.add_argument("--repeats", type=int, default=1)
    verify.add_argument("--adapter", type=Path, help="clean-side adapter JSON: {actions, rules}")
    verify.add_argument("--max-failures", type=int, default=40, help="failing tests to list (all are counted)")

    export = sub.add_parser("export-clean", help="write the released spec and a clean-room kit to a directory")
    export.add_argument("--project", required=True, type=Path)
    export.add_argument("--out", required=True, type=Path)
    export.add_argument("--api", default="", help="web kits: the backend API base URL the clone should call")

    vw = sub.add_parser("verify-web", help="serve a static web clone and verify it against the original")
    vw.add_argument("--project", required=True, type=Path)
    vw.add_argument("--dist", required=True, type=Path, help="the clone's static build directory")
    vw.add_argument("--adapter", type=Path)
    vw.add_argument("--repeats", type=int, default=1)
    vw.add_argument("--max-failures", type=int, default=40)

    bench = sub.add_parser("bench-jq", help="score an implementation on the hidden jq test suite")
    bench.add_argument("--image", required=True)
    bench.add_argument("--cmd", default="jq", help="command name inside the image")
    bench.add_argument("--reference-image", default="teardown/jq-original",
                       help="only cases this reference passes count (pinned denominator)")
    bench.add_argument("--tag", default="jq-1.7.1")
    bench.add_argument("--suite", type=Path, default=Path("bench/jq/hidden/jq.test"))

    bj = sub.add_parser("bench-jsonl", help="score an implementation on a hidden JSONL CLI suite")
    bj.add_argument("--image", required=True)
    bj.add_argument("--cmd", required=True, help="command name inside the image")
    bj.add_argument("--suite", required=True, type=Path)
    bj.add_argument("--rename", nargs=2, metavar=("FROM", "TO"), help="map the clone's command name in its output")

    audit = sub.add_parser("audit-verify", help="verify a project's audit hash chain")
    audit.add_argument("--project", required=True, type=Path)

    rev = sub.add_parser("review", help="show a draft's gate findings by class, their approvals and coverage gaps")
    rev.add_argument("--project", required=True, type=Path)
    which = rev.add_mutually_exclusive_group(required=True)
    which.add_argument("--draft")
    which.add_argument("--feature", help="compile the feature's current draft and review it")
    rev.add_argument("--json", action="store_true")

    apv = sub.add_parser("approve", help="human at a terminal: approve gate findings or acknowledge coverage gaps")
    apv.add_argument("--project", required=True, type=Path)
    which = apv.add_mutually_exclusive_group(required=True)
    which.add_argument("--draft")
    which.add_argument("--feature")
    apv.add_argument("--by", required=True, help="your name or e-mail (recorded in the audit log)")
    what = apv.add_mutually_exclusive_group(required=True)
    what.add_argument("--class", dest="cls", choices=["expected-output", "interface"])
    what.add_argument("--finding", nargs="+", help="finding ids (fnd_...) from `teardown review`")
    what.add_argument("--coverage", action="store_true", help="acknowledge the feature's current coverage gaps")
    apv.add_argument("--reason", choices=["protocol", "file-format", "public-api", "error-code", "accessibility-name",
                                          "test-oracle", "user-required"], help="why the text is functional")
    apv.add_argument("--kind", default="verbatim", help="finding kind for --class (verbatim, near-verbatim)")
    apv.add_argument("--note", default="")

    eg = sub.add_parser("egress-proxy", help="allowlisting HTTP/CONNECT proxy for the clean zone")
    eg.add_argument("--allow", action="append", default=[], help="host:port the clean zone may reach (repeatable)")
    eg.add_argument("--host", default="0.0.0.0")  # noqa: S104 - listens on the clean network only
    eg.add_argument("--port", type=int, default=3128)
    eg.add_argument("--log", type=Path)

    ap_ = sub.add_parser("api-proxy", help="web targets serving UI and API on one port: an API-only front for "
                         "the clean side (everything outside the given prefixes answers 404)")
    ap_.add_argument("--listen", type=int, required=True, help="local port to listen on")
    ap_.add_argument("--backend", required=True, help="the original's base URL, e.g. http://127.0.0.1:8080")
    ap_.add_argument("--allow", nargs="+", required=True, help="API path prefixes, e.g. /api /auth")

    cr = sub.add_parser("cleanroom", help="enforced clean room on this machine: up | check | shell | down")
    cr.add_argument("action", choices=["up", "check", "shell", "down"])
    cr.add_argument("--project", required=True, type=Path)
    cr.add_argument("--kit", type=Path, help="(up) the exported kit directory")
    cr.add_argument("--api", help="(up) backend API the kit names, e.g. http://127.0.0.1:8000/api")
    cr.add_argument("--allow", action="append", default=[], help="(up) extra host:port for the egress allowlist")
    cr.add_argument("--port", type=int, default=8765, help="(up) gate port on the host")
    cr.add_argument("--clone", default="web:kit", help="(up) web:kit or cli:build:/kit")
    cr.add_argument("--no-model-api", action="store_true", help="(up) do not allow the model API")
    cr.add_argument("--claude-token-file", type=Path,
                    help="(up) file holding a Claude Code OAuth token (`claude setup-token`) for the clean agent")
    cr.add_argument("--original-port", type=int, help="(check) the original's port, probed as unreachable")
    cr.add_argument("shell_cmd", nargs="*", metavar="CMD", help="(shell) command to run instead of bash")

    orr = sub.add_parser("observerroom", help="enforced observer room on this machine: up | check | shell | down")
    orr.add_argument("action", choices=["up", "check", "shell", "down"])
    orr.add_argument("--project", required=True, type=Path)
    orr.add_argument("--workspace", type=Path, help="(up) the observer's scratch directory (mounted at /work)")
    orr.add_argument("--port", type=int, default=8766, help="(up) observe server port on the host")
    orr.add_argument("--no-model-api", action="store_true")
    orr.add_argument("--claude-token-file", type=Path)
    orr.add_argument("--target-port", type=int, action="append", default=[],
                     help="(check) host ports of the target, probed as unreachable")
    orr.add_argument("shell_cmd", nargs="*", metavar="CMD", help="(shell) command to run instead of bash")

    vk = sub.add_parser("verify-kit", help="verify a clone built from a kit (web:kit, android:kit, cli:build:/kit)")
    vk.add_argument("--project", required=True, type=Path)
    vk.add_argument("--kit", required=True, type=Path)
    vk.add_argument("--clone", required=True)
    vk.add_argument("--adapter", type=Path)
    vk.add_argument("--max-failures", type=int, default=40)
    vk.add_argument("--only-failed", action="store_true", help="re-run only the tests the clone did not pass last time")

    rel = sub.add_parser("release", help="release a feature's current draft through the gate")
    rel.add_argument("--project", required=True, type=Path)
    rel.add_argument("--feature", required=True)

    sub.add_parser("install-browser", help="web targets: install the Chromium build that Teardown's Playwright uses")
    sub.add_parser("install-android-agent",
                   help="Android targets: build the on-device observer (needs the Android SDK; without it the driver "
                        "falls back to the slower uiautomator dump, which lacks error text, headings and dialogs)")

    args = parser.parse_args(argv)

    if args.command == "observe":
        from teardown.mcp.observe_server import build_observe_server
        from teardown.project import Project

        server = build_observe_server(Project(args.project))
        if args.port is None:
            server.run()
        else:
            if not args.token:
                print("--token is required for HTTP", file=sys.stderr)
                return 2
            from teardown.mcp.http import serve_http

            serve_http(server, host=args.host, port=args.port, token=args.token, allowed_hosts=args.allowed_host)
    elif args.command == "clean":
        from teardown.mcp.clean_server import build_clean_server
        from teardown.project import Project

        if args.gate_url:
            from teardown.gate.service import RemoteCleanRoom

            build_clean_server(RemoteCleanRoom(args.gate_url, args.token)).run()
        else:
            build_clean_server(_local_room(Project(args.project))).run()
    elif args.command == "gate-serve":
        import time

        from teardown.gate.service import serve
        from teardown.project import Project

        server = serve(_local_room(Project(args.project), kit=args.kit), args.host, args.port, args.token)
        print(f"gate service on http://{args.host}:{server.server_address[1]}", flush=True)
        while True:
            time.sleep(3600)
    elif args.command == "remote-verify":
        import os

        from teardown.gate.service import GateError, RemoteCleanRoom

        room = RemoteCleanRoom(args.gate_url or os.environ["TEARDOWN_GATE_URL"],
                               args.token or os.environ.get("TEARDOWN_GATE_TOKEN"))
        adapter = json.loads(args.adapter.read_text(encoding="utf-8")) if args.adapter else None
        try:
            verdict = room.verify_against_original(args.clone, adapter, "failed" if args.only_failed else None)
        except GateError as exc:  # a refusal, the clone's own build error, or an infrastructure failure
            print(str(exc), file=sys.stderr)
            return 1
        verdict["results"] = [r for r in verdict["results"] if r["status"] != "pass"][: args.max_failures]
        print(json.dumps(verdict, indent=1, ensure_ascii=False))
    elif args.command == "demo":
        import shutil

        from teardown.demo import run_demo

        if args.project.exists():
            shutil.rmtree(args.project)
        run_demo(args.project)
    elif args.command == "verify":
        from teardown.project import Project

        adapter = json.loads(args.adapter.read_text(encoding="utf-8")) if args.adapter else None
        verdict = Project(args.project).verifier().verify(args.clone, repeats=args.repeats, adapter=adapter)
        failing = [r.model_dump(mode="json") for r in verdict.results if r.status != "pass"]
        by_kind: dict[str, int] = {}
        for r in verdict.results:
            if r.status == "fail":
                by_kind[r.kind] = by_kind.get(r.kind, 0) + 1
        print(json.dumps({"release": verdict.release, "passed": verdict.passed, "failed": verdict.failed,
                          "inconclusive": verdict.inconclusive, "failed_by_kind": by_kind,
                          "not_passing": failing[: args.max_failures]}, indent=1, ensure_ascii=False))
    elif args.command == "export-clean":
        from teardown.cleanroom import export_kit

        print(export_kit(args.project, args.out, args.api))
    elif args.command == "verify-web":
        from teardown.drivers.web.driver import LocalSite
        from teardown.project import Project

        site = LocalSite(args.dist, spa=True)
        try:
            adapter = json.loads(args.adapter.read_text(encoding="utf-8")) if args.adapter else None
            verdict = Project(args.project).verifier().verify("web:" + site.url(""), repeats=args.repeats,
                                                             adapter=adapter)
        finally:
            site.close()
        failing = [r.model_dump(mode="json") for r in verdict.results if r.status != "pass"]
        print(json.dumps({"passed": verdict.passed, "failed": verdict.failed, "inconclusive": verdict.inconclusive,
                          "not_passing": failing[: args.max_failures]}, indent=1, ensure_ascii=False))
    elif args.command == "bench-jq":
        from teardown.bench import jqtest
        from teardown.drivers.cli.runner import ContainerRunner

        cases = jqtest.parse(jqtest.fetch(args.tag, args.suite).read_text(encoding="utf-8"))
        ref_runner = ContainerRunner(args.reference_image)
        reference = jqtest.run(ref_runner, "jq", cases)
        ref_runner.close()
        failing_ref = {f["line"] for f in reference.failures}
        pinned = [c for c in cases if c.line not in failing_ref]
        runner = ContainerRunner(args.image)
        report = jqtest.run(runner, args.cmd, pinned)
        runner.close()
        print(json.dumps({"suite": args.tag, "cases": len(cases), "denominator": len(pinned),
                          "reference_passed": reference.passed, "passed": report.passed,
                          "rate": round(report.rate, 4), "first_failures": report.failures[:15]}, indent=1))
    elif args.command == "bench-jsonl":
        import collections

        from teardown.bench import jsonltest
        from teardown.drivers.cli.runner import ContainerRunner

        runner = ContainerRunner(args.image)
        report = jsonltest.run(runner, args.cmd, jsonltest.load(args.suite),
                               rename=tuple(args.rename) if args.rename else None)
        runner.close()
        kinds = collections.Counter(p.split(" ")[0] for f in report.failures for p in f["problems"])
        print(json.dumps({"passed": report.passed, "total": report.total, "rate": round(report.rate, 4),
                          "failure_kinds": kinds, "failed_ids": [f["id"] for f in report.failures]}, indent=1))
    elif args.command == "audit-verify":
        from teardown.audit.log import AuditLog

        print(f"ok: {AuditLog(args.project / 'audit.jsonl').verify()} entries")
    elif args.command == "review":
        return _review(args)
    elif args.command == "approve":
        return _approve(args)
    elif args.command == "api-proxy":
        from teardown.api_proxy import serve as serve_api

        server = serve_api(args.listen, args.backend, args.allow)
        print(f"API-only proxy on http://127.0.0.1:{server.server_port} -> {args.backend} ({' '.join(args.allow)})",
              flush=True)
        server.serve_forever()
    elif args.command == "egress-proxy":
        import time

        from teardown.gate.egress import EgressPolicy
        from teardown.gate.egress import serve as serve_egress

        serve_egress(EgressPolicy(args.allow, args.log), args.host, args.port)
        print(f"egress proxy on {args.host}:{args.port}; allow: {args.allow}", flush=True)
        while True:
            time.sleep(3600)
    elif args.command == "cleanroom":
        from teardown import cleanroom_runtime as rt

        if args.action == "up":
            if not args.kit:
                print("--kit is required for up", file=sys.stderr)
                return 2
            print(json.dumps(rt.up(args.project, args.kit, allow=args.allow, api=args.api, port=args.port,
                                   clone=args.clone, model_api=not args.no_model_api,
                                   claude_token_file=args.claude_token_file), indent=1))
        elif args.action == "check":
            results = rt.check(args.project, args.original_port)
            for r in results:
                print(f"{'ok  ' if r['ok'] else 'FAIL'} {r['probe']}  {r['detail']}")
            return 0 if results and all(r["ok"] for r in results) else 1
        elif args.action == "shell":
            return rt.shell(args.project, args.shell_cmd or None)
        else:
            rt.down(args.project)
    elif args.command == "observerroom":
        from teardown import cleanroom_runtime as rt

        if args.action == "up":
            if not args.workspace:
                print("--workspace is required for up", file=sys.stderr)
                return 2
            print(json.dumps(rt.observer_up(args.project, args.workspace, port=args.port,
                                            model_api=not args.no_model_api,
                                            claude_token_file=args.claude_token_file), indent=1))
        elif args.action == "check":
            results = rt.check(args.project, room="observer", target_ports=args.target_port)
            for r in results:
                print(f"{'ok  ' if r['ok'] else 'FAIL'} {r['probe']}  {r['detail']}")
            return 0 if results and all(r["ok"] for r in results) else 1
        elif args.action == "shell":
            return rt.shell(args.project, args.shell_cmd or None, room="observer")
        else:
            rt.down(args.project, room="observer")
    elif args.command == "verify-kit":
        from teardown.cleanroom import verify_kit
        from teardown.project import Project

        adapter = json.loads(args.adapter.read_text(encoding="utf-8")) if args.adapter else None
        verdict = verify_kit(Project(args.project), args.kit, args.clone, adapter,
                             "failed" if args.only_failed else None)
        verdict["results"] = [r for r in verdict["results"] if r["status"] != "pass"][: args.max_failures]
        print(json.dumps(verdict, indent=1, ensure_ascii=False))
    elif args.command == "install-browser":
        import importlib.util
        import subprocess

        if importlib.util.find_spec("playwright") is None:
            print('web targets need the web extra: pip install "teardown-cleanroom[web]"', file=sys.stderr)
            return 2
        # the interpreter Teardown runs in, so the browser matches its Playwright (uv tool installs, venvs, pipx)
        return subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"]).returncode
    elif args.command == "install-android-agent":
        import shutil
        import subprocess
        import tempfile

        from teardown.drivers.android.driver import AGENT_APK
        from teardown.resources import room_root

        with tempfile.TemporaryDirectory() as tmp:  # build a copy, so the shipped sources stay untouched
            src = Path(tmp) / "android-agent"
            shutil.copytree(room_root() / "deploy" / "android-agent", src, ignore=shutil.ignore_patterns("build"))
            key = AGENT_APK.parent / "debug.keystore"  # one signing key per machine: Android refuses a key change
            if key.exists() and not (src / "debug.keystore").exists():
                shutil.copy2(key, src / "debug.keystore")
            cp = subprocess.run(["sh", str(src / "build.sh")], capture_output=True, text=True)
            if cp.returncode != 0:
                print(cp.stderr[-2000:], file=sys.stderr)
                return cp.returncode
            AGENT_APK.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / "build" / "agent.apk", AGENT_APK)
            if not key.exists():
                shutil.copy2(src / "debug.keystore", key)
        print(AGENT_APK)
        return 0
    elif args.command == "release":
        from teardown.project import Project

        project = Project(args.project)
        rel = project.release_spec(project.compile_spec(args.feature).id)
        print(json.dumps({"release": rel.id, "codename": rel.codename, "mode": rel.mode,
                          "findings": len(rel.report.findings), "approved_by": rel.report.approved_by}, indent=1))
    return 0


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    from teardown.resources import DIST

    try:
        return version(DIST)
    except PackageNotFoundError:
        return "unknown"


def _draft_id(project, args) -> str:
    return args.draft or project.compile_spec(args.feature).id


def _review(args) -> int:
    from teardown.project import Project
    from teardown.spec.draft import SpecDraft

    project = Project(args.project)
    draft_id = _draft_id(project, args)
    draft = project.workspace.get(draft_id, SpecDraft)
    _, report = project.review_spec(draft_id)
    summary = report.summary()
    if draft.feature in project.state.coverage:  # the gaps as they are now, as release will judge them
        project.coverage(draft.feature, record_unknowns=False)
    gaps = project.coverage_gaps(draft.feature)  # rules-only drafts too: release checks them either way
    acknowledged = set((project.state.coverage_approvals.get(draft.feature) or {}).get("gaps", []))
    explained = project.gap_explanations(draft.feature)
    summary.update(draft=draft_id, feature=draft.feature, coverage_gaps=gaps,
                   coverage_unacknowledged=[g for g in gaps if g not in acknowledged],
                   coverage_explanations={g: explained[g] for g in gaps if g in explained},
                   prose=[{"id": f.id, "location": f.location, "matched": f.matched, "approved": bool(f.approval)}
                          for f in report.findings if f.cls == "prose"])
    if args.json:
        print(json.dumps(summary, indent=1, ensure_ascii=False))
        return 0
    print(f"draft {draft_id}  feature {draft.feature!r}  gate mode {summary['mode']}")
    print(f"findings: {summary['findings']}, without approval: {summary['unapproved']}")
    for g in summary["groups"]:
        how = "approve as a class" if g["class_approvable"] else "approve one by one, or rewrite"
        print(f"  {g['cls']:<16} {g['kind']:<14} {g['findings']:>4} findings, {g['approved']:>4} approved  ({how})")
        for ex in g["examples"]:
            print(f"      {ex['id']}  {ex['location']}: {ex['matched']}")
    for f in summary["prose"]:
        print(f"  prose {f['id']}{' (approved)' if f['approved'] else ''}  {f['location']}: {f['matched']}")
    if gaps:
        print(f"coverage gaps: {len(gaps)}, unacknowledged: {len(summary['coverage_unacknowledged'])}, "
              f"unexplained by the observer: {sum(g not in explained for g in gaps)}")
        _print_gaps(summary["coverage_unacknowledged"], explained)
    return 0


def _print_gaps(gaps: list[str], explained: dict[str, str], limit: int = 80) -> None:
    """Unexplained gaps first: those are the ones to ask the observer about."""
    ordered = sorted(gaps, key=lambda g: g in explained)
    for g in ordered[:limit]:
        print(f"  - {g}" + (f"\n      {explained[g]}" if g in explained else "  (no explanation)"))
    if len(ordered) > limit:
        print(f"  ... and {len(ordered) - limit} more (teardown review --json lists them all)")


def _approve(args) -> int:
    """Approvals are a human decision: they need an interactive terminal and a typed confirmation, so an agent
    driving the observer tools cannot grant them to itself."""
    from teardown.project import Project
    from teardown.spec.draft import SpecDraft

    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("teardown approve needs an interactive terminal: approvals are made by a person, not by an agent",
              file=sys.stderr)
        return 2
    project = Project(args.project)
    draft_id = _draft_id(project, args)
    _, report = project.review_spec(draft_id)
    codename = project.state.gate.codename
    if args.coverage:
        feature = args.feature or project.workspace.get(draft_id, SpecDraft).feature
        gaps = project.coverage_gaps(feature)
        print(f"Acknowledge {len(gaps)} coverage gap(s) of {feature!r} (released as unknowns):")
        _print_gaps(gaps, project.gap_explanations(feature))
    else:
        if not args.reason:
            print("--reason is required for findings", file=sys.stderr)
            return 2
        if args.cls:
            covered = [f for f in report.findings if f.cls == args.cls and f.kind == args.kind]
        else:
            covered = [f for f in report.findings if f.id in set(args.finding)]
        print(f"Approve {len(covered)} finding(s) as functional ({args.reason}):")
        for f in covered[:15]:
            print(f"  {f.id}  {f.location}: {f.matched[:100]}")
        if len(covered) > 15:
            print(f"  ... and {len(covered) - 15} more")
    typed = input(f"Type the codename '{codename}' to confirm: ").strip()
    if typed != codename:
        print("not confirmed; nothing recorded", file=sys.stderr)
        return 1
    if args.coverage:
        project.approve_coverage_gaps(feature, args.by, args.note)
    else:
        before = {a.id: a for a in project.state.gate.approvals}
        ids = project.approve_findings(draft_id, args.by, args.reason, finding_ids=args.finding, cls=args.cls,
                                       kind=args.kind, note=args.note)
        print(f"recorded {len(ids)} approval(s)")
        if not ids:  # the same approval already exists (content-addressed): say by whom, so 0 is not alarming
            wanted = {("class", args.cls, args.kind, None)} | {("finding", None, "verbatim", f)
                                                               for f in args.finding or []}
            same = [a for a in before.values() if (a.scope, a.cls, a.kind, a.finding) in wanted]
            who = sorted({a.approved_by for a in same})
            print(f"already approved{' by ' + ', '.join(who) if who else ''}; nothing new to record")
    return 0


def _local_room(project, kit: Path | None = None):
    """The gate's clean-room endpoints. With ``kit``, the clean side can only name clones built from the kit
    (``web:kit``, ``android:kit``, ``cli:build:/kit``; see ``verify_kit``). Any other target spec (a URL, a local
    command, a Python class) is refused."""
    from teardown.mcp.clean_server import CleanRoom

    def verify(clone, adapter=None, only=None):
        if kit is not None:
            from teardown.cleanroom import verify_kit

            return verify_kit(project, kit, clone, adapter, only)
        return project.verifier().verify(clone, adapter=adapter, only=only).model_dump(mode="json")

    return CleanRoom(project.releases_dir, project.tickets_dir, verify)


if __name__ == "__main__":
    sys.exit(main())
