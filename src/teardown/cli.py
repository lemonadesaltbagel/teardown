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
        room = CleanRoom(project.releases_dir, project.tickets_dir,
                         lambda clone: project.verifier().verify(clone).model_dump(mode="json"))
        build_clean_server(room).run()
    elif args.command == "demo":
        import shutil

        from teardown.demo import run_demo

        if args.project.exists():
            shutil.rmtree(args.project)
        run_demo(args.project)
    elif args.command == "audit-verify":
        from teardown.audit.log import AuditLog

        print(f"ok: {AuditLog(args.project / 'audit.jsonl').verify()} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
