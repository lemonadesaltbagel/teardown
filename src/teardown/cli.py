"""``teardown`` command line: run the MCP servers (stdio), the demo, or an audit check."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="teardown", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    observe = sub.add_parser("observe", help="run the dirty-side observe MCP server on stdio")
    observe.add_argument("--project", required=True, type=Path)

    clean = sub.add_parser("clean", help="run the clean-side MCP server on stdio")
    clean.add_argument("--project", required=True, type=Path,
                       help="Phase 0: the verifier runs in-process, so the clean server needs the project path. "
                            "Phase 3 replaces this with a verifier endpoint and a releases directory only.")

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

    bench = sub.add_parser("bench-jq", help="score an implementation on the hidden jq test suite")
    bench.add_argument("--image", required=True)
    bench.add_argument("--cmd", default="jq", help="command name inside the image")
    bench.add_argument("--reference-image", default="teardown/jq-original",
                       help="only cases this reference passes count (pinned denominator)")
    bench.add_argument("--tag", default="jq-1.7.1")
    bench.add_argument("--suite", type=Path, default=Path("bench/jq/hidden/jq.test"))

    audit = sub.add_parser("audit-verify", help="verify a project's audit hash chain")
    audit.add_argument("--project", required=True, type=Path)

    args = parser.parse_args(argv)

    if args.command == "observe":
        from teardown.mcp.observe_server import build_observe_server
        from teardown.project import Project

        build_observe_server(Project(args.project)).run()
    elif args.command == "clean":
        from teardown.mcp.clean_server import CleanRoom, build_clean_server
        from teardown.project import Project

        project = Project(args.project)
        def verify(clone, adapter=None):
            return project.verifier().verify(clone, adapter=adapter).model_dump(mode="json")

        room = CleanRoom(project.releases_dir, project.tickets_dir, verify)
        build_clean_server(room).run()
    elif args.command == "demo":
        import shutil

        from teardown.demo import run_demo

        if args.project.exists():
            shutil.rmtree(args.project)
        run_demo(args.project)
    elif args.command == "verify":
        import json

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

        print(export_kit(args.project, args.out))
    elif args.command == "bench-jq":
        import json

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
    elif args.command == "audit-verify":
        from teardown.audit.log import AuditLog

        print(f"ok: {AuditLog(args.project / 'audit.jsonl').verify()} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
