from __future__ import annotations

import json

import pytest

pytest.importorskip("playwright")

from teardown.drivers.base import Action  # noqa: E402
from teardown.drivers.web.driver import EXAMPLES, LocalSite, WebDriver  # noqa: E402
from teardown.engine.abstractions import web_aria  # noqa: E402
from teardown.project import Project  # noqa: E402

ACTIONS = {
    "email_ok": {"op": "fill", "role": "textbox", "name": "Email", "value": "jane.doe@example.com"},
    "pw_ok": {"op": "fill", "role": "textbox", "name": "Password", "value": "correct7horse"},
    "terms": {"op": "click", "role": "checkbox", "name": "Terms", "name_regex": True},
    "next": {"op": "click", "role": "button", "name": "Continue"},
    "back": {"op": "click", "role": "button", "name": "Back"},
    "submit": {"op": "click", "role": "button", "name": "Create account"},
}


@pytest.fixture(scope="module")
def site():
    s = LocalSite(EXAMPLES)
    yield s
    s.close()


def _act(**params):
    return Action(name="adhoc", params=params)


def test_driver_observes_behavior_tier_only(site):
    d = WebDriver("web:" + site.url("signup_a.html"))
    try:
        obs = d.reset()
        assert set(obs) == {"path", "aria", "form"} and "<script" not in json.dumps(obs)
        assert web_aria(obs, {})["headings"] == ["Your email"]
        assert d.step(_act(op="click", role="button", name="Nope")) is None  # absent -> NA
        d.step(_act(op="fill", role="textbox", name="Email", value="jane@example.com"))
        d.step(_act(op="click", role="button", name="Continue"))
        d.step(_act(op="fill", role="textbox", name="Password", value="correct7horse"))
        d.step(_act(op="click", role="button", name="Continue"))
        assert d.step(_act(op="click", role="button", name="Create account")) == "DISABLED"
        abstract = web_aria(d.observe(), {})
        assert abstract["controls"]["checkbox:I agree to the Terms of Service"] == []
    finally:
        d.close()


def test_secrets_and_values_never_reach_symbols(site):
    d = WebDriver("web:" + site.url("signup_a.html"))
    try:
        d.reset()
        obs = d.step(_act(op="fill", role="textbox", name="Email", value="secret.person@example.com"))
        assert "secret.person" not in json.dumps(web_aria(obs, {}))
    finally:
        d.close()


def test_web_claim_release_and_verify_against_variant(site, tmp_path):
    project = Project(tmp_path / "p")
    project.open_target("web:" + site.url("signup_a.html"), purpose="research", real_names=["Acme"])
    project.define_actions(ACTIONS)
    trip = ["email_ok", "next", "pw_ok", "next", "back"]
    observed = json.loads(project.session().run(trip, use_cache=False)[0][-1])
    assert observed["controls"]["textbox:Password"] == ["filled"]
    expect = json.dumps({"controls": observed["controls"]})  # assert the behavior, not the brand or the URL
    claim = project.propose_claim(feature="signup", kind="sequence", statement="Back from the terms step keeps "
                                  "the password.", inputs=trip, expect=[None] * 4 + [expect], match="subset")
    assert project.falsify_claim(claim.id, repeats=2).status == "corroborated"
    rel = project.release_spec(project.compile_spec("signup").id)
    assert "Acme" not in json.dumps(rel.spec) and set(rel.spec["actions"]) == set(ACTIONS)
    verifier = project.verifier()
    same = verifier.verify("web:" + site.url("signup_a.html"), repeats=1)
    variant = verifier.verify("web:" + site.url("signup_b.html"), repeats=1)
    assert same.failed == 0 and same.passed == 1
    assert variant.failed == 1 and variant.results[0].step == 4


def test_field_probing_finds_length_boundary_and_refusal_classes(site, tmp_path):
    project = Project(tmp_path / "p")
    project.open_target("web:" + site.url("signup_a.html"), purpose="research")
    project.define_actions({"next": ACTIONS["next"]})
    result = project.probe_web_field("signup", prefix=[], role="textbox", name="Email", submit="next", kind="email")
    assert result["boundary"] == 40  # signup_a limits email to 40 characters
    assert result["boundary_actions"] == ["fill[Email]=len_at_max", "fill[Email]=len_over_max"]
    claims = {c.identity.statement: c for c in project.ledger.all().values()}
    refused = [s for s in claims if "is refused" in s]
    assert any("email.len_over_max" in s for s in refused) and any("email.empty" in s for s in refused)
    assert any("email.len_at_max" in s and "is accepted" in s for s in claims)
    rel = project.release_spec(project.compile_spec("signup").id)
    variant = project.verifier().verify("web:" + site.url("signup_b.html"), repeats=1)
    assert rel.spec["probe_table"] and variant.failed > 0  # signup_b allows 50 characters
