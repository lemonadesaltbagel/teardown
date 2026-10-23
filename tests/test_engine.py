from __future__ import annotations

import pytest

from teardown.audit.log import AuditLog
from teardown.core.model import Evidence
from teardown.drivers.policy import PROHIBITED_CATEGORIES, HardRefusal
from teardown.engine.claims import ClaimLedger
from teardown.engine.learner import learn
from teardown.examples.signup import ACTIONS
from teardown.spec.efsm import EFSM
from teardown.spec.export import to_ears, to_xstate


def test_session_records_evidence_traces_and_unavailable_actions(signup_session, workspace):
    outputs, evidence, conflicts = signup_session.run(["submit", "email_ok", "next"])
    assert outputs[0] == "NA" and '"screen":"step2"' in outputs[2]
    assert len(evidence) == 3 and not conflicts
    assert workspace.get(evidence[0], Evidence).payload == {"unavailable": "submit"}
    cached, ev2, _ = signup_session.run(["submit", "email_ok", "next"])
    assert cached == outputs and ev2 == []  # served from the observation tree


@pytest.mark.parametrize("category", sorted(PROHIBITED_CATEGORIES))
def test_hard_refusals_cannot_be_used(signup_session, category):
    with pytest.raises(HardRefusal):
        signup_session.step("anything", category=category)


def test_learning_recovers_ground_truth(signup_session, signup_truth):
    result = learn(signup_session, ACTIONS, name="signup", algorithm="kv")
    assert len(result.model.states) == signup_truth(signup_session.mapper)
    assert "not proven" in result.completeness and not result.conflicts


def test_small_oracle_budget_can_silently_miss_states(signup_session, signup_truth):
    """The spike's main finding, kept as a regression test: under-budgeted oracles return incomplete models."""
    result = learn(signup_session, ACTIONS, name="signup", algorithm="lsharp", walks_per_state=2, walk_len=3)
    assert len(result.model.states) < signup_truth(signup_session.mapper)


def test_efsm_interpreter_and_exports(signup_session):
    model = learn(signup_session, ACTIONS, name="signup").model
    model = EFSM.model_validate(model.model_dump())  # round-trips through JSON form
    trace = ["email_ok", "next", "pw_ok", "next", "terms", "submit"]
    observed = signup_session.run(trace, use_cache=False)[0]
    assert model.run(trace) == observed
    assert model.accepts(trace, observed) == (True, None)
    assert model.accepts(trace, observed[:-1] + ["NA"]) == (False, 5)
    assert len(model.transition_cover()) == len(model.states) * len(ACTIONS)
    xs = to_xstate(model)
    assert xs["initial"] == model.initial and set(xs["states"]) == {s.name for s in model.states}
    assert any("shall not offer 'submit'" in line for line in to_ears(model))


def test_claims_are_corroborated_or_falsified_by_fresh_probes(signup_session, workspace, tmp_path):
    ledger = ClaimLedger(workspace, AuditLog(tmp_path / "audit.jsonl"))
    common = {"feature": "signup", "reference": signup_session.target, "mapper": signup_session.mapper.id}
    true_claim = ledger.propose(kind="refusal", statement="no submit before terms",
                                inputs=["email_ok", "next", "pw_ok", "next", "submit"],
                                expect=[None, None, None, None, "NA"], **common)
    false_claim = ledger.propose(kind="refusal", statement="submit is never offered",
                                 inputs=["email_ok", "next", "pw_ok", "next", "terms", "submit"],
                                 expect=[None, None, None, None, None, "NA"], **common)
    assert ledger.falsify(true_claim.id, signup_session).status == "corroborated"
    falsified = ledger.falsify(false_claim.id, signup_session)
    assert falsified.status == "falsified" and falsified.contradicting == 3 and falsified.counterexamples
    assert AuditLog(tmp_path / "audit.jsonl").verify() == 4


def test_field_outcomes_mask_the_typed_value_and_its_slug_but_not_short_values():
    from teardown.engine.fieldprobe import outcome

    a = outcome({"path": "/article/hello-world", "headings": ["Hello World"],
                 "network": ["GET /api/articles/hello-world 200"]}, "Hello World")
    b = outcome({"path": "/article/another-title", "headings": ["Another Title"],
                 "network": ["GET /api/articles/another-title 200"]}, "Another Title")
    assert a == b  # two accepted titles have the same outcome once their echo is masked
    assert outcome({"text": ["a cat"]}, "a")["text"] == ["a cat"]


def test_subset_expectations_are_subsets_at_every_level():
    import json

    from teardown.engine.mapper import symbol_matches

    observed = json.dumps({"controls": {"button:Go": ["disabled"], "textbox:Name": ["empty"]}, "text": ["Hi"]})
    assert symbol_matches(observed, json.dumps({"controls": {"button:Go": ["disabled"]}}), "subset")
    assert not symbol_matches(observed, json.dumps({"controls": {"button:Go": []}}), "subset")
    assert not symbol_matches(observed, json.dumps({"controls": {"button:Stop": ["disabled"]}}), "subset")
    assert symbol_matches(observed, json.dumps({"alerts": []}), "subset")
    assert symbol_matches(observed, json.dumps({"controls": {"button:Delete": None}}), "subset")  # must be absent
    assert not symbol_matches(observed, json.dumps({"controls": {"button:Go": None}}), "subset")
    assert not symbol_matches(observed, json.dumps({"controls": {}}), "subset")  # {} means none, not anything
    assert symbol_matches(json.dumps({"text": ["Hi"]}), json.dumps({"controls": {}}), "subset")


def test_server_side_refusals_are_told_apart_from_acceptance():
    from teardown.engine.fieldprobe import judge, outcome

    good = outcome({"path": "/specimens/SF-1", "status": ["Quarantined."],
                    "network": ["POST /api/specimens/{id}/quarantine 200"]})
    refused, _ = judge(good)
    too_long = {"path": "/specimens/SF-1", "network": ["POST /api/specimens/{id}/quarantine 422"],
                "dialogs": ["dialog:Quarantine SF-1"], "controls": {"textbox:Reason": ["filled", "invalid"]}}
    assert outcome(too_long)["flagged"] == ["textbox:Reason"] and outcome(too_long)["dialogs"]
    assert refused(outcome(too_long))
    for signal in ({"network": ["POST /api/specimens/{id}/quarantine 422"]},
                   {"dialogs": ["dialog:Quarantine SF-1"], "status": ["Quarantined."],
                    "network": ["POST /api/specimens/{id}/quarantine 200"]}):
        assert refused(outcome({"path": "/specimens/SF-1", **signal}))  # each signal alone is a refusal
    assert not refused(good)
