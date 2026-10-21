"""Project: the dirty-side orchestration shared by the observe MCP server, the CLI and tests.

Directory layout under the project root::

    project.json      target spec, mapper, intake, gate config
    workspace/        evidence, traces, models, drafts, claim/unknown ledgers, string corpus (dirty only)
    audit.jsonl       hash-chained audit log
    releases/         gate-released specs: the ONLY directory the clean side may read
    tickets/          clean-side questions and gate-checked answers
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from teardown.audit.log import AuditLog
from teardown.core.ids import content_id
from teardown.core.model import ContentAddressed, MapperRule, MapperVersion
from teardown.core.store import Workspace
from teardown.drivers.base import Driver
from teardown.drivers.fake import open_fake
from teardown.drivers.session import ObservationSession
from teardown.engine.claims import ClaimLedger
from teardown.engine.learner import LearnResult, learn
from teardown.engine.mapper import Mapper, describe_symbol
from teardown.gate.gate import (
    GateConfig,
    GateMode,
    QuoteEntry,
    SpecRelease,
    make_codename,
    release,
    rename_symbol,
    review,
)
from teardown.gate.verifier import Verifier
from teardown.intake import Intake, Purpose, terms_digest, warnings_for
from teardown.spec.draft import ModelRecord, ProbeRow, ProbeTable, SpecDraft


class CoverageGateBlocked(PermissionError):
    def __init__(self, feature: str, gaps: list[str]):
        super().__init__(f"strict mode: feature {feature!r} has {len(gaps)} unacknowledged coverage gap(s); probe "
                         f"them, or acknowledge them at a terminal with `teardown approve --coverage`: {gaps[:5]}")
        self.gaps = gaps


class DiscoveryRecord(ContentAddressed):
    PREFIX: ClassVar[str] = "dsc"

    cmd: str
    target: str
    data: dict[str, Any]


def _portable_actions(actions: dict[str, dict[str, Any]], target_spec: str) -> dict[str, dict[str, Any]]:
    """Web `goto` actions with the original's absolute origin become root-relative paths (portable to clones)."""
    if not target_spec.startswith("web:"):
        return actions
    from urllib.parse import urlparse

    origin = "{0.scheme}://{0.netloc}".format(urlparse(target_spec.removeprefix("web:")))
    out = {}
    for name, a in actions.items():
        if a.get("op") == "goto" and isinstance(a.get("value"), str) and a["value"].startswith(origin):
            a = {**a, "value": a["value"][len(origin):] or "/"}
        out[name] = a
    return out


def _drop_masked_text(check):
    """A folded claim covers several typed values; drop outcome lists that only match with the echo masked."""
    expect = []
    for e in check.expect:
        if e is not None and "<input>" in e:
            data = json.loads(e)
            data = {k: v for k, v in data.items() if not (isinstance(v, list) and any("<input>" in str(x) for x in v))}
            e = json.dumps(data, sort_keys=True, ensure_ascii=False)
        expect.append(e)
    return check.model_copy(update={"expect": expect})


def _flatten(value: Any):
    if isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _flatten(v)
    elif isinstance(value, list):
        for v in value:
            yield from _flatten(v)
    elif isinstance(value, str):
        yield value


def open_driver(target_spec: str, actions: dict[str, dict[str, Any]] | None = None,
                options: dict[str, Any] | None = None) -> Driver:
    options = options or {}
    if target_spec.startswith("fake:"):
        return open_fake(target_spec)
    if target_spec.startswith("cli:"):
        from teardown.drivers.cli.driver import CliDriver
        from teardown.drivers.cli.invocation import Invocation

        table = {k: Invocation.model_validate(v) for k, v in (actions or {}).items()}
        return CliDriver(target_spec, actions=table)
    if target_spec.startswith("web:"):
        from teardown.drivers.web.driver import Profile, WebAction, WebDriver

        return WebDriver(target_spec, actions={k: WebAction.model_validate(v) for k, v in (actions or {}).items()},
                         profile=Profile(**options["profile"]) if options.get("profile") else None,
                         reset_command=options.get("reset_command"), reset_check_url=options.get("reset_check_url"),
                         contract_selectors=options.get("contract_selectors"))
    if target_spec.startswith("desktop:"):
        from teardown.drivers.desktop.driver import DesktopAction, DesktopDriver

        return DesktopDriver(target_spec, {k: DesktopAction.model_validate(v) for k, v in (actions or {}).items()},
                             options)
    if target_spec.startswith("android:"):
        from teardown.drivers.android.driver import AndroidAction, AndroidDriver

        return AndroidDriver(target_spec, {k: AndroidAction.model_validate(v) for k, v in (actions or {}).items()},
                             options)
    raise ValueError(f"no driver for {target_spec!r} (fake:, cli:, web:, desktop: and android: are available)")


def default_mapper(target_spec: str, target: str) -> MapperVersion:
    if target_spec.startswith("cli:"):
        return MapperVersion(target=target, builtin="cli.behavior/v1", note="CLI behavior-level abstraction")
    if target_spec.startswith("web:"):
        return MapperVersion(target=target, builtin="web.aria/v1", note="structured accessibility snapshot")
    if target_spec.startswith("desktop:"):
        return MapperVersion(target=target, builtin="desktop.a11y/v1", note="structured AT-SPI snapshot")
    if target_spec.startswith("android:"):
        return MapperVersion(target=target, builtin="android.a11y/v1", note="structured accessibility dump")
    return MapperVersion(target=target, note="identity mapper (no rules yet)")



def _contract_path(path: str, templates: list[str]) -> str:
    """Observed API path -> contract path: the first matching template ('{name}' matches one segment), query
    values dropped (keys kept)."""
    base, _, query = path.partition("?")
    segments = base.strip("/").split("/")
    for template in templates:
        parts = template.strip("/").split("/")
        if len(parts) == len(segments) and all(p == s or (p.startswith("{") and p.endswith("}"))
                                               for p, s in zip(parts, segments, strict=True)):
            base = "/" + "/".join(parts)
            break
    if query:
        keys = sorted({kv.partition("=")[0] for kv in query.split("&") if kv})
        base += "?" + "&".join(f"{k}={{}}" for k in keys)
    return base

