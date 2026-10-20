"""Phase 0 exit criterion: one feature makes the full trip observe -> gate -> clean -> verdict on the fake driver."""

from __future__ import annotations

import asyncio
import json

import pytest
from mcp import Client

from teardown.demo import run_demo
from teardown.mcp.clean_server import CleanRoom, build_clean_server
from teardown.mcp.observe_server import build_observe_server
from teardown.project import Project


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    return run_demo(tmp_path_factory.mktemp("demo"), log=lambda *_: None)


def test_gate_caught_the_leak_and_the_refined_mapper_released_clean(demo):
    assert demo["draft1_leaks"] == ["i agree to the terms of service and privacy policy"]
    assert demo["release"].report.findings == []


def test_released_spec_contains_no_target_prose_names_or_dirty_ids(demo):
    text = json.dumps(demo["spec"])
    project: Project = demo["project"]
    for leaked in ("Acme", "Terms of Service", "characters or fewer", "Use at least 8", "ev_", project.state.target):
        assert leaked not in text


def test_clean_clone_passes_and_buggy_clone_fails_with_minimal_abstract_counterexample(demo):
    good, bad = demo["good"], demo["bad"]
    assert good["failed"] == 0 and good["inconclusive"] == 0 and good["passed"] > 0
    assert bad["failed"] > 0
    fails = [r for r in bad["results"] if r["status"] == "fail"]
    shortest = min(fails, key=lambda r: len(r["inputs"]))
    assert shortest["inputs"][-1] == "back" and '"Password":"filled"' in shortest["expected"]
    assert '"Password":"empty"' in shortest["observed"]


def test_verdicts_reveal_only_released_vocabulary(demo):
    vocabulary = {o["symbol"] for o in demo["spec"]["spec"]["model"]["outputs"]}
    for verdict in (demo["good"], demo["bad"]):
        for r in verdict["results"]:
            assert r["expected"] is None or r["expected"] in vocabulary


def test_ticket_answer_reached_the_clean_side(demo):
    assert demo["ticket"]["status"] == "answered" and "email-too-long" in demo["ticket"]["answer"]


def test_audit_log_covers_the_whole_trip(demo):
    project: Project = demo["project"]
    kinds = [e["statement"]["predicateType"].split("/")[-2] for e in project.audit.entries()]
    for kind in ("intake", "mapper-version", "model-learned", "claim-probed", "spec-release", "verdict"):
        assert kind in kinds
    assert project.audit.verify() == len(kinds)


def test_mcp_servers_expose_the_expected_tools(demo):
    project: Project = demo["project"]
    room = CleanRoom(project.releases_dir, project.tickets_dir, lambda c, a=None: {"clone": c})

    async def tools(server):
        async with Client(server) as client:
            return {t.name for t in (await client.list_tools()).tools}, client

    async def call_get_spec():
        async with Client(build_clean_server(room)) as client:
            result = await client.call_tool("get_spec", {})
            return result.structured_content

    clean_tools, _ = asyncio.run(tools(build_clean_server(room)))
    observe_tools, _ = asyncio.run(tools(build_observe_server(project)))
    assert clean_tools == {"get_spec", "list_unknowns", "ask_question", "get_ticket", "verify_against_original"}
    assert {"open_target", "learn_flow", "propose_claim", "falsify_claim", "release_spec"} <= observe_tools
    assert not clean_tools & observe_tools
    spec = asyncio.run(call_get_spec())
    assert spec["release"] == demo["release"].id


def test_gate_service_serves_spec_verdicts_and_tickets_over_http(demo):
    from teardown.gate.service import RemoteCleanRoom, serve

    project: Project = demo["project"]

    def verify(clone, adapter=None):
        return project.verifier().verify(clone, adapter=adapter).model_dump(mode="json")

    server = serve(CleanRoom(project.releases_dir, project.tickets_dir, verify), token="s3cret")
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        remote = RemoteCleanRoom(url, "s3cret")
        assert remote.get_spec()["release"] == demo["release"].id
        verdict = remote.verify_against_original("fake:py:teardown.examples.signup_clone:CleanSignup")
        assert verdict["failed"] == 0 and verdict["passed"] > 0
        ticket = remote.ask_question("Does Back keep the email?")
        assert remote.get_ticket(ticket["ticket"])["status"] == "open"
        import urllib.error

        with pytest.raises(urllib.error.HTTPError) as err:
            RemoteCleanRoom(url, "wrong").get_spec()
        assert err.value.code == 401
    finally:
        server.shutdown()
