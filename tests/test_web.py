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
    from teardown.drivers.web.driver import shutdown_browser

    s = LocalSite(EXAMPLES)
    yield s
    s.close()
    shutdown_browser()


def _act(**params):
    return Action(name="adhoc", params=params)


def test_driver_observes_behavior_tier_only(site):
    d = WebDriver("web:" + site.url("signup_a.html"))
    try:
        obs = d.reset()
        assert set(obs) == {"path", "aria", "form", "network", "api_shapes"} and "<script" not in json.dumps(obs)
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


def test_web_rules_relations(site, tmp_path):
    project = Project(tmp_path / "p")
    project.open_target("web:" + site.url("signup_a.html"), purpose="research")
    project.define_actions(ACTIONS)
    to_terms = ["email_ok", "next", "pw_ok", "next"]
    rules = [{"statement": "Going back from the terms step and forward again keeps the step's state.",
              "checks": [{"kind": "same", "a": {"actions": to_terms}, "b": {"actions": [*to_terms, "back", "next"]},
                          "keys": ["controls"]}]},
             {"statement": "Submitting is impossible before agreeing.", "kind": "refusal",
              "checks": [{"kind": "outcome", "a": {"actions": [*to_terms, "submit"]}, "expect": {"value": "x"}}]}]
    result = project.check_rules("signup", rules, workers=1)
    assert [r["status"] for r in result["rules"]] == ["corroborated", "falsified"]
    project.release_spec(project.compile_spec("signup").id)
    verifier = project.verifier()
    assert verifier.verify("web:" + site.url("signup_a.html"), repeats=1).failed == 0
    variant = verifier.verify("web:" + site.url("signup_b.html"), repeats=1)  # b clears the password on Back
    assert variant.failed == 1 and variant.results[0].note == "relation violated"


def test_fault_injection_reveals_error_handling_and_query_strings_are_kept(site):
    d = WebDriver("web:" + site.url("fetcher.html"))
    try:
        load = _act(op="click", role="button", name="Load quotes")
        d.reset()
        healthy = web_aria(d.step(load), {})
        assert healthy["network"] == ["GET /quotes.json?page=1 200"] and "first" in healthy["text"]
        outcomes = {}
        for mode, extra in (("status", {"status": 503}), ("abort", {}), ("malformed", {})):
            d.reset()
            d.step(_act(op="fault", fault={"path": "/quotes.json", "mode": mode, **extra}))
            outcomes[mode] = web_aria(d.step(load), {}).get("alerts")
        assert outcomes == {"status": ["Server error 503"], "abort": ["Offline"], "malformed": ["Unreadable reply"]}
    finally:
        d.close()


def test_hang_fault_exposes_pending_state_until_release(site):
    d = WebDriver("web:" + site.url("fetcher.html"))
    try:
        d.reset()
        d.step(_act(op="fault", fault={"path": "/quotes.json", "mode": "hang"}))
        pending = web_aria(d.step(_act(op="click", role="button", name="Load quotes")), {})
        assert "Loading…" in pending["text"] and pending["controls"]["button:Load quotes"] == ["disabled"]
        assert "network" not in pending  # held, not answered
        done = web_aria(d.step(_act(op="fault", fault={"mode": "release", "then": "status", "status": 502})), {})
        assert done["alerts"] == ["Server error 502"] and done["controls"]["button:Load quotes"] == []
        again = web_aria(d.step(_act(op="click", role="button", name="Load quotes")), {})  # the hang is gone
        assert again["network"] == ["GET /quotes.json?page=1 200"]
        d.reset()  # releasing with 'continue' lets the held call reach the server
        d.step(_act(op="fault", fault={"path": "/quotes.json", "mode": "hang"}))
        d.step(_act(op="click", role="button", name="Load quotes"))
        done = web_aria(d.step(_act(op="fault", fault={"mode": "release", "then": "continue"})), {})
        assert done["network"] == ["GET /quotes.json?page=1 200"] and "first" in done["text"]
    finally:
        d.close()


