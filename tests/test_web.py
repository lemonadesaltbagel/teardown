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
        assert set(obs) == {"path", "aria", "form", "network", "api_shapes", "title", "focus", "current",
                            "landmarks", "generated", "descriptions", "flagged", "properties", "focus_named"}
        assert "<script" not in json.dumps(obs)
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


def test_coverage_lists_every_observed_endpoint_by_fault_class(site, tmp_path):
    project = Project(tmp_path / "p")
    project.open_target("web:" + site.url("fetcher.html"), purpose="research")
    project.define_actions({"load": {"op": "click", "role": "button", "name": "Load quotes"},
                            "offline": {"op": "fault", "fault": {"path": "/quotes.json", "mode": "abort"}},
                            "broken": {"op": "fault", "fault": {"path": "/quotes.json", "mode": "malformed"}}})
    project.check_rules("quotes", [{"statement": "Offline loads show an alert.",
                                    "checks": [{"kind": "outcome", "a": {"actions": ["offline", "load"]},
                                                "expect": {"alerts": ["Offline"]}}]},
                                   {"statement": "A malformed reply alone changes nothing on screen.",
                                    "checks": [{"kind": "outcome", "a": {"actions": ["broken"]},
                                                "expect": {"alerts": []}}]}], workers=1)
    report = project.coverage("quotes", record_unknowns=False)
    faults = {k: v for k, v in report["counts"].items() if k.startswith("fault ")}
    # 'broken' is used, but no call to /quotes.json was observed while it was active: no credit
    assert faults == {"fault GET /quotes.json 5xx": 0, "fault GET /quotes.json network": 1,
                      "fault GET /quotes.json malformed": 0}
    with pytest.raises(ValueError, match="define_actions"):
        project.check_rules("quotes", [{"statement": "x", "checks": [
            {"kind": "outcome", "a": {"actions": [{"op": "click", "role": "button", "name": "Load quotes"}]},
             "expect": {"alerts": []}}]}], workers=1)


def test_discover_ui_crawls_screens_defines_actions_and_drives_coverage(site, tmp_path):
    project = Project(tmp_path / "p")
    project.open_target("web:" + site.url("signup_a.html"), purpose="research")
    found = project.discover_ui("signup", max_states=10, max_depth=3)
    assert found["screens"] and found["episodes"] > 0
    assert any(a.startswith("click[button:") for a in found["actions_defined"])
    first = found["screens"][0]
    assert first["fields"]  # the wizard's first step has text fields
    report = project.coverage("signup", record_unknowns=False)
    assert any(i.startswith("field ") for i in report["uncovered"])
    suggestions = project.suggest_probes("signup")
    field = next(s for s in suggestions if s["kind"] == "field")
    assert field["call"]["tool"] == "probe_web_field" and field["call"]["name"]


def test_web_aria_v2_reads_quoted_names_and_table_cells():
    from teardown.engine.abstractions import BUILTINS

    snap = "\n".join([
        "- main:",
        "  - 'heading \"Piece #3: \\\"Vase\\\"\" [level=1]'",
        "  - 'link \"Vase #3\"':",
        "    - /url: /x",
        "  - paragraph: \"Note: done\"",
        "  - table:",
        "    - row \"Clay Stoneware\":",
        "      - rowheader \"Clay\"",
        "      - cell \"Stoneware\"",
    ])
    v2 = BUILTINS["web.aria/v2"]({"aria": snap, "path": "/"}, {})
    assert v2["headings"] == ['Piece #3: "Vase"'] and "link:Vase #3" in v2["controls"]
    assert v2["text"] == ["Note: done", "Clay", "Stoneware"]


def test_coverage_resolves_its_own_unknowns_once_covered(site, tmp_path):
    project = Project(tmp_path / "p")
    project.open_target("web:" + site.url("fetcher.html"), purpose="research")
    project.define_actions({"load": {"op": "click", "role": "button", "name": "Load quotes"}})
    project.coverage("quotes", {"loading": ["Load quotes"]})  # nothing exercised yet -> an unknown
    project.check_rules("quotes", [{"statement": "Loading shows the heading.", "checks": [
        {"kind": "outcome", "a": {"actions": ["load"]}, "expect": {"headings": ["Quotes"]}}]}], workers=1)
    project.coverage("quotes", {"loading": ["Load quotes"]})
    open_gaps = [u for u in project.ledger.unknowns().values()
                 if u.status == "open" and "loading" in u.identity.question]
    assert not open_gaps


