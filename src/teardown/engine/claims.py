"""Claim ledger: propose falsifiable claims, try to falsify them with fresh probes, keep honest counts."""

from __future__ import annotations

from teardown.audit.log import AuditLog
from teardown.core.confidence import violation_upper_bound
from teardown.core.model import (
    Claim,
    ClaimIdentity,
    ClaimKind,
    ClaimStatus,
    Layer,
    Origin,
    Strictness,
    TraceCheck,
    Unknown,
    UnknownIdentity,
)
from teardown.core.store import Workspace
from teardown.drivers.session import ObservationSession


class ClaimLedger:
    def __init__(self, workspace: Workspace, audit: AuditLog):
        self.workspace = workspace
        self.audit = audit

    # -- claims ------------------------------------------------------------------------------------------------
    def propose(
        self,
        *,
        feature: str,
        kind: ClaimKind | str,
        statement: str,
        inputs: list[str],
        expect: list[str | None],
        reference: str,
        mapper: str,
        strictness: Strictness | str = Strictness.MUST,
        origin: Origin | str = Origin.OBSERVED,
        layer: Layer | str = Layer.UNKNOWN,
    ) -> Claim:
        identity = ClaimIdentity(
            feature=feature,
            kind=ClaimKind(kind),
            statement=statement,
            check=TraceCheck(inputs=inputs, expect=expect),
            strictness=Strictness(strictness),
            origin=Origin(origin),
            layer=Layer(layer),
            reference=reference,
            mapper=mapper,
        )
        claims = self.workspace.load_claims()
        claim = claims.get(identity.id) or Claim(identity=identity)
        claims[claim.id] = claim
        self.workspace.save_claims(claims)
        self.workspace.put(identity)
        self.audit.append("claim-proposed", {"claim": claim.id}, {"feature": feature, "kind": identity.kind})
        return claim

    def falsify(self, claim_id: str, session: ObservationSession, repeats: int = 3) -> Claim:
        """Re-run the claim's check ``repeats`` times on fresh resets (no cache) and update its counts."""
        claims = self.workspace.load_claims()
        claim = claims[claim_id]
        check = claim.identity.check
        if session.mapper.id != claim.identity.mapper:
            raise ValueError("claim was stated under a different mapper version; re-state it first")
        for _ in range(repeats):
            outputs, evidence, _ = session.run(check.inputs, use_cache=False)
            claim.probes += 1
            claim.evidence.extend(evidence[-1:])
            mismatch = [o if e is not None and o != e else None for o, e in zip(outputs, check.expect, strict=True)]
            if any(m is not None for m in mismatch):
                claim.contradicting += 1
                if mismatch not in claim.counterexamples:
                    claim.counterexamples.append(mismatch)
            else:
                claim.confirming += 1
        claim.status = _status(claim)
        claims[claim.id] = claim
        self.workspace.save_claims(claims)
        self.audit.append(
            "claim-probed",
            {"claim": claim.id},
            {
                "status": claim.status,
                "probes": claim.probes,
                "confirming": claim.confirming,
                "contradicting": claim.contradicting,
                "violation_upper_bound_95": round(violation_upper_bound(claim.confirming, claim.contradicting), 4),
            },
        )
        return claim

    def all(self) -> dict[str, Claim]:
        return self.workspace.load_claims()

    # -- unknowns ----------------------------------------------------------------------------------------------
    def record_unknown(self, feature: str, question: str, recommended_probes: list[str] | None = None) -> Unknown:
        identity = UnknownIdentity(feature=feature, question=question)
        unknowns = self.workspace.load_unknowns()
        unknown = unknowns.get(identity.id) or Unknown(identity=identity)
        for probe in recommended_probes or []:
            if probe not in unknown.recommended_probes:
                unknown.recommended_probes.append(probe)
        unknowns[unknown.id] = unknown
        self.workspace.save_unknowns(unknowns)
        self.audit.append("unknown-recorded", {"unknown": unknown.id}, {"feature": feature})
        return unknown

    def unknowns(self) -> dict[str, Unknown]:
        return self.workspace.load_unknowns()


def _status(claim: Claim) -> ClaimStatus:
    if claim.contradicting and claim.confirming:
        return ClaimStatus.CONTESTED
    if claim.contradicting:
        return ClaimStatus.FALSIFIED
    if claim.confirming:
        return ClaimStatus.CORROBORATED
    return ClaimStatus.HYPOTHESIZED