class ProjectState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_spec: str
    target: str
    intake: str
    mapper: str
    gate: GateConfig
    models: dict[str, str] = Field(default_factory=dict, description="feature -> latest model record id")
    probes: dict[str, str] = Field(default_factory=dict, description="feature -> latest probe table id")
    rules: dict[str, str] = Field(default_factory=dict, description="feature -> latest rule table id")
    actions: dict[str, dict[str, Any]] = Field(default_factory=dict, description="named actions (invocations)")
    coverage: dict[str, dict[str, Any]] = Field(default_factory=dict, description="feature -> last coverage report")
    coverage_approvals: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="feature -> {gaps, approved_by, note}: coverage gaps a human acknowledged")
    target_options: dict[str, Any] = Field(default_factory=dict,
                                           description="driver options, e.g. reset_command, reset_check_url, "
                                                       "contract_selectors, profile (web determinism profile "
                                                       "overrides such as asset_hosts)")


class Project:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.workspace = Workspace(self.root / "workspace")
        from teardown.audit.signing import Signer

        # The dirty zone's signing key lives with the project; the clean side never receives it.
        self.signer = Signer(self.root / "keys" / "observer.ed25519.pem")
        self.audit = AuditLog(self.root / "audit.jsonl", signer=self.signer)
        self.releases_dir = self.root / "releases"
        self.tickets_dir = self.root / "tickets"
        self.ledger = ClaimLedger(self.workspace, self.audit)
        self._session: ObservationSession | None = None

    # -- state -------------------------------------------------------------------------------------------------
    @property
    def state(self) -> ProjectState:
        return ProjectState.model_validate_json((self.root / "project.json").read_text(encoding="utf-8"))

    def _save(self, state: ProjectState) -> None:
        (self.root / "project.json").write_text(state.model_dump_json(indent=1), encoding="utf-8")

    # -- intake and target -------------------------------------------------------------------------------------
    def open_target(
        self,
        target_spec: str,
        *,
        purpose: Purpose | str,
        jurisdiction: str = "",
        account: str = "",
        terms_text: str | None = None,
        owner_declaration: str | None = None,
        max_actions_per_second: float | None = None,
        strict: bool = False,
        real_names: list[str] | None = None,
        target_options: dict[str, Any] | None = None,
    ) -> tuple[Intake, list[str]]:
        driver = open_driver(target_spec, None, target_options)
        target = driver.target_fingerprint()
        intake = Intake(
            target=target,
            target_spec=target_spec,
            purpose=Purpose(purpose),
            jurisdiction=jurisdiction,
            account=account,
            terms_sha256=terms_digest(terms_text),
            owner_declaration=owner_declaration,
            max_actions_per_second=max_actions_per_second,
        )
        self.workspace.put(intake)
        mapper = default_mapper(target_spec, target)
        self.workspace.put(mapper)
        gate = GateConfig(
            mode=GateMode.STRICT if strict else GateMode.STANDARD,
            codename=make_codename(target),
            denylist=sorted(set(real_names or [])),
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self._save(ProjectState(target_spec=target_spec, target=target, intake=intake.id, mapper=mapper.id, gate=gate,
                                target_options=dict(target_options or {})))
        notes = warnings_for(intake)
        self.audit.append(
            "intake",
            {"intake": intake.id, "target": target},
            {"purpose": intake.purpose, "jurisdiction": jurisdiction, "gate_mode": gate.mode, "warnings": notes},
        )
        driver.close()
        return intake, notes

    def set_mapper(self, rules: list[MapperRule | dict[str, Any]] | None = None, note: str = "", *,
                   params: dict[str, Any] | None = None) -> MapperVersion:
        """New mapper version: ``rules`` replace the current rules (None keeps them); ``params`` are merged into the
        built-in abstraction's parameters (e.g. ``{"mask_dates": True}`` for web.aria/v1)."""
        state = self.state
        current = self.workspace.get(state.mapper, MapperVersion)
        if rules is None:
            rules = list(current.rules)
        version = MapperVersion(
            target=state.target,
            builtin=current.builtin,
            params={**(current.params or {}), **(params or {})},
            rules=[r if isinstance(r, MapperRule) else MapperRule.model_validate(r) for r in rules],
            parent=state.mapper,
            note=note,
        )
        self.workspace.put(version)
        self._save(state.model_copy(update={"mapper": version.id}))
        self.audit.append("mapper-version", {"mapper": version.id}, {"parent": state.mapper, "rules": len(rules)})
        self._reset_session()
        return version

    def action_table(self) -> dict[str, dict[str, Any]]:
        """Named actions plus every probe of every probe table (claims and tests refer to probes by id)."""
        state = self.state
        table = dict(state.actions)
        for table_id in state.probes.values():
            table.update(self.workspace.get(table_id, ProbeTable).actions)
        from teardown.engine.rules import RuleTable

        for table_id in state.rules.values():
            table.update(self.workspace.get(table_id, RuleTable).actions)
        return table

    def define_actions(self, actions: dict[str, dict[str, Any]]) -> None:
        if self.state.target_spec.startswith("web:"):
            from teardown.drivers.web.driver import WebAction as Model
        elif self.state.target_spec.startswith("desktop:"):
            from teardown.drivers.desktop.driver import DesktopAction as Model
        elif self.state.target_spec.startswith("android:"):
            from teardown.drivers.android.driver import AndroidAction as Model
        else:
            from teardown.drivers.cli.invocation import Invocation as Model

        validated = {k: Model.model_validate(v).model_dump(mode="json") for k, v in actions.items()}
        state = self.state
        self._save(state.model_copy(update={"actions": {**state.actions, **validated}}))
        self.workspace.add_supplied([str(x) for v in validated.values() for x in _flatten(v)])
        self._reset_session()

    def _reset_session(self) -> None:
        if self._session:
            self._session.close()
            self._session = None

    def mapper(self) -> Mapper:
        return Mapper(self.workspace.get(self.state.mapper, MapperVersion))

    def session(self) -> ObservationSession:
        if self._session is None or self._session.mapper.id != self.state.mapper:
            state = self.state
            intake = self.workspace.get(state.intake, Intake)
            self._session = ObservationSession(
                self.workspace,
                open_driver(state.target_spec, self.action_table(), state.target_options),
                self.mapper(),
                max_actions_per_second=intake.max_actions_per_second,
            )
            self.audit.append(
                "observation-session",
                {"target": state.target, "mapper": state.mapper},
                {"session": self._session.session_id, "driver": self._session.driver.name},
            )
        return self._session

    # -- learning, claims, spec --------------------------------------------------------------------------------
    def learn(self, feature: str, alphabet: list[str], **kwargs: Any) -> tuple[ModelRecord, LearnResult]:
        result = learn(self.session(), alphabet, name=feature, **kwargs)
        state = self.state
        record = ModelRecord(
            feature=feature,
            target=state.target,
            mapper=state.mapper,
            model=result.model,
            algorithm=result.algorithm,
            budget=result.budget,
            completeness=result.completeness,
        )
        self.workspace.put(record)
        self._save(state.model_copy(update={"models": {**state.models, feature: record.id}}))
        self.audit.append(
            "model-learned",
            {"model": record.id, "mapper": state.mapper},
            {"feature": feature, "states": len(result.model.states), "budget": result.budget,
             "conflicts": len(result.conflicts), "resets": result.stats["session"]["resets"]},
        )
        if result.conflicts:
            self.ledger.record_unknown(
                feature,
                f"{len(result.conflicts)} nondeterministic observation(s) under mapper {state.mapper}",
                ["calibrate noise with timing jitter", "refine the mapper (split or mask)"],
            )
        return record, result

    def propose_claim(self, **kwargs: Any):
        state = self.state
        return self.ledger.propose(reference=state.target, mapper=state.mapper, **kwargs)

    def falsify_claim(self, claim_id: str, repeats: int = 3):
        return self.ledger.falsify(claim_id, self.session(), repeats=repeats)

    def update_unknown(self, unknown_id: str, status: str, note: str = "") -> dict[str, Any]:
        """Mark an unknown investigating / resolved / out-of-scope (or reopen it), with a note saying why. Resolved
        unknowns stay in the ledger and the audit log but are no longer released; out-of-scope ones are released
        (the implementer should know what was not observed)."""
        from teardown.core.model import UnknownStatus

        unknowns = self.workspace.load_unknowns()
        if unknown_id not in unknowns:
            raise KeyError(unknown_id)
        unknown = unknowns[unknown_id]
        unknown.status = UnknownStatus(status)
        unknown.note = note
        self.workspace.save_unknowns(unknowns)
        self.audit.append("unknown-updated", {"unknown": unknown_id}, {"status": unknown.status.value, "note": note})
        return unknown.model_dump(mode="json")

    def blocked_hosts(self, actions: list[str] | None = None) -> list[dict[str, str]]:
        """Third-party hosts the web determinism profile refused during one episode (reset + ``actions``): which
        stylesheets, fonts or scripts the app tried to load. Candidates for ``profile.asset_hosts`` when layout
        depends on them."""
        state = self.state
        if not state.target_spec.startswith("web:"):
            raise ValueError("blocked_hosts is for web targets")
        from teardown.drivers.base import Action

        driver = open_driver(state.target_spec, self.action_table(), state.target_options)
        try:
            driver.reset()
            for name in actions or []:
                driver.step(Action(name=name))
            return [{"host": h, "type": t} for h, t in sorted(driver.blocked)]
        finally:
            driver.close()

    def _flag_clock_text(self, feature: str, probes: Any, rule_table: Any) -> None:
        """Calendar dates in expected UI text usually come from a clock (server creation times) and drift between
        observation and verification. Unless the abstraction masks them, say so as an unknown."""
        if not self.state.target_spec.startswith("web:"):
            return
        version = self.workspace.get(self.state.mapper, MapperVersion)
        if version.builtin != "web.aria/v1":
            return
        if (version.params or {}).get("mask_dates"):  # masked now: an earlier clock unknown is answered
            for u in self.ledger.unknowns().values():
                if u.identity.feature == feature and u.status == "open" and "calendar dates" in u.identity.question:
                    self.update_unknown(u.id, "resolved", "dates are masked (web.aria/v1 mask_dates)")
            return
        from teardown.engine.abstractions import CALENDAR_DATE

        blob = " ".join(json.dumps(x.model_dump(mode="json")) for x in (probes, rule_table) if x is not None)
        dates = sorted(set(CALENDAR_DATE.findall(blob)))
        if dates:
            self.ledger.record_unknown(
                feature, f"Expected UI text contains calendar dates ({', '.join(dates[:3])}): if they come from a "
                         "clock (e.g. creation times) they drift and verification turns inconclusive; mask them "
                         "(web.aria/v1 param mask_dates) or confirm they are fixed data.",
                ["re-run a date-bearing check on another day", "set_mapper(params={'mask_dates': True})"])

    def compile_spec(self, feature: str) -> SpecDraft:
        state = self.state
        feature_claims = [c for c in self.ledger.all().values() if c.identity.feature == feature]
        known = feature in state.models or feature in state.probes or feature in state.rules
        if not known and not feature_claims:
            raise KeyError(f"nothing learned, probed or claimed for feature {feature!r}")
        record = self.workspace.get(state.models[feature], ModelRecord) if feature in state.models else None
        probes = self.workspace.get(state.probes[feature], ProbeTable) if feature in state.probes else None
        from teardown.engine.rules import RuleTable

        rule_table = self.workspace.get(state.rules[feature], RuleTable) if feature in state.rules else None
        self._flag_clock_text(feature, probes, rule_table)
        version = self.workspace.get(state.mapper, MapperVersion)
        abstraction = {"builtin": version.builtin, "params": version.params} if version.builtin else {}
        claims = [c for c in self.ledger.all().values() if c.identity.feature == feature]
        unknowns = [u for u in self.ledger.unknowns().values()
                    if u.identity.feature == feature and u.status != "resolved"]
        draft = SpecDraft(
            feature=feature,
            target=state.target,
            mapper=(record.mapper if record else probes.mapper if probes else
                    rule_table.mapper if rule_table else state.mapper),
            abstraction=abstraction,
            model=record,
            probes=probes,
            rules=rule_table,
            actions=_portable_actions(state.actions, state.target_spec),
            api=self.api_contract() if state.target_spec.startswith("web:") else None,
            markup_contract=state.target_options.get("contract_selectors") if state.target_spec.startswith(
                "web:") else None,
            claims=sorted(claims, key=lambda c: c.id),
            unknowns=sorted(unknowns, key=lambda u: u.id),
        )
        self.workspace.put(draft)
        return draft

    def review_spec(self, draft_id: str):
        draft = self.workspace.get(draft_id, SpecDraft)
        return review(draft, self.workspace.corpus(), self.state.gate, self.workspace.supplied())

    def coverage_gaps(self, feature: str) -> list[str]:
        report = self.state.coverage.get(feature)
        return ["coverage was never measured"] if report is None else list(report.get("uncovered", []))

    def approve_findings(self, draft_id: str, approved_by: str, compat_reason: str, *,
                         finding_ids: list[str] | None = None, cls: str | None = None, kind: str = "verbatim",
                         note: str = "") -> list[str]:
        """Record approvals for gate findings of a draft: listed findings, or (``cls``) a whole class of one kind.
        Prose findings can only be approved one by one. Meant for a human at the gate (`teardown approve`)."""
        from teardown.gate.gate import CLASS_APPROVABLE, COMPAT_REASONS, GateApproval

        if not approved_by.strip():
            raise ValueError("approved_by must name the person approving")
        if compat_reason not in COMPAT_REASONS:
            raise ValueError(f"compat_reason must be one of {COMPAT_REASONS}")
        _, report = self.review_spec(draft_id)
        known = {f.id: f for f in report.findings}
        new: list[GateApproval] = []
        if cls is not None:
            if finding_ids:
                raise ValueError("give either finding ids or a class, not both")
            if cls not in CLASS_APPROVABLE:
                raise ValueError(f"{cls!r} findings are approved one at a time (class approval is for "
                                 f"{sorted(CLASS_APPROVABLE)})")
            new.append(GateApproval(scope="class", cls=cls, kind=kind, compat_reason=compat_reason,
                                    approved_by=approved_by, note=note))
        else:
            missing = [i for i in finding_ids or [] if i not in known]
            if missing or not finding_ids:
                raise KeyError(f"not findings of this draft: {missing}" if missing else "no findings named")
            new = [GateApproval(scope="finding", finding=i, compat_reason=compat_reason, approved_by=approved_by,
                                note=note) for i in finding_ids]
        state = self.state
        existing = {a.id for a in state.gate.approvals}
        added = [a for a in new if a.id not in existing]
        self._save(state.model_copy(update={"gate": state.gate.model_copy(
            update={"approvals": [*state.gate.approvals, *added]})}))
        for a in added:
            covered = [f.id for f in report.findings if a.covers(f)]
            self.audit.append("gate-approval", {"draft": draft_id},
                              {**a.model_dump(mode="json"), "approval": a.id, "covers": covered})
        return [a.id for a in added]

    def approve_coverage_gaps(self, feature: str, approved_by: str, note: str = "") -> list[str]:
        """Acknowledge the feature's current coverage gaps (they are released as unknowns). New gaps need a new
        acknowledgement."""
        if not approved_by.strip():
            raise ValueError("approved_by must name the person approving")
        gaps = self.coverage_gaps(feature)
        state = self.state
        approvals = {**state.coverage_approvals, feature: {"gaps": gaps, "approved_by": approved_by, "note": note}}
        self._save(state.model_copy(update={"coverage_approvals": approvals}))
        self.audit.append("coverage-gaps-approved", {}, {"feature": feature, "gaps": gaps, "approved_by": approved_by,
                                                          "note": note})
        return gaps

    def release_spec(self, draft_id: str, approved_by: str | None = None) -> SpecRelease:
        """Release a draft through the gate. In strict mode nothing passed here approves anything: findings and
        coverage gaps need recorded approvals (``approve_findings`` / ``approve_coverage_gaps``, i.e. `teardown
        approve` at a terminal). In standard mode ``approved_by`` only names who released."""
        draft = self.workspace.get(draft_id, SpecDraft)
        state = self.state
        if state.gate.mode is GateMode.STRICT:
            if approved_by:
                raise ValueError("strict mode: approvals are recorded with `teardown approve` at a terminal, not "
                                 "passed to release_spec")
            if draft.probes is not None:
                gaps = self.coverage_gaps(draft.feature)
                acknowledged = set((state.coverage_approvals.get(draft.feature) or {}).get("gaps", []))
                open_gaps = [g for g in gaps if g not in acknowledged]
                if open_gaps:
                    raise CoverageGateBlocked(draft.feature, open_gaps)
        rel = release(draft, self.workspace.corpus(), self.state.gate, self.releases_dir, approved_by=approved_by,
                      supplied=self.workspace.supplied())
        self.audit.append(
            "spec-release",
            {"release": rel.id, "draft": draft.id},
            {"mode": rel.mode, "findings": len(rel.report.findings), "approved_by": rel.report.approved_by,
             "previous": rel.previous},
        )
        return rel

    def add_quote(self, text: str, compat_reason: str, approved_by: str) -> None:
        state = self.state
        quotes = [*state.gate.quotes, QuoteEntry(text=text, compat_reason=compat_reason, approved_by=approved_by)]
        self._save(state.model_copy(update={"gate": state.gate.model_copy(update={"quotes": quotes})}))
        self.audit.append("quote-approved", {}, {"compat_reason": compat_reason, "approved_by": approved_by})

    def approve_observed_output(self, feature: str, approved_by: str, *, flags: tuple[str, ...] = ("--help", "-h",
                                "--version"), action_ids: list[str] | None = None,
                                compat_reason: str = "user-required") -> list[str]:
        """Approve the stdout of selected probes as functional quotes (byte-exact output the behavior requires,
        e.g. help and usage text). Selection: actions whose argv contains one of ``flags``, or explicit ids."""
        from teardown.engine.mapper import describe_symbol as parse
        from teardown.engine.rules import RuleTable

        state = self.state
        table = self.action_table()
        wanted = set(action_ids or []) | {k for k, a in table.items()
                                          if any(f in (a.get("argv") or [])[1:] for f in flags)}
        outputs: dict[str, str] = {}
        if feature in state.probes:
            for row in self.workspace.get(state.probes[feature], ProbeTable).rows:
                if row.action in wanted:
                    outputs[row.action] = row.expect
        if feature in state.rules:
            for rule in self.workspace.get(state.rules[feature], RuleTable).rules:
                for c in rule.checks:
                    for aid, sym in ((c.a, c.observed_a), (c.b, c.observed_b)):
                        if aid in wanted and sym:
                            outputs[aid] = sym
        texts = sorted({out["stdout"] for out in map(parse, outputs.values())
                        if isinstance(out, dict) and isinstance(out.get("stdout"), str) and out["stdout"].strip()})
        for text in texts:
            self.add_quote(text, compat_reason, approved_by)
        return texts

    # -- CLI probing -------------------------------------------------------------------------------------------
    def max_workers(self, requested: int) -> int:
        """Episodes may only run in parallel when each one has isolated state. A shared self-hosted backend (a
        `reset_command` target) is one state: parallel workers would reset each other mid-episode."""
        state = self.state
        if state.target_options.get("reset_command") or state.target_spec.startswith("android:"):
            return 1  # one shared backend / one device: episodes must not overlap
        return requested

    def _worker_session(self) -> ObservationSession:
        state = self.state
        driver = open_driver(state.target_spec, self.action_table(), state.target_options)
        return ObservationSession(self.workspace, driver, self.mapper())

    def _execute_raw(self, probes: list) -> list[dict[str, Any]]:
        from teardown.engine.probing import run_probes

        return [r.observation for r in run_probes(self._worker_session, probes, workers=4)]

    def discover_cli(self, cmd: str, takes_files: bool = True) -> dict[str, Any]:
        """Interface structure from help + behavior. Help prose stays in evidence; only structure is kept here."""
        from teardown.drivers.cli.discover import discover

        found = discover(self._execute_raw, cmd, takes_files=takes_files)
        found.pop("_help_text", None)
        record = DiscoveryRecord(cmd=cmd, target=self.state.target, data=found)
        self.workspace.put(record)
        summary = {"cmd": cmd, "options": len(found["model"]["options"]),
                   "findings": {k: len(v) for k, v in found["findings"].items()}}
        self.audit.append("cli-discovery", {"discovery": record.id}, summary)
        return {"discovery": record.id, **found}

    def probe_cli(self, feature: str, hints: dict[str, Any], *, discovery: dict[str, Any] | None = None,
                  workers: int = 4, pairwise: bool = True, env_sample: int = 200) -> dict[str, Any]:
        from teardown.drivers.cli.plan import ProbeHints, accepted_classes, plan_pairwise, plan_sweep
        from teardown.engine.mapper import describe_symbol
        from teardown.engine.mining import mine
        from teardown.engine.noise import calibrate
        from teardown.engine.probing import run_probes

        h = ProbeHints.model_validate(hints)
        workers = self.max_workers(workers)
        found = discovery or self.discover_cli(h.cmd, takes_files=h.takes_files)
        model = found["model"]
        sweep = plan_sweep(model, h)
        results = run_probes(self._worker_session, sweep, workers=workers)
        accepted = accepted_classes(sweep, [describe_symbol(r.symbol) for r in results], h.default_input)
        probes = list(sweep)
        if pairwise:
            extra = [p for p in plan_pairwise(model, h, accepted) if p.id not in {q.id for q in probes}]
            results += run_probes(self._worker_session, extra, workers=workers)
            probes += extra
        noise = calibrate(self._worker_session, probes, results, env_sample=env_sample, workers=workers)
        nondet = set(noise.nondeterministic)
        table = ProbeTable(
            feature=feature,
            target=self.state.target,
            mapper=self.state.mapper,
            actions={r.probe.id: r.probe.invocation.model_dump(mode="json") for r in results},
            rows=[ProbeRow(action=r.probe.id, expect=r.symbol, tags=r.probe.tags) for r in results
                  if r.probe.id not in nondet],
            excluded={pid: "nondeterministic" for pid in sorted(nondet)},
            discovery={k: v for k, v in found.items() if k in ("cmd", "model", "minimal", "findings")},
        )
        mined, mixed = mine(feature, h.cmd, results, exclude=nondet)
        table = table.model_copy(update={"mixed": mixed, "id": ""})
        table = ProbeTable.model_validate(table.model_dump(exclude={"id"}))
        self.workspace.put(table)
        state = self.state
        self._save(state.model_copy(update={"probes": {**state.probes, feature: table.id}}))
        self._reset_session()
        evidence = {r.probe.id: r.evidence for r in results}
        for m in mined:
            first, *rest = m.checks
            claim = self.propose_claim(feature=feature, kind=m.kind, statement=m.statement, inputs=first.inputs,
                                       expect=first.expect, match="subset", cases=rest)
            self.ledger.record_batch(claim.id, 2 * len(m.checks), [evidence[c.inputs[0]] for c in m.checks])
        for var, ids in noise.env_dependent.items():
            self.ledger.record_unknown(feature, f"{len(ids)} sampled probe(s) behave differently when {var} changes",
                                       [f"specify the {var}-dependent behavior", "probe it across more values"])
        for row in mixed:
            self.ledger.record_unknown(feature, f"value class '{row['class']}' of {row['factor']} has mixed outcomes",
                                       ["partition this class further", "check for interaction with other inputs"])
        if nondet:
            self.ledger.record_unknown(feature, f"{len(nondet)} probe(s) are nondeterministic and were excluded",
                                       ["mask the varying part of the output", "state a partial-order claim"])
        self.audit.append("probe-table", {"table": table.id}, {
            "feature": feature, "probes": len(results), "rows": len(table.rows), "nondeterministic": len(nondet),
            "env_dependent": {k: len(v) for k, v in noise.env_dependent.items()}, "claims": len(mined),
            "mixed": len(mixed)})
        return {"table": table.id, "probes": len(results), "rows": len(table.rows), "claims": len(mined),
                "mixed": len(mixed), "noise": noise.model_dump(mode="json"), "accepted": accepted}

    def ingest_docs(self, source: str, text: str) -> int:
        """Register public documentation the observer read. It stays dirty-side; its paragraphs join the gate corpus
        so verbatim reuse in rules or claims is flagged. Rules derived from it should use origin='documented'."""
        n = self.workspace.add_reference_text(source, text)
        self.audit.append("docs-ingested", {}, {"source": source, "paragraphs": n})
        return n

    def api_contract(self) -> dict[str, Any]:
        """OpenAPI-style skeleton of the backend contract observed through the UI: paths, methods, statuses and
        value-free body shapes. No values, so no data or prose from the target: query values become ``{}``, and
        path segments that are data (slugs, user names) are folded by the observer's ``target_options
        ["api_templates"]`` (e.g. ``["/api/articles/feed", "/api/articles/{slug}"]``; first match wins)."""
        from teardown.core.model import Evidence

        templates = list(self.state.target_options.get("api_templates", []))
        paths: dict[str, dict[str, Any]] = {}
        for ev in self.workspace.iter_objects("ev", Evidence):
            if ev.driver != "web" or not isinstance(ev.payload, dict):
                continue
            for ex in ev.payload.get("api_shapes", []) + [
                    {"method": m, "path": p, "status": st} for m, p, st in ev.payload.get("network", [])]:
                op = paths.setdefault(_contract_path(ex["path"], templates), {}).setdefault(
                    ex["method"].lower(), {"responses": {}})
                if ex.get("request_shape") is not None:
                    op["requestBody"] = ex["request_shape"]
                if ex.get("status") is not None:
                    resp = op["responses"].setdefault(str(ex["status"]), {})
                    if ex.get("response_shape") is not None:
                        resp["shape"] = ex["response_shape"]
        return {"openapi": "3.1.0-skeleton", "paths": dict(sorted(paths.items()))}

    # -- coverage ------------------------------------------------------------------------------------------------
    def coverage(self, feature: str, inventory: dict[str, list[str]] | None = None, *,
                 record_unknowns: bool = True) -> dict[str, Any]:
        """Feature inventory -> number of probes and rule checks exercising each item.

        An item is exercised when any of its patterns occurs in an action's argv or stdin. The inventory defaults to
        the discovered options; the observer adds documented items (functions, formats, modes, edge cases).
        Uncovered items become explicit unknowns: missing coverage is unknown, not absence.
        """
        from teardown.engine.rules import RuleTable

        state = self.state
        items = dict(inventory or {})
        table = self.workspace.get(state.probes[feature], ProbeTable) if feature in state.probes else None
        if table and table.discovery.get("model"):
            for o in table.discovery["model"]["options"].values():
                if not o.get("phantom") and o["names"][0] not in ("--help", "--version", "-h"):
                    items.setdefault(f"option {'/'.join(o['names'])}", list(o["names"]))
        actions = list(table.actions.items()) if table else []
        if feature in state.rules:
            rule_table = self.workspace.get(state.rules[feature], RuleTable)
            actions += list(rule_table.actions.items())
            named = self.action_table()
            for rule in rule_table.rules:  # UI rules: the named actions their sequences use
                for c in rule.checks:
                    for name in (c.a_inputs or []) + (c.b_inputs or []):
                        if name in named:
                            actions.append((name, named[name]))
        if not state.target_spec.startswith("cli:"):
            actions += list(state.actions.items())

        def exercises(entry: tuple[str, dict[str, Any]], pattern: str) -> bool:
            name, action = entry
            if "argv" not in action:  # UI action: match its name or definition (role, accessible name, value)
                return pattern in name or pattern in json.dumps(action, ensure_ascii=False)
            argv = action.get("argv", [])[1:]
            if pattern.startswith("-"):  # an option: a token, --opt=value, or a short option attached/bundled
                return any(t == pattern or t.startswith(pattern + "=") or (
                    len(pattern) == 2 and t.startswith("-") and not t.startswith("--") and pattern[1] in t[1:])
                    for t in argv)
            return pattern in " ".join(argv) or pattern in (action.get("stdin") or "")

        counts = {item: sum(any(exercises(a, pat) for pat in patterns) for a in actions)
                  for item, patterns in items.items()}
        uncovered = sorted(i for i, n in counts.items() if n == 0)
        self._save(self.state.model_copy(update={"coverage": {**self.state.coverage, feature: {
            "items": len(items), "uncovered": uncovered}}}))
        if record_unknowns:
            for item in uncovered:
                self.ledger.record_unknown(feature, f"not exercised by any probe or rule: {item}",
                                           ["add probes or a rule for this item"])
        self.audit.append("coverage", {}, {"feature": feature, "items": len(items), "uncovered": len(uncovered)})
        return {"items": len(items), "covered": len(items) - len(uncovered), "uncovered": uncovered,
                "counts": counts}

    # -- rules ---------------------------------------------------------------------------------------------------
    def check_rules(self, feature: str, rules: list[dict[str, Any]], workers: int = 4) -> dict[str, Any]:
        """Run observer-authored rules against the original (CLI targets) and record them for the spec."""
        from teardown.drivers.cli.invocation import Invocation
        from teardown.drivers.cli.plan import Probe
        from teardown.engine import rules as R
        from teardown.engine.probing import run_probes

        specs = [R.RuleSpec.model_validate({"feature": feature, **r}) for r in rules]
        workers = self.max_workers(workers)
        invocations: dict[str, dict[str, Any]] = {}
        sequences: dict[str, list[str]] = {}
        for spec in specs:
            for check in spec.checks:
                for side in (check.a, check.b):
                    if side is None:
                        continue
                    if "actions" in side:  # UI rule: a sequence of named actions
                        sequences[R.action_id(side)] = list(side["actions"])
                    else:
                        invocations[R.action_id(side)] = Invocation.model_validate(side).model_dump(mode="json")
        if sequences:
            from teardown.engine.fieldprobe import SequenceProbe, run_sequences

            seq_probes = [SequenceProbe(id=k, inputs=v) for k, v in sequences.items()]
            first = {r.probe.id: r.symbol for r in run_sequences(self._worker_session, seq_probes, workers=workers)}
            second = {r.probe.id: r.symbol for r in run_sequences(self._worker_session, seq_probes, workers=workers)}
        else:
            first, second = {}, {}
        probes = [Probe(id=k, invocation=Invocation.model_validate(v), tags=["s:rule"]) for k, v in invocations.items()]
        if probes:
            first |= {r.probe.id: r.symbol for r in run_probes(self._worker_session, probes, workers=workers)}
            second |= {r.probe.id: r.symbol for r in run_probes(self._worker_session, probes, workers=workers)}
        unstable = {k for k in first if first[k] != second[k]}
        records = []
        for spec in specs:
            results = [R.evaluate(c, first) for c in spec.checks]
            noisy = any(r.a in unstable or (r.b in unstable) for r in results)
            status = "contested" if noisy else R.status_of(results)
            rid = content_id("rle", {"feature": feature, "statement": spec.statement,
                                     "checks": [c.model_dump(mode="json") for c in spec.checks]})
            records.append(R.RuleRecord(id=rid, statement=spec.statement, origin=spec.origin, kind=spec.kind,
                                        status=status, checks=results))
        state = self.state
        old = self.workspace.get(state.rules[feature], R.RuleTable) if feature in state.rules else None
        merged = {r.id: r for r in (old.rules if old else [])}
        merged.update({r.id: r for r in records})
        table = R.RuleTable(feature=feature, target=state.target, mapper=state.mapper,
                            actions={**(old.actions if old else {}), **invocations}, rules=list(merged.values()))
        self.workspace.put(table)
        self._save(state.model_copy(update={"rules": {**state.rules, feature: table.id}}))
        self.workspace.add_supplied([str(x) for v in invocations.values() for x in _flatten(v)])
        self._reset_session()
        conflicts = [r for r in records if r.origin == "documented" and r.status != "corroborated"]
        for r in conflicts:
            self.ledger.record_unknown(feature, f"documentation/behavior conflict: '{r.statement}' is {r.status}",
                                       ["decide which one the reimplementation should follow"])
        self.audit.append("rules-checked", {"table": table.id}, {
            "feature": feature, "rules": len(records), "corroborated": sum(r.status == "corroborated" for r in records),
            "falsified": sum(r.status == "falsified" for r in records), "conflicts": len(conflicts)})
        return {"table": table.id, "rules": [{"statement": r.statement, "status": r.status,
                                              "failed_checks": [i for i, c in enumerate(r.checks) if not c.holds],
                                              "suggestions": R.suggest(r) if r.status != "corroborated" else []}
                                             for r in records]}

    # -- web field probing -------------------------------------------------------------------------------------
    def probe_ui_field(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Field probing for any UI target (web, android, desktop)."""
        return self.probe_web_field(*args, **kwargs)

    def probe_web_field(self, feature: str, *, prefix: list[str], role: str, name: str, submit: str,
                        kind: str = "text", classes: dict[str, str] | None = None, valid: str | None = None,
                        boundary: bool = True, workers: int = 4) -> dict[str, Any]:
        """Probe one form field: every class (plus the length boundary) is filled after ``prefix`` and submitted.

        ``valid`` names a class known to be accepted; it defines the acceptance reference for the boundary search.
        """
        from teardown.engine import fieldprobe as fp
        from teardown.engine.mining import mine

        workers = self.max_workers(workers)
        values = dict(classes or fp.CLASSES.get(kind, fp.TEXT))
        valid = valid or ("valid" if "valid" in values else "typical" if "typical" in values else None)

        platform = self.state.target_spec.split(":", 1)[0]

        def fill_action(cls: str, value: str) -> tuple[str, dict[str, Any]]:
            if platform == "web":
                spec = {"op": "fill", "role": role, "name": name, "value": value}
            else:  # android / desktop action shape
                spec = {"action": "fill", "role": role, "name": name, "value": value}
            return f"fill[{name}]={cls}", spec

        actions = dict(fill_action(c, v) for c, v in values.items())
        self.define_actions(actions)
        boundary_found = None
        if boundary and valid:
            session = self._worker_session()
            try:
                ref_inputs = [*prefix, fill_action(valid, values[valid])[0], submit]
                reference = fp.outcome(describe_symbol(session.run(ref_inputs, use_cache=False)[0][-1]))

                def probe_once(value: str) -> str:
                    act_name, spec = fill_action("probe", value)
                    session.reset()
                    for step in prefix:
                        session.step(step)
                    session.step(act_name, params=spec)
                    return session.step(submit)[1]

                boundary_found = fp.length_boundary(probe_once, kind, reference)
            finally:
                session.close()
            if boundary_found is not None:
                extra = dict([fill_action("len_at_max", fp.value_for_length(kind, boundary_found)),
                              fill_action("len_over_max", fp.value_for_length(kind, boundary_found + 1))])
                self.define_actions(extra)
                actions.update(extra)
                values["len_at_max"] = extra[f"fill[{name}]=len_at_max"]["value"]
                values["len_over_max"] = extra[f"fill[{name}]=len_over_max"]["value"]
        probes = [fp.SequenceProbe(id=f"{feature}:{name}={cls}", inputs=[*prefix, f"fill[{name}]={cls}", submit],
                                   tags=["s:field", f"field:{name}", f"val:{kind}.{cls}"]) for cls in values]
        first = fp.run_sequences(self._worker_session, probes, workers=workers)
        second = {r.probe.id: r.symbol for r in fp.run_sequences(self._worker_session, probes, workers=workers)}
        typed = {p.id: values[p.id.rsplit("=", 1)[1]] for p in probes}

        def outcome_of(result) -> dict[str, Any]:
            return fp.outcome(describe_symbol(result.symbol), typed[result.probe.id])

        nondet = {r.probe.id for r in first if fp.outcome_json(r.symbol, typed[r.probe.id])
                  != fp.outcome_json(second[r.probe.id], typed[r.probe.id])}
        # Rows keep the literal outcome (the typed value is part of the row, so its echo is reproducible); mining
        # and acceptance compare echo-masked outcomes.
        literal = {r.probe.id: fp.outcome_json(r.symbol) for r in first}
        for r in first:
            r.symbol = json.dumps(outcome_of(r), sort_keys=True, ensure_ascii=False)
        table = ProbeTable(
            feature=feature, target=self.state.target, mapper=self.state.mapper,
            actions={k: v for k, v in self.action_table().items() if k in {*prefix, submit, *actions}},
            rows=[ProbeRow(action=submit, prefix=r.probe.inputs[:-1], expect=literal[r.probe.id],
                           tags=r.probe.tags, match="subset") for r in first if r.probe.id not in nondet],
            excluded={pid: "nondeterministic" for pid in sorted(nondet)},
        )
        state = self.state
        if feature in state.probes:  # extend an existing table for the feature
            old = self.workspace.get(state.probes[feature], ProbeTable)
            table = ProbeTable(feature=feature, target=old.target, mapper=old.mapper,
                               actions={**old.actions, **table.actions}, rows=[*old.rows, *table.rows],
                               excluded={**old.excluded, **table.excluded}, discovery=old.discovery,
                               mixed=old.mixed)
        self.workspace.put(table)
        self._save(self.state.model_copy(update={"probes": {**self.state.probes, feature: table.id}}))
        reference_outcome = next((describe_symbol(r.symbol) for r in first
                                  if r.probe.id.endswith(f"={valid}")), None) if valid else None
        is_refused, describe = fp.judge(reference_outcome)
        mined, mixed = mine(feature, "the form", first, exclude=nondet, outcome=fp.outcome, describe=describe,
                            refused=is_refused)
        for m in mined:
            checks = [_drop_masked_text(c) for c in m.checks]
            head, *rest = checks
            layer = fp.layer_of(m.outcome) if m.kind == "refusal" else "unknown"
            claim = self.propose_claim(feature=feature, kind=m.kind, statement=m.statement, inputs=head.inputs,
                                       expect=head.expect, match="subset", cases=rest, layer=layer)
            self.ledger.record_batch(claim.id, 2 * len(m.checks), [])
        for row in mixed:
            self.ledger.record_unknown(feature, f"value class '{row['class']}' of {row['factor']} has mixed outcomes",
                                       ["partition this class further"])
        if boundary_found is None and boundary:
            self.ledger.record_unknown(feature, f"no length limit observed for field '{name}' up to 4096 characters "
                                       "(or no accepted reference)", ["probe longer values", "check server limits"])
        summary = {"feature": feature, "field": name, "classes": len(values), "boundary": boundary_found,
                   "claims": len(mined), "nondeterministic": len(nondet)}
        self.audit.append("field-probe", {"table": table.id}, summary)
        return {"table": table.id, "classes": len(values), "boundary": boundary_found, "claims": len(mined),
                "mixed": len(mixed), "nondeterministic": sorted(nondet),
                "boundary_actions": [a for a in actions if a.endswith(("=len_at_max", "=len_over_max"))]}

    # -- clean-side channels -----------------------------------------------------------------------------------
    def verifier(self) -> Verifier:
        def open_original(rel: SpecRelease) -> ObservationSession:
            state = self.state
            return ObservationSession(self.workspace,
                                      open_driver(state.target_spec, self.action_table(), state.target_options),
                                      self.mapper())

        def open_clone(clone_target: str, rel: SpecRelease, adapter: dict[str, Any] | None) -> ObservationSession:
            adapter = adapter or {}
            # A web clone against the same self-hosted backend needs the same per-episode backend reset.
            if adapter.get("target_options") is not None:  # e.g. a desktop clone's launch argv
                options = adapter["target_options"]
            elif clone_target.split(":", 1)[0] == self.state.target_spec.split(":", 1)[0]:
                options = self.state.target_options
            else:
                options = None
            driver = open_driver(clone_target, adapter.get("actions") or rel.spec.get("actions") or {}, options)
            # Built-in abstractions (CLI behavior, structured accessibility snapshot) are public and apply to the
            # clone too. The original's rules stay dirty-side; the clean side supplies its own adapter rules that
            # map its UI onto the released vocabulary. Clone evidence goes to a scratch workspace.
            abstraction = rel.spec.get("abstraction") or {}
            version = MapperVersion(target=driver.target_fingerprint(), builtin=abstraction.get("builtin"),
                                    params=abstraction.get("params") or {},
                                    rules=[MapperRule.model_validate(r) for r in adapter.get("rules", [])])
            return ObservationSession(Workspace(self.root / "clone-runs"), driver, Mapper(version))

        gate = self.state.gate
        return Verifier(
            rename=lambda symbol: rename_symbol(symbol, gate),
            releases_dir=self.releases_dir,
            open_original=open_original,
            open_clone=open_clone,
            ledger=self.ledger,
            audit=self.audit,
        )

    def tickets(self) -> list[dict[str, Any]]:
        if not self.tickets_dir.exists():
            return []
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(self.tickets_dir.glob("tkt_*.json"))]

    def answer_ticket(self, ticket_id: str, answer: str) -> dict[str, Any]:
        """Answers are gate-checked like spec text; in strict mode a finding blocks the answer."""
        from teardown.gate.matcher import CorpusMatcher

        path = self.tickets_dir / f"{ticket_id}.json"
        ticket = json.loads(path.read_text(encoding="utf-8"))
        gate = self.state.gate
        match = CorpusMatcher(self.workspace.corpus()).longest(answer)
        leak = bool(match and match.length >= gate.min_tokens)
        if leak and gate.mode is GateMode.STRICT:
            raise PermissionError("strict mode: the answer quotes observed text verbatim; rephrase it")
        ticket.update(status="answered", answer=answer, gate_warning="verbatim text from the target" if leak else None)
        path.write_text(json.dumps(ticket, indent=1), encoding="utf-8")
        self.audit.append("ticket-answered", {}, {"ticket": ticket_id, "gate_warning": leak})
        return ticket