def test_web_aria_v2_observes_title_focus_status_dialogs_options_and_current(tmp_path):
    from teardown.engine.abstractions import BUILTINS

    root = tmp_path / "site"
    root.mkdir()
    (root / "page.html").write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Pieces — App</title></head><body>'
        '<nav aria-label="Main"><a href="#a" aria-current="page">Pieces</a><a href="#b">Firings</a></nav>'
        '<label>Clay <select><option>Choose</option><option selected>Stoneware</option></select></label>'
        '<label>Title <input id="t" autofocus></label><div role="status">Piece saved.</div>'
        '<dialog open aria-label="Delete piece?"><button>Delete</button></dialog></body></html>')
    site = LocalSite(root)
    d = WebDriver("web:" + site.url("page.html"))
    try:
        obs = d.reset()
        d.page.focus("#t")
        obs = d.observe()
        v2 = BUILTINS["web.aria/v2"](obs, {})
        assert v2["title"] == "Pieces — App" and v2["focus"] == "textbox:Title"
        assert v2["status"] == ["Piece saved."] and v2["dialogs"] == ["Delete piece?"]
        assert v2["options"] == {"combobox:Clay": ["Choose", "Stoneware [selected]"]}
        assert "current" in v2["controls"]["link:Pieces"] and "current" not in v2["controls"]["link:Firings"]
        v1 = BUILTINS["web.aria/v1"](obs, {})
        assert "title" not in v1 and "status" not in v1  # v1 unchanged
    finally:
        d.close()
        site.close()


