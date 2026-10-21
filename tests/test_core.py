from __future__ import annotations

import pytest
from pydantic import ValidationError

from teardown.core.confidence import violation_upper_bound
from teardown.core.model import Claim, ClaimIdentity, Evidence, MapperRule, MapperVersion, ObservationTier, TraceCheck
from teardown.core.obstree import ObservationTree
from teardown.core.store import Workspace
from teardown.engine.mapper import Mapper


def _ev(seq=0, payload=None, tier=ObservationTier.BEHAVIOR):
    return Evidence(session="s", seq=seq, target="tgt_x", driver="fake", operation="step",
                    payload=payload if payload is not None else {"a": 1}, tier=tier)


def test_content_ids_are_stable_and_tamper_evident():
    a, b = _ev(), _ev()
    assert a.id == b.id and a.id.startswith("ev_")
    data = a.model_dump()
    data["payload"] = {"a": 2}
    with pytest.raises(ValidationError):
        Evidence(**data)


def test_implementation_tier_is_never_captured():
    with pytest.raises(ValidationError):
        _ev(tier=ObservationTier.IMPLEMENTATION)


def test_trace_check_lengths_must_match():
    with pytest.raises(ValidationError):
        TraceCheck(inputs=["a", "b"], expect=[None])


def test_workspace_packs_evidence_dedupes_payloads_and_reloads(tmp_path):
    ws = Workspace(tmp_path)
    ids = [ws.put(_ev(seq=i, payload={"same": "payload"})) for i in range(5)]
    assert ws.get(ids[3], Evidence).payload == {"same": "payload"}
    assert len((tmp_path / "packs" / "blobs.jsonl").read_text().splitlines()) == 1
    reopened = Workspace(tmp_path)
    assert reopened.has(ids[0]) and reopened.get(ids[4], Evidence).seq == 4
    assert [e.seq for e in reopened.iter_objects("ev", Evidence)] == [0, 1, 2, 3, 4]


def test_workspace_rejects_malformed_ids(tmp_path):
    ws = Workspace(tmp_path)
    with pytest.raises(ValueError):
        ws.get("../etc/passwd", Evidence)


def test_corpus_collects_each_string_once(tmp_path):
    ws = Workspace(tmp_path)
    for i in range(3):
        ws.put(_ev(seq=i, payload={"msg": "Email address is required.", "n": i}))
    assert ws.corpus().count("Email address is required.") == 1


def test_claim_ledger_round_trip(tmp_path):
    ws = Workspace(tmp_path)
    identity = ClaimIdentity(feature="f", kind="refusal", statement="s", check=TraceCheck(inputs=["x"], expect=["NA"]),
                             reference="tgt", mapper="map")
    ws.save_claims({identity.id: Claim(identity=identity, probes=2, confirming=2)})
    assert ws.load_claims()[identity.id].confirming == 2


def test_observation_tree_caches_and_reports_conflicts():
    tree = ObservationTree("map_x")
    assert tree.insert(["a", "b"], ["1", "2"]) == []
    assert tree.lookup(["a"]) == ["1"] and tree.lookup(["a", "c"]) is None
    conflicts = tree.insert(["a", "b"], ["1", "3"])
    assert len(conflicts) == 1 and conflicts[0].inputs == ("a", "b") and conflicts[0].observed == "3"


def test_mapper_ops_are_deterministic_and_semantic():
    version = MapperVersion(target="t", rules=[
        MapperRule(path="heading", op="drop"),
        MapperRule(path="fields.*", op="classify", classes=[(r"^$", "empty")], default="filled"),
        MapperRule(path="box.*", op="rename", value="terms"),
        MapperRule(path="token", op="mask", value="<id>"),
    ])
    mapper = Mapper(version)
    obs = {"heading": "Hello Acme", "fields": {"Email": "x@y"}, "box": {"I agree to it all": True}, "token": "a1b2"}
    symbol = mapper.symbol(obs)
    assert symbol == '{"box":{"terms":true},"fields":{"Email":"filled"},"token":"<id>"}'
    assert mapper.symbol(obs) == symbol and obs["heading"] == "Hello Acme"  # input not mutated
    assert Mapper(version).id == version.id == MapperVersion(**version.model_dump()).id


def test_violation_bound_matches_rule_of_three():
    assert violation_upper_bound(0, 0) == 1.0
    assert abs(violation_upper_bound(100, 0) - 0.0295) < 0.001  # ~3/n
    assert violation_upper_bound(10, 5) > violation_upper_bound(10, 1) > violation_upper_bound(10, 0)


def test_audit_accepts_lists_of_subjects(tmp_path):
    from teardown.audit.log import AuditLog

    log = AuditLog(tmp_path / "audit.jsonl")
    entry = log.append("x", {"claims": ["clm_" + "a" * 64, "clm_" + "b" * 64]}, {})
    assert [s["name"] for s in entry["statement"]["subject"]] == ["claims[0]", "claims[1]"]
    assert log.verify() == 1