def test_contract_selectors_tell_empty_structure_from_absence(site):
    contract = {"source": "fetcher markup contract (public)", "selectors": [".quotes-panel", "#list li", ".nope"]}
    d = WebDriver("web:" + site.url("fetcher.html"), contract_selectors=contract)
    try:
        start = web_aria(d.reset(), {})
        assert start["contract"] == {"#list li": "absent", ".nope": "absent", ".quotes-panel": "empty"}
        d.step(_act(op="fault", fault={"path": "/quotes.json", "mode": "abort"}))
        failed = web_aria(d.step(_act(op="click", role="button", name="Load quotes")), {})
        assert failed["contract"][".quotes-panel"] == "empty"
        d.reset()
        loaded = web_aria(d.step(_act(op="click", role="button", name="Load quotes")), {})
        assert loaded["contract"] == {"#list li": "content", ".nope": "absent", ".quotes-panel": "content"}
    finally:
        d.close()
    with pytest.raises(ValueError):
        WebDriver("web:" + site.url("fetcher.html"), contract_selectors={"selectors": [".x"]})  # no public source


def test_contract_rules_release_and_catch_a_clone_that_drops_the_empty_wrapper(tmp_path):
    original = (EXAMPLES / "fetcher.html").read_text()
    root = tmp_path / "site"
    root.mkdir()
    (root / "fetcher.html").write_text(original)
    (root / "quotes.json").write_text((EXAMPLES / "quotes.json").read_text())
    # the clone removes the panel when loading fails: same accessibility view, different structure
    (root / "clone.html").write_text(original.replace(
        "err.textContent = 'Offline'; err.hidden = false;",
        "err.textContent = 'Offline'; err.hidden = false; document.querySelector('.quotes-panel').remove();"))
    site = LocalSite(root)
    try:
        project = Project(tmp_path / "p")
        contract = {"source": "fetcher markup contract (public)", "selectors": [".quotes-panel"]}
        project.open_target("web:" + site.url("fetcher.html"), purpose="research",
                            target_options={"contract_selectors": contract})
        project.define_actions({"offline": {"op": "fault", "fault": {"path": "/quotes.json", "mode": "abort"}},
                                "load": {"op": "click", "role": "button", "name": "Load quotes"}})
        rules = [{"statement": "A failed load keeps the quotes panel, empty.",
                  "checks": [{"kind": "outcome", "a": {"actions": ["offline", "load"]},
                              "expect": {"contract": {".quotes-panel": "empty"}}}]}]
        assert [r["status"] for r in project.check_rules("quotes", rules, workers=1)["rules"]] == ["corroborated"]
        rel = project.release_spec(project.compile_spec("quotes").id)
        assert rel.spec["markup_contract"] == contract and "markup_contract" in rel.spec["testability_contract"]
        verifier = project.verifier()
        assert verifier.verify("web:" + site.url("fetcher.html"), repeats=1).failed == 0
        assert verifier.verify("web:" + site.url("clone.html"), repeats=1).failed == 1
    finally:
        site.close()


def test_profile_overrides_reach_the_driver():
    from teardown.project import open_driver

    d = open_driver("web:http://127.0.0.1:9/", None, {"profile": {"asset_hosts": ["cdn.example"]}})
    assert d.profile.asset_hosts == ["cdn.example"] and d.profile.block_external