def test_history_ops_unclickable_elements_and_undefined_rule_actions(site, tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    (root / "a.html").write_text('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>A</title></head>'
                                 '<body><a href="#main" style="position:absolute;left:-9999px">Skip to content</a>'
                                 '<main id="main"><h1>Page A</h1><a href="b.html">Go to B</a></main></body></html>')
    (root / "b.html").write_text('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>B</title></head>'
                                 '<body><main><h1>Page B</h1></main></body></html>')
    local = LocalSite(root)
    try:
        project = Project(tmp_path / "p")
        project.open_target("web:" + local.url("a.html"), purpose="research")
        project.define_actions({"to_b": {"op": "click", "role": "link", "name": "Go to B"},
                                "back": {"op": "back"}, "reload": {"op": "reload"},
                                "skip": {"op": "click", "role": "link", "name": "Skip to content"}})
        outputs = project.session().run(["to_b", "back", "reload", "skip"], use_cache=False)[0]
        assert [json.loads(o)["headings"] if o != "NA" else "NA" for o in outputs] == [
            ["Page B"], ["Page A"], ["Page A"], "NA"]  # the off-screen skip link is unavailable, not a crash
        with pytest.raises(ValueError, match="undefined actions"):
            project.check_rules("nav", [{"statement": "x", "checks": [
                {"kind": "outcome", "a": {"actions": ["to_c"]}, "expect": {"headings": ["Page C"]}}]}], workers=1)
        project.check_rules("nav", [{"statement": "The link on page A leads to page B.", "checks": [
            {"kind": "outcome", "a": {"actions": ["click[link:Go to B]"]}, "expect": {"headings": ["Page B"]}}]}],
            workers=1)  # a discovery-style name defines itself
        defined = project.action_table()["click[link:Go to B]"]
        assert (defined["op"], defined["role"], defined["name"]) == ("click", "link", "Go to B")
        found = project.discover_ui("nav", max_states=5, max_depth=2)  # the skip link no longer stops the crawl
        assert len(found["screens"]) >= 2
        first = {sc["id"] for sc in found["screens"]}
        again = project.discover_ui("nav", start=["to_b"], max_states=5, max_depth=1)  # another start point
        assert again["screens_total"] >= len(first)  # a second run adds to the inventory, it does not replace it
        with pytest.raises(ValueError, match="claim kind must be one of"):
            project.propose_claim(feature="nav", kind="flow", statement="x", inputs=["to_b"], expect=[None])
        project.check_rules("nav", [{"statement": "The skip link cannot be used by a pointer.", "checks": [
            {"kind": "outcome", "a": {"actions": ["skip"]}, "expect": {"value": "NA"}}]}], workers=1)
        counts = project.coverage("nav", record_unknowns=False)["counts"]
        assert counts["control link:Skip to content"] == 0  # a click that only came back NA exercised nothing
        assert counts["control link:Go to B"] == 1  # the rule above clicked it
    finally:
        local.close()


def test_web_aria_v3_keeps_table_structure_and_description_lists():
    from teardown.engine.abstractions import BUILTINS

    snap = "\n".join([
        '- table "Pieces":', "  - rowgroup:", '    - row "Title Units":', '      - columnheader "Title"',
        '      - columnheader "Units"', "  - rowgroup:", '    - row "Moon jar 4":', '      - cell "Moon jar":',
        '        - link "Moon jar":', "          - /url: /p/2", '      - cell "4"', "- term: Cone",
        '- definition: "10"'])
    v3 = BUILTINS["web.aria/v3"]({"aria": snap, "path": "/"}, {})
    assert v3["tables"] == {"Pieces": {"columns": ["Title", "Units"], "rows": [["Moon jar", "4"]]}}
    assert v3["definitions"] == [["Cone", "10"]] and "link:Moon jar" in v3["controls"]
    assert "tables" not in BUILTINS["web.aria/v2"]({"aria": snap, "path": "/"}, {})  # v2 unchanged


def test_same_named_controls_null_expectations_purpose_errors_and_data_folding(tmp_path):
    import json as _json

    from teardown.engine.discovery import summarize
    from teardown.engine.mapper import symbol_matches
    from teardown.project import _contract_path

    root = tmp_path / "site"
    root.mkdir()
    (root / "p.html").write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>P</title></head><body><main>'
        '<button onclick="document.getElementById(\'d\').showModal()">Delete</button>'
        '<dialog id="d" aria-label="Delete boat?"><button onclick="document.body.dataset.x=1;'
        'document.querySelector(\'h1\').textContent=\'Deleted\';this.closest(\'dialog\').close()">Delete</button>'
        '</dialog><h1>Boat</h1></main></body></html>')
    local = LocalSite(root)
    try:
        project = Project(tmp_path / "p")
        with pytest.raises(ValueError, match="purpose must be one of"):
            project.open_target("web:" + local.url("p.html"), purpose="a long sentence")
        project.open_target("web:" + local.url("p.html"), purpose="research")
        project.define_actions({"open": {"op": "click", "role": "button", "name": "Delete"},
                                "confirm": {"op": "click", "role": "button", "name": "Delete",
                                            "within": {"role": "dialog", "name": "Delete boat?"}},
                                "second": {"op": "click", "role": "button", "name": "Delete", "nth": 5}})
        outputs = project.session().run(["open", "confirm"], use_cache=False)[0]
        assert _json.loads(outputs[-1])["headings"] == ["Deleted"]
        assert project.session().run(["second"], use_cache=False)[0] == ["NA"]  # no sixth match
    finally:
        local.close()
    assert symbol_matches(_json.dumps({"text": ["x"]}), _json.dumps({"focus": None}), "subset")
    assert _contract_path("/api/locks/lock-3/passages/b7", []) == "/api/locks/{id}/passages/{id}"
    assert _contract_path("/api/locks", []) == "/api/locks"
    symbol = {"controls": {"link:Otter": [], "link:Heron": [], "link:Locks": []},
              "tables": {"Boats": {"columns": ["Name"], "rows": [["Otter"], ["Heron"]]}}}
    summary = summarize(symbol)
    assert summary["clickable"] == ["link:Heron", "link:Locks"] and summary["row_links"] == {"Boats": 2}


