from __future__ import annotations

import json

import pytest

from teardown.audit.log import AuditChainBroken, AuditLog
from teardown.engine.learner import learn
from teardown.examples.signup import ACTIONS
from teardown.gate.gate import (
    GateConfig,
    GateMode,
    QuoteEntry,
    ReleaseBlocked,
    load_release,
    make_codename,
    release,
    review,
)
from teardown.gate.matcher import CorpusMatcher
from teardown.spec.draft import ModelRecord, SpecDraft

LABEL = "I agree to the Terms of Service and Privacy Policy"


def _draft(session, statement="Submit stays unavailable until the terms are accepted.") -> SpecDraft:
    from teardown.core.model import Claim, ClaimIdentity, TraceCheck

    result = learn(session, ACTIONS, name="signup", walks_per_state=20, walk_len=10)
    record = ModelRecord(
        feature="signup",
        target=session.target,
        mapper=session.mapper.id,
        model=result.model,
        algorithm=result.algorithm,
        budget=result.budget,
        completeness=result.completeness,
    )
    claim = Claim(
        identity=ClaimIdentity(
            feature="signup",
            kind="refusal",
            statement=statement,
            check=TraceCheck(inputs=["submit"], expect=["NA"]),
            reference=session.target,
            mapper=session.mapper.id,
        )
    )
    return SpecDraft(feature="signup", target=session.target, mapper=session.mapper.id, model=record, claims=[claim])


def test_matcher_finds_longest_verbatim_run_without_crossing_documents():
    m = CorpusMatcher([LABEL, "Email address is required."])
    assert m.longest("tick 'I agree to the terms of service' first").length == 7
    assert m.longest("required I agree to").length == 3  # "i agree to": never spans two corpus strings
    assert m.longest("nothing in common") is None


def test_gate_flags_leaked_label_and_denylisted_names(signup_session, workspace):
    draft = _draft(signup_session, statement="Acme shows 'Use at least 8 characters, including a number.'")
    config = GateConfig(codename="amber-falcon", denylist=["Acme"])
    projection, report = review(draft, workspace.corpus(), config)
    kinds = {(f.kind, f.matched) for f in report.findings}
    assert ("verbatim", "i agree to the terms of service and privacy policy") in kinds  # leaked via mapper key
    assert any(k == "verbatim" and "at least 8 characters" in m for k, m in kinds)  # leaked via claim text
    assert "Acme" not in json.dumps(projection) and "amber-falcon" in json.dumps(projection)
    assert not report.blocked  # standard mode warns


def test_quote_ledger_allows_justified_literals(signup_session, workspace):
    draft = _draft(signup_session, statement="Shows 'Use at least 8 characters, including a number.'")
    quote = QuoteEntry(
        text="Use at least 8 characters, including a number.",
        compat_reason="test-oracle",
        approved_by="reviewer@example.com",
    )
    _, report = review(draft, workspace.corpus(), GateConfig(codename="c", quotes=[quote]))
    assert not any("at least 8" in f.matched for f in report.findings)


def test_strict_mode_blocks_until_recorded_approvals_cover_every_finding(signup_session, workspace, tmp_path):
    from teardown.gate.gate import GateApproval

    draft = _draft(signup_session, statement="Shows 'Use at least 8 characters, including a number.'")
    config = GateConfig(codename="c", mode=GateMode.STRICT)
    _, report = review(draft, workspace.corpus(), config)
    classes = {f.cls for f in report.findings}
    assert "prose" in classes and report.blocked
    with pytest.raises(ReleaseBlocked):  # a name is not an approval
        release(draft, workspace.corpus(), config, tmp_path / "rel", approved_by="reviewer@example.com")
    by_class = [GateApproval(scope="class", cls=c, compat_reason="accessibility-name", approved_by="me")
                for c in classes - {"prose"}]
    prose_class = GateApproval(scope="class", cls="prose", compat_reason="user-required", approved_by="me")
    config = config.model_copy(update={"approvals": [*by_class, prose_class]})
    _, report = review(draft, workspace.corpus(), config)
    assert [f.cls for f in report.unapproved()] and all(f.cls == "prose" for f in report.unapproved())
    singles = [GateApproval(scope="finding", finding=f.id, compat_reason="test-oracle", approved_by="me")
               for f in report.unapproved()]
    config = config.model_copy(update={"approvals": [*by_class, *singles]})
    rel = release(draft, workspace.corpus(), config, tmp_path / "rel")
    assert rel.report.approved_by == "me" and load_release(tmp_path / "rel").id == rel.id


def test_release_projection_carries_no_dirty_identifiers(signup_session, workspace, tmp_path):
    draft = _draft(signup_session)
    rel = release(draft, workspace.corpus(), GateConfig(codename="c"), tmp_path / "rel")
    text = json.dumps(rel.spec)
    assert signup_session.target not in text and "ev_" not in text and "reference" not in text


def test_codenames_are_deterministic():
    assert make_codename("tgt_1") == make_codename("tgt_1")


def test_audit_chain_detects_tampering(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    for i in range(3):
        log.append("claim-probed", {"claim": f"clm_{i:064x}"}, {"n": i})
    assert log.verify() == 3
    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    entry = json.loads(lines[1])
    entry["statement"]["predicate"]["n"] = 99
    lines[1] = json.dumps(entry, sort_keys=True)
    (tmp_path / "audit.jsonl").write_text("\n".join(lines) + "\n")
    with pytest.raises(AuditChainBroken):
        log.verify()


def test_audit_entries_are_dsse_signed(tmp_path):
    from teardown.audit.signing import Signer

    signer = Signer(tmp_path / "k.pem")
    log = AuditLog(tmp_path / "audit.jsonl", signer=signer)
    log.append("spec-release", {"release": "rel_" + "0" * 64}, {"mode": "strict"})
    keys = {signer.keyid: signer.public_pem}
    assert log.verify(keys) == 1 and (tmp_path / "k.pem").stat().st_mode & 0o777 == 0o600
    other = Signer(tmp_path / "other.pem")
    with pytest.raises(AuditChainBroken):
        log.verify({other.keyid: other.public_pem})  # signature by an unknown key


def test_near_verbatim_copy_is_flagged_but_own_words_pass():
    from teardown.gate.matcher import NearMatcher

    manual = ("Comments are lines whose first character is a hash sign; they are ignored entirely, and blank lines "
              "consisting only of spaces and tabs are ignored as well.")
    near = NearMatcher([manual])
    edited = ("Comments are lines whose first character is a hash sign; they are ignored completely, and blank lines "
              "consisting only of spaces and tabs are skipped as well.")
    own = "A line starting with # produces no output; so does a line that is empty or holds only whitespace."
    assert near.best(edited)[0] >= 0.5
    assert near.best(own)[0] < 0.2