def test_clock_dates_are_flagged_as_unknown_until_masked(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    (root / "post.html").write_text('<!doctype html><html lang="en"><body><main><h1>Post</h1>'
                                    "<p>Published October 20, 2026</p></main></body></html>")
    site = LocalSite(root)
    try:
        project = Project(tmp_path / "p")
        project.open_target("web:" + site.url("post.html"), purpose="research")
        project.define_actions({"stay": {"op": "goto", "value": "post.html"}})
        rules = [{"statement": "The post shows its date.",
                  "checks": [{"kind": "outcome", "a": {"actions": ["stay"]},
                              "expect": {"text": ["Published October 20, 2026"]}}]}]
        project.check_rules("post", rules, workers=1)
        draft = project.compile_spec("post")
        assert any("calendar dates" in u.identity.question for u in draft.unknowns)
        project.set_mapper(params={"mask_dates": True})  # rules are kept, dates become <date>
        project.check_rules("post", [{**rules[0], "checks": [{**rules[0]["checks"][0],
                                                              "expect": {"text": ["Published <date>"]}}]}], workers=1)
        assert not any("calendar dates" in u.identity.question for u in project.compile_spec("post").unknowns)
        assert web_aria({"aria": '- paragraph: Published October 20, 2026', "path": "/"},
                        {"mask_dates": True})["text"] == ["Published <date>"]
    finally:
        site.close()


def test_blocked_hosts_are_reported(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    (root / "cdn.html").write_text('<!doctype html><html lang="en"><head>'
                                   '<link rel="stylesheet" href="https://cdn.invalid/icons.css"></head>'
                                   "<body><main><h1>Icons</h1></main></body></html>")
    site = LocalSite(root)
    try:
        project = Project(tmp_path / "p")
        project.open_target("web:" + site.url("cdn.html"), purpose="research")
        assert project.blocked_hosts() == [{"host": "cdn.invalid", "type": "stylesheet"}]
    finally:
        site.close()


def test_api_contract_folds_declared_templates_and_query_values():
    from teardown.project import _contract_path

    templates = ["/api/articles/feed", "/api/articles/{slug}", "/api/articles/{slug}/comments"]
    assert _contract_path("/api/articles/my-post-1a2b3c4d", templates) == "/api/articles/{slug}"
    assert _contract_path("/api/articles/feed?limit=10&offset=0", templates) == "/api/articles/feed?limit={}&offset={}"
    assert _contract_path("/api/articles/x/comments", templates) == "/api/articles/{slug}/comments"
    assert _contract_path("/api/tags", templates) == "/api/tags"


def test_fault_path_globs_respect_segments():
    from teardown.drivers.web.driver import path_glob

    article = path_glob("/api/articles/*")
    assert article("/api/articles/my-post") and not article("/api/articles/my-post/comments")
    assert path_glob("/api/**")("/api/articles/x/comments") and path_glob("/quotes.json")("/quotes.json")


def test_rule_checks_with_unknown_keys_are_rejected_not_passed_vacuously(site, tmp_path):
    project = Project(tmp_path / "p")
    project.open_target("web:" + site.url("fetcher.html"), purpose="research")
    project.define_actions({"load": {"op": "click", "role": "button", "name": "Load quotes"},
                            "stay": {"op": "goto", "value": "fetcher.html"}})
    dotted = [{"statement": "Loading keeps the button.",
               "checks": [{"kind": "same", "a": {"actions": ["stay"]}, "b": {"actions": ["load"]},
                           "keys": ["controls.button:Load quotes"]}]}]
    with pytest.raises(ValueError, match="unknown key 'controls.button:Load quotes'"):
        project.check_rules("quotes", dotted, workers=1)
    fine = [{**dotted[0], "checks": [{**dotted[0]["checks"][0], "keys": ["headings"]}]}]
    assert project.check_rules("quotes", fine, workers=1)["rules"][0]["status"] == "corroborated"


def test_reopening_keeps_work_cannot_relax_strict_and_rules_can_be_retracted(site, tmp_path):
    project = Project(tmp_path / "p")
    target = "web:" + site.url("fetcher.html")
    project.open_target(target, purpose="research", strict=True)
    project.define_actions({"load": {"op": "click", "role": "button", "name": "Load quotes"}})
    rule = {"statement": "Loading shows the heading.",
            "checks": [{"kind": "outcome", "a": {"actions": ["load"]}, "expect": {"headings": ["Quotes"]}}]}
    rid = project.check_rules("quotes", [rule], workers=1)["rules"][0]["id"]
    with pytest.raises(PermissionError):
        project.open_target(target, purpose="research", strict=False)
    project.open_target(target, purpose="research", strict=True, target_options={"api_templates": ["/x/{id}"]})
    assert "load" in project.state.actions and "quotes" in project.state.rules
    assert project.retract_rule("quotes", rid, "superseded") == 0
    with pytest.raises(KeyError):
        project.retract_rule("quotes", rid, "again")