def test_web_aria_v4_landmark_text_tells_inline_from_block_splits(tmp_path):
    from teardown.engine.abstractions import BUILTINS

    root = tmp_path / "site"
    root.mkdir()
    head = '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>T</title></head><body>'
    (root / "inline.html").write_text(head + '<header><p>Signed in as <strong>Otto</strong> (Skipper)</p></header>'
                                      '<main><section aria-label="Fits"><ul><li>Hollin</li></ul></section></main>'
                                      '</body></html>')
    (root / "split.html").write_text(head + '<header><p>Signed in as</p><p>Otto</p><p>(Skipper)</p></header>'
                                     '<main><section aria-label="Fits"><ul><li>Hollin</li></ul></section></main>'
                                     '</body></html>')
    local = LocalSite(root)
    try:
        symbols = {}
        for page in ("inline", "split"):
            d = WebDriver("web:" + local.url(f"{page}.html"))
            try:
                symbols[page] = BUILTINS["web.aria/v4"](d.reset(), {})
            finally:
                d.close()
        assert symbols["inline"]["landmarks"] == {"banner": "Signed in as Otto (Skipper)", "region:Fits": "Hollin"}
        assert symbols["split"]["landmarks"]["banner"] == "Signed in asOtto(Skipper)"  # conformance now sees it
        assert "landmarks" not in BUILTINS["web.aria/v3"]({"aria": "", "path": "/", "landmarks": {"banner": "x"}}, {})
    finally:
        local.close()


def test_release_requires_coverage_gaps_to_be_exercised_explained_or_accepted(site, tmp_path):
    from teardown.project import CoverageGateBlocked

    project = Project(tmp_path / "p")
    project.open_target("web:" + site.url("fetcher.html"), purpose="research")
    project.define_actions({"load": {"op": "click", "role": "button", "name": "Load quotes"}})
    project.check_rules("quotes", [{"statement": "Loading shows the heading.", "checks": [
        {"kind": "outcome", "a": {"actions": ["load"]}, "expect": {"headings": ["Quotes"]}}]}], workers=1)
    project.coverage("quotes", {"export": ["Export quotes"]})  # never exercised
    draft = project.compile_spec("quotes").id
    with pytest.raises(ValueError, match="neither exercised nor explained"):
        project.release_spec(draft)
    project.release_spec(draft, accept_gaps="the app has no export; documented feature only")
    for gap in project.ledger.unknowns().values():
        if gap.status == "open" and gap.identity.question.startswith("not exercised by any probe or rule:"):
            project.update_unknown(gap.id, "out-of-scope", "not part of this feature")
    assert project.open_coverage_gaps("quotes") == []
    project.release_spec(draft)  # every gap explained: no flag needed
    kinds = [e["statement"]["predicate"] for e in project.audit.entries()
             if e["statement"]["predicateType"].split("/")[-2] == "spec-release"]
    assert kinds[0].get("accept_gaps_reason", "").startswith("the app has no export")

    strict = Project(tmp_path / "s")
    strict.open_target("web:" + site.url("fetcher.html"), purpose="research", strict=True)
    strict.define_actions({"load": {"op": "click", "role": "button", "name": "Load quotes"}})
    strict.check_rules("quotes", [{"statement": "Loading shows the heading.", "checks": [
        {"kind": "outcome", "a": {"actions": ["load"]}, "expect": {"headings": ["Quotes"]}}]}], workers=1)
    with pytest.raises(CoverageGateBlocked):  # rules-only drafts need measured coverage too
        strict.release_spec(strict.compile_spec("quotes").id)


def test_field_probe_reads_refusals_shown_only_as_status_messages(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    (root / "form.html").write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>F</title></head><body><main>'
        '<label>Variety <input id="v"></label><button id="b">Save</button><p role="status" id="s"></p>'
        '<script>document.getElementById("b").onclick=()=>{const v=document.getElementById("v").value;'
        'document.getElementById("s").textContent = v.length > 20 ? "Variety is too long." : "Saved " + v + ".";};'
        '</script></main></body></html>')
    local = LocalSite(root)
    try:
        project = Project(tmp_path / "p")
        project.open_target("web:" + local.url("form.html"), purpose="research")
        project.define_actions({"save": {"op": "click", "role": "button", "name": "Save"}})
        result = project.probe_web_field("variety", prefix=[], role="textbox", name="Variety", submit="save",
                                         kind="text", workers=1)
        assert result["boundary"] == 20
    finally:
        local.close()


