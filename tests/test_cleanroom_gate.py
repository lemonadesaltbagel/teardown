"""The gate in kit mode: the clean side can only name clones built from the kit."""

from __future__ import annotations

import shutil

import pytest

pytest.importorskip("playwright")

from teardown.cli import _local_room  # noqa: E402
from teardown.drivers.web.driver import EXAMPLES, LocalSite, shutdown_browser  # noqa: E402
from teardown.project import Project  # noqa: E402


def test_kit_gate_verifies_web_kit_and_refuses_other_targets(tmp_path):
    site = LocalSite(EXAMPLES)
    try:
        project = Project(tmp_path / "p")
        project.open_target("web:" + site.url("fetcher.html"), purpose="research")
        project.define_actions({"load": {"op": "click", "role": "button", "name": "Load quotes"}})
        project.check_rules("quotes", [{"statement": "Loading lists the quotes.",
                                        "checks": [{"kind": "outcome", "a": {"actions": ["load"]},
                                                    "expect": {"headings": ["Quotes"]}}]}], workers=1)
        project.release_spec(project.compile_spec("quotes").id)
        kit = tmp_path / "kit"
        (kit / "impl").mkdir(parents=True)
        shutil.copy(EXAMPLES / "fetcher.html", kit / "impl" / "index.html")
        shutil.copy(EXAMPLES / "quotes.json", kit / "impl" / "quotes.json")
        room = _local_room(project, kit=kit)
        verdict = room.verify_against_original("web:kit")
        assert verdict["passed"] >= 1 and verdict["failed"] == 0
        for target in ("fake:py:teardown.examples.signup_clone:CleanSignup", "cli:local", "web:" + site.url("")):
            with pytest.raises(PermissionError):
                room.verify_against_original(target)
    finally:
        site.close()
        shutdown_browser()


def test_gate_service_never_forwards_unexpected_error_text(tmp_path):
    import json
    import urllib.error
    import urllib.request

    from teardown.cleanroom import CloneError
    from teardown.gate.service import serve
    from teardown.mcp.clean_server import CleanRoom

    def verify(clone, adapter=None):
        if clone == "boom":
            raise RuntimeError("no launcher activity for com.example.realname")  # dirty detail
        raise CloneError("javac failed: Main.java:3: error: ';' expected")  # the clone's own output

    server = serve(CleanRoom(tmp_path / "rel", tmp_path / "tickets", verify), "127.0.0.1", 0, "t")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        def post(clone):
            req = urllib.request.Request(f"http://127.0.0.1:{server.server_address[1]}/verify",
                                         data=json.dumps({"clone": clone}).encode(), method="POST",
                                         headers={"Authorization": "Bearer t"})
            try:
                opener.open(req, timeout=10)
            except urllib.error.HTTPError as exc:
                return exc.code, json.loads(exc.read())["error"]

        code, message = post("boom")
        assert code == 500 and "realname" not in message and "infrastructure" in message
        code, message = post("bad-build")
        assert code == 400 and "';' expected" in message
        import pytest

        from teardown.gate.service import GateError, RemoteCleanRoom

        client = RemoteCleanRoom(f"http://127.0.0.1:{server.server_address[1]}", "t", timeout_s=10)
        with pytest.raises(GateError, match="400: javac failed"):  # the clean side sees why, not "Bad Request"
            client.verify_against_original("bad-build")
        with pytest.raises(GateError, match="500: verification could not run"):
            client.verify_against_original("boom")
    finally:
        server.shutdown()
