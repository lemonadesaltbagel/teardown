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
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from teardown.audit.log import AuditLog
from teardown.core.model import MapperRule, MapperVersion
from teardown.core.store import Workspace
from teardown.drivers.base import Driver
from teardown.drivers.fake import open_fake
from teardown.drivers.session import ObservationSession
from teardown.engine.claims import ClaimLedger
from teardown.engine.learner import LearnResult, learn
from teardown.engine.mapper import Mapper
from teardown.gate.gate import GateConfig, GateMode, QuoteEntry, SpecRelease, make_codename, release, review
from teardown.gate.verifier import Verifier
from teardown.intake import Intake, Purpose, terms_digest, warnings_for
from teardown.spec.draft import ModelRecord, SpecDraft


def open_driver(target_spec: str) -> Driver:
    if target_spec.startswith("fake:"):
        return open_fake(target_spec)
    raise ValueError(f"no driver for {target_spec!r} yet (Phase 0 ships the fake driver; CLI and web come next)")


class ProjectState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_spec: str
    target: str
    intake: str
    mapper: str
    gate: GateConfig
    models: dict[str, str] = Field(default_factory=dict, description="feature -> latest model record id")


class Project:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.workspace = Workspace(self.root / "workspace")
        self.audit = AuditLog(self.root / "audit.jsonl")
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
    ) -> tuple[Intake, list[str]]:
        driver = open_driver(target_spec)
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
        mapper = MapperVersion(target=target, note="identity mapper (no rules yet)")
        self.workspace.put(mapper)
        gate = GateConfig(
            mode=GateMode.STRICT if strict else GateMode.STANDARD,
            codename=make_codename(target),
            denylist=sorted(set(real_names or [])),
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self._save(ProjectState(target_spec=target_spec, target=target, intake=intake.id, mapper=mapper.id, gate=gate))
        notes = warnings_for(intake)
        self.audit.append(
            "intake",
            {"intake": intake.id, "target": target},
            {"purpose": intake.purpose, "jurisdiction": jurisdiction, "gate_mode": gate.mode, "warnings": notes},
        )
        driver.close()
        return intake, notes

    def set_mapper(self, rules: list[MapperRule | dict[str, Any]], note: str = "") -> MapperVersion:
        state = self.state
        version = MapperVersion(
            target=state.target,
            rules=[r if isinstance(r, MapperRule) else MapperRule.model_validate(r) for r in rules],
            parent=state.mapper,
            note=note,
        )
        self.workspace.put(version)
        self._save(state.model_copy(update={"mapper": version.id}))
        self.audit.append("mapper-version", {"mapper": version.id}, {"parent": state.mapper, "rules": len(rules)})
        if self._session:
            self._session.close()
            self._session = None
        return version

    def mapper(self) -> Mapper:
        return Mapper(self.workspace.get(self.state.mapper, MapperVersion))

    def session(self) -> ObservationSession:
        if self._session is None or self._session.mapper.id != self.state.mapper:
            state = self.state
            intake = self.workspace.get(state.intake, Intake)
            self._session = ObservationSession(
                self.workspace,
                open_driver(state.target_spec),
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

    def compile_spec(self, feature: str) -> SpecDraft:
        state = self.state
        if feature not in state.models:
            raise KeyError(f"no model learned for feature {feature!r}")
        record = self.workspace.get(state.models[feature], ModelRecord)
        claims = [c for c in self.ledger.all().values() if c.identity.feature == feature]
        unknowns = [u for u in self.ledger.unknowns().values() if u.identity.feature == feature]
        draft = SpecDraft(
            feature=feature,
            target=state.target,
            mapper=record.mapper,
            model=record,
            claims=sorted(claims, key=lambda c: c.id),
            unknowns=sorted(unknowns, key=lambda u: u.id),
        )
        self.workspace.put(draft)
        return draft

    def review_spec(self, draft_id: str):
        draft = self.workspace.get(draft_id, SpecDraft)
        return review(draft, self.workspace.corpus(), self.state.gate)

    def release_spec(self, draft_id: str, approved_by: str | None = None) -> SpecRelease:
        draft = self.workspace.get(draft_id, SpecDraft)
        rel = release(draft, self.workspace.corpus(), self.state.gate, self.releases_dir, approved_by=approved_by)
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

    # -- clean-side channels -----------------------------------------------------------------------------------
    def verifier(self) -> Verifier:
        def open_original() -> ObservationSession:
            return ObservationSession(self.workspace, open_driver(self.state.target_spec), self.mapper())

        def open_clone(clone_target: str) -> ObservationSession:
            driver = open_driver(clone_target)
            # The clone's observations are expected to be abstract already (testability contract), so its mapper
            # is the identity. Its evidence goes to a scratch workspace: clone output is clean-side data.
            scratch = Workspace(self.root / "clone-runs")
            return ObservationSession(scratch, driver, Mapper(MapperVersion(target=driver.target_fingerprint())))

        return Verifier(
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