def test_web_aria_v5_tells_css_generated_icons_from_literal_ones(tmp_path):
    from teardown.engine.abstractions import BUILTINS

    root = tmp_path / "site"
    root.mkdir()
    head = '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>T</title>'
    (root / "css.html").write_text(head + '<style>.warn::before{content:"\\26A0\\FE0E "}</style></head><body>'
                                   '<table aria-label="Grafts"><tr><td class="warn">Needs partner</td></tr></table>'
                                   '</body></html>')
    (root / "literal.html").write_text(head + '</head><body><table aria-label="Grafts"><tr><td>\u26a0\ufe0e Needs '
                                       'partner</td></tr></table></body></html>')
    local = LocalSite(root)
    try:
        symbols = {}
        for page in ("css", "literal"):
            d = WebDriver("web:" + local.url(f"{page}.html"))
            try:
                symbols[page] = BUILTINS["web.aria/v5"](d.reset(), {})
            finally:
                d.close()
        assert symbols["css"]["generated"] == ["\u26a0\ufe0e|Needs partner|"]  # the space ends the CSS escape
        assert "generated" not in symbols["literal"]  # same accessible name, different page: conformance sees it
    finally:
        local.close()


def test_coverage_lists_data_states_and_session_expiry_until_observed(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    (root / "list.html").write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>L</title></head><body><main>'
        '<label>Password <input type="password"></label><label>Search <input id="q"></label>'
        '<button id="go">Search</button><div id="out"></div><script>'
        'const all=["Bramley","Pippin","Russet"];document.getElementById("go").onclick=()=>{'
        'const q=document.getElementById("q").value;const hits=all.filter(x=>x.includes(q));'
        'document.getElementById("out").innerHTML = hits.length ? "<table aria-label=\'Grafts\'>" + '
        'hits.map(h=>"<tr><td>"+h+"</td></tr>").join("") + "</table>" : "<p>No grafts match.</p>";};'
        '</script></main></body></html>')
    local = LocalSite(root)
    try:
        project = Project(tmp_path / "p")
        project.open_target("web:" + local.url("list.html"), purpose="research")
        project.define_actions({"pw": {"op": "fill", "role": "textbox", "name": "Password", "value": "x"},
                                "q_all": {"op": "fill", "role": "textbox", "name": "Search", "value": ""},
                                "q_one": {"op": "fill", "role": "textbox", "name": "Search", "value": "Pip"},
                                "q_none": {"op": "fill", "role": "textbox", "name": "Search", "value": "zzz"},
                                "go": {"op": "click", "role": "button", "name": "Search"}})
        rule = {"statement": "Searching lists every graft.", "checks": [
            {"kind": "outcome", "a": {"actions": ["q_all", "go"]}, "expect": {"title": "L"}}]}
        project.check_rules("grafts", [rule], workers=1)
        report = project.coverage("grafts", record_unknowns=False)
        assert {"data state: table Grafts: none", "data state: table Grafts: one",
                "session expiry: a signed-in request answered 401"} <= set(report["uncovered"])
        assert "data state: table Grafts: several" not in report["uncovered"]
        kinds = {s["kind"] for s in project.suggest_probes("grafts", limit=50)}
        assert {"data-state", "session"} <= kinds
        project.check_rules("grafts", [
            {"statement": "One match lists one graft.", "checks": [
                {"kind": "outcome", "a": {"actions": ["q_one", "go"]}, "expect": {"title": "L"}}]},
            {"statement": "No match shows a message.", "checks": [
                {"kind": "outcome", "a": {"actions": ["q_none", "go"]}, "expect": {"title": "L"}}]}], workers=1)
        report = project.coverage("grafts", record_unknowns=False)
        assert not {i for i in report["uncovered"] if i.startswith("data state:")}
    finally:
        local.close()


def test_nested_expectations_need_their_keys_and_faults_can_be_cleared(site):
    import json as _json

    from teardown.engine.mapper import symbol_matches

    observed = _json.dumps({"controls": {"button:Save": []}})
    assert symbol_matches(observed, _json.dumps({"controls": {"button:Save": []}}), "subset")
    assert not symbol_matches(observed, _json.dumps({"controls": {"button:Imaginary": []}}), "subset")
    assert symbol_matches(observed, _json.dumps({"alerts": []}), "subset")  # top level: absent means empty
    assert symbol_matches(_json.dumps("NA"), _json.dumps({"value": "NA"}), "subset")

    d = WebDriver("web:" + site.url("fetcher.html"))
    try:
        load = _act(op="click", role="button", name="Load quotes")
        d.reset()
        d.step(_act(op="fault", fault={"path": "/quotes.json", "mode": "status", "status": 503}))
        assert web_aria(d.step(load), {}).get("alerts") == ["Server error 503"]
        d.step(_act(op="fault", fault={"mode": "clear"}))
        assert web_aria(d.step(load), {})["network"] == ["GET /quotes.json?page=1 200"]
    finally:
        d.close()


def test_web_aria_v6_records_dialog_roles_and_accessible_descriptions(tmp_path):
    from teardown.engine.abstractions import BUILTINS

    root = tmp_path / "site"
    root.mkdir()
    head = '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>T</title></head><body><main>'
    body = ('<label>Code <input aria-describedby="code-hint"></label><p id="code-hint">Two letters, three digits.</p>'
            '<button aria-describedby="oil">Light lantern</button><p id="oil">Needs at least 90 ml of oil.</p>')
    (root / "alert.html").write_text(head + body + '<div role="alertdialog" aria-label="Remove HB-102?">'
                                     '<button>Remove</button></div></main></body></html>')
    (root / "plain.html").write_text(head + '<label>Code <input></label><button>Light lantern</button>'
                                     '<div role="dialog" aria-label="Remove HB-102?"><button>Remove</button></div>'
                                     '</main></body></html>')
    local = LocalSite(root)
    try:
        symbols = {}
        for page in ("alert", "plain"):
            d = WebDriver("web:" + local.url(f"{page}.html"))
            try:
                symbols[page] = BUILTINS["web.aria/v6"](d.reset(), {})
            finally:
                d.close()
        assert symbols["alert"]["dialogs"] == ["alertdialog:Remove HB-102?"]
        assert symbols["plain"]["dialogs"] == ["dialog:Remove HB-102?"]
        assert symbols["alert"]["descriptions"] == {"button:Light lantern": "Needs at least 90 ml of oil.",
                                                    "textbox:Code": "Two letters, three digits."}
        assert "descriptions" not in symbols["plain"]
        v5 = BUILTINS["web.aria/v5"]({"aria": '- alertdialog "X"', "path": "/", "descriptions": {"a": "b"}}, {})
        assert v5.get("dialogs") == ["X"] and "descriptions" not in v5  # v5 unchanged
    finally:
        local.close()


def test_web_aria_v7_records_aria_invalid_row_headers_and_named_groups(tmp_path):
    from teardown.engine.abstractions import BUILTINS

    root = tmp_path / "site"
    root.mkdir()
    head = '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>T</title></head><body><main>'
    (root / "th.html").write_text(
        head + '<label>Litres <input aria-invalid="true" value="900"></label>'
        '<table aria-label="Readings"><tr><th>Day</th><th>Litres</th></tr>'
        '<tr><th scope="row">Day 12</th><td>40.0 L</td></tr></table>'
        '<div role="group" aria-label="Net actions"><a href="/e">Edit net</a><button>Retire</button></div>'
        '<button>Outside</button></main></body></html>')
    (root / "td.html").write_text(
        head + '<label>Litres <input value="900"></label>'
        '<table aria-label="Readings"><tr><th>Day</th><th>Litres</th></tr>'
        '<tr><td>Day 12</td><td>40.0 L</td></tr></table>'
        '<div><a href="/e">Edit net</a><button>Retire</button></div>'
        '<button>Outside</button></main></body></html>')
    local = LocalSite(root)
    try:
        symbols = {}
        for page in ("th", "td"):
            d = WebDriver("web:" + local.url(f"{page}.html"))
            try:
                symbols[page] = BUILTINS["web.aria/v7"](d.reset(), {})
            finally:
                d.close()
        th, td = symbols["th"], symbols["td"]
        assert th["controls"]["textbox:Litres"] == ["filled", "invalid"]
        assert td["controls"]["textbox:Litres"] == ["filled"]
        assert th["tables"]["Readings"] == {"columns": ["Day", "Litres"], "rows": [["Day 12", "40.0 L"]],
                                           "row_headers": ["Day 12"]}
        assert "row_headers" not in td["tables"]["Readings"]
        assert th["groups"] == {"group:Net actions": ["link:Edit net", "button:Retire"]}
        assert "groups" not in td
        v6 = BUILTINS["web.aria/v6"]({"aria": '- group "G":\n  - button "B"', "path": "/", "flagged": ["button:B"]}, {})
        assert "groups" not in v6 and v6["controls"]["button:B"] == []  # v6 unchanged
    finally:
        local.close()


def test_web_aria_v8_records_the_user_facing_playwright_surface(tmp_path):
    from teardown.drivers.web.surface import CASES, SAME, audit

    result = audit(["web.aria/v7", "web.aria/v8", "web.aria/v9"], root=tmp_path / "surface")
    assert [c.id for c in CASES if not result[c.id]["web.aria/v9"]] == []  # every user-facing difference shows
    assert [c.id for c in SAME if result[c.id]["web.aria/v9"]] == []  # implementation differences do not
    assert [c.id for c in CASES if not result[c.id]["web.aria/v8"]] == ["focus-heading"]  # v8 unchanged
    assert sum(result[c.id]["web.aria/v7"] for c in CASES) == 17  # v7 unchanged: it records 17 of the 40


def test_live_outputs_are_discovered_and_need_a_field_probe_without_submit(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    (root / "form.html").write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Net</title></head><body><main>'
        '<h1>New net</h1><label>Width <input id="w"></label><label>Height <input id="h"></label>'
        '<p id="out">Enter a size.</p><button>Save</button>'
        '<script>const w = document.getElementById("w"), h = document.getElementById("h");'
        'const ok = v => /^\\d+$/.test(v) && +v >= 1 && +v <= 50;'
        'const show = () => document.getElementById("out").textContent ='
        ' ok(w.value) && ok(h.value) ? "Area " + (w.value * h.value) + " m2" : "Enter a size.";'
        'w.addEventListener("input", show); h.addEventListener("input", show);</script>'
        '</main></body></html>')
    local = LocalSite(root)
    try:
        project = Project(tmp_path / "p")
        project.open_target("web:" + local.url("form.html"), purpose="research")
        found = project.discover_ui("form", max_states=3, max_depth=1)
        screen = next(s for s in found["screens"] if s["fields"])
        assert screen["live_fields"] == ["textbox:Height", "textbox:Width"]
        counts = project.coverage("form", record_unknowns=False)["counts"]
        assert counts["live output textbox:Width"] == 0
        call = next(s for s in project.suggest_probes("form") if s["item"] == "live output textbox:Width")["call"]
        assert call["submit"] is None and call["prefix"] == ["fill[Height]=sample"]
        project.probe_web_field("form", prefix=call["prefix"], role="textbox", name="Width", submit=None,
                                kind="number", workers=1)
        assert project.coverage("form", record_unknowns=False)["counts"]["live output textbox:Width"] >= 3
    finally:
        local.close()


def test_coverage_lists_data_states_of_named_lists():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "site"
        root.mkdir()
        (root / "loans.html").write_text(
            '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>V</title></head><body><main>'
            '<h1>Summary</h1><div id="out"></div><button id="r">Record return</button><script>'
            'let loans=["SF-4","SF-7"];const show=()=>{document.getElementById("out").innerHTML = loans.length ?'
            ' "<ul aria-label=\'On loan\'>" + loans.map(x=>"<li>"+x+"</li>").join("") + "</ul>"'
            ' : "<p>Nothing is on loan.</p>";};show();'
            'document.getElementById("r").onclick=()=>{loans.pop();show();};</script></main></body></html>')
        local = LocalSite(root)
        try:
            project = Project(Path(tmp) / "p")
            project.open_target("web:" + local.url("loans.html"), purpose="research")
            project.define_actions({"ret": {"op": "click", "role": "button", "name": "Record return"}})
            project.check_rules("vault", [{"statement": "The summary lists what is on loan.", "checks": [
                {"kind": "outcome", "a": {"actions": ["ret", "ret", "ret"]}, "expect": {"title": "V"}}]},
                {"statement": "Two loans to start with.", "checks": [
                    {"kind": "outcome", "a": {"actions": ["ret"]}, "expect": {"title": "V"}}]}], workers=1)
            uncovered = project.coverage("vault", record_unknowns=False)["uncovered"]
            assert "data state: list On loan: several" in uncovered  # only one-left and none were recorded
            assert "data state: list On loan: one" not in uncovered
            assert "data state: list On loan: none" not in uncovered  # the list gave way to a message
            hint = next(s for s in project.suggest_probes("vault") if s["item"].startswith("data state: list"))
            assert hint["list"] == "On loan" and "`outline`" in hint["suggest"]
        finally:
            local.close()


def test_coverage_combines_routes_with_session_and_record_status(tmp_path):
    root = tmp_path / "site"
    (root / "items" / "1").mkdir(parents=True)
    (root / "items" / "2").mkdir(parents=True)
    head = '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>T</title></head><body><main>'
    signed = 'localStorage.getItem("s")'
    (root / "signin.html").write_text(
        head + f'<script>if ({signed}) location.replace("/list.html");</script><h1>Sign in</h1>'
        '<label>Username <input></label><label>Password <input type="password"></label>'
        '<button id="go">Sign in</button><script>document.getElementById("go").onclick=()=>{'
        'localStorage.setItem("s","1");location.href="/list.html";};</script></main></body></html>')
    (root / "list.html").write_text(
        head + f'<script>if (!{signed}) location.replace("/signin.html");</script><h1>Items</h1>'
        '<button id="out">Sign out</button><table aria-label="Items"><tr><th>Name</th><th>Status</th></tr>'
        '<tr><td><a href="/items/1/edit.html">One</a></td><td>Draft</td></tr>'
        '<tr><td><a href="/items/2/edit.html">Two</a></td><td>Locked</td></tr></table>'
        '<script>document.getElementById("out").onclick=()=>{localStorage.clear();location.href="/signin.html";};'
        '</script></main></body></html>')
    for n, heading in (("1", "Edit One"), ("2", "Cannot edit")):
        (root / "items" / n / "edit.html").write_text(
            head + f'<script>if (!{signed}) location.replace("/signin.html");</script><h1>{heading}</h1>'
            '<button>Sign out</button></main></body></html>')
    local = LocalSite(root)
    try:
        project = Project(tmp_path / "p")
        project.open_target("web:" + local.url("signin.html"), purpose="research")
        project.define_actions({
            "user": {"op": "fill", "role": "textbox", "name": "Username", "value": "a"},
            "pw": {"op": "fill", "role": "textbox", "name": "Password", "value": "b"},
            "submit": {"op": "click", "role": "button", "name": "Sign in"},
            "edit1": {"op": "goto", "value": "/items/1/edit.html"}})
        project.check_rules("items", [
            {"statement": "Signing in shows the items.", "checks": [
                {"kind": "outcome", "a": {"actions": ["user", "pw", "submit"]}, "expect": {"path": "/list.html"}}]},
            {"statement": "A draft item can be edited.", "checks": [
                {"kind": "outcome", "a": {"actions": ["user", "pw", "submit", "edit1"]},
                 "expect": {"headings": ["Edit One"]}}]}], workers=1)
        uncovered = set(project.coverage("items", record_unknowns=False)["uncovered"])
        assert {"route /signin.html: signed in", "route /items/*/edit.html: signed out",
                "route /items/*/edit.html: one record per status"} <= uncovered
        assert "route /items/*/edit.html: signed in" not in uncovered
        hints = {s["item"]: s for s in project.suggest_probes("items", limit=60)}
        session = hints["route /signin.html: signed in"]
        assert session["sequence"] == ["user", "pw", "submit", "goto[/signin.html]"]
        status = hints["route /items/*/edit.html: one record per status"]
        assert status["statuses"] == ["Draft", "Locked"] and status["visited"] == ["1"]
        project.define_actions({**session["define"], "edit2": {"op": "goto", "value": "/items/2/edit.html"}})
        project.check_rules("items", [
            {"statement": "A signed-in user who opens the sign-in page is sent to the items.", "checks": [
                {"kind": "outcome", "a": {"actions": session["sequence"]}, "expect": {"path": "/list.html"}}]},
            {"statement": "A locked item cannot be edited.", "checks": [
                {"kind": "outcome", "a": {"actions": ["user", "pw", "submit", "edit2"]},
                 "expect": {"headings": ["Cannot edit"]}}]},
            {"statement": "Signed out, an edit page sends you to sign in.", "checks": [
                {"kind": "outcome", "a": {"actions": ["edit1"]}, "expect": {"path": "/signin.html"}}]}], workers=1)
        uncovered = set(project.coverage("items", record_unknowns=False)["uncovered"])
        assert not {i for i in uncovered if i.startswith(("route /signin.html", "route /items/"))}
    finally:
        local.close()
