"""Spec drafts (dirty side) and their release projection (what may cross to the clean side).

The draft keeps everything the observer knows: evidence ids, the real target fingerprint, the mapper rules. The
projection keeps only the abstract model, claim definitions and counts, unknowns and the completeness statement.
The gate then scans that projection for leaked expression before anything is released.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import Field

from teardown.core.model import Claim, ContentAddressed, Unknown
from teardown.spec.efsm import EFSM
from teardown.spec.export import to_ears, to_xstate

TESTABILITY_CONTRACT = (
    "The implementation must expose, after every input, an observation whose abstract form equals one of the "
    "output definitions in `model.outputs` (keys and class values exactly as given). Inputs not offered in a state "
    "must be reported as unavailable ('NA'). Wording, layout and visual design are yours to choose."
)


class ModelRecord(ContentAddressed):
    PREFIX: ClassVar[str] = "mdl"

    feature: str
    target: str
    mapper: str
    model: EFSM
    algorithm: str
    budget: dict[str, Any]
    completeness: str


class SpecDraft(ContentAddressed):
    PREFIX: ClassVar[str] = "dft"

    feature: str
    target: str
    mapper: str
    model: ModelRecord
    claims: list[Claim] = Field(default_factory=list)
    unknowns: list[Unknown] = Field(default_factory=list)

    def release_projection(self) -> dict[str, Any]:
        model = self.model.model
        return {
            "feature": self.feature,
            "vocabulary": self.mapper,
            "testability_contract": TESTABILITY_CONTRACT,
            "completeness": self.model.completeness,
            "model": model.model_dump(mode="json"),
            "requirements": to_ears(model),
            "xstate": to_xstate(model),
            "claims": [
                {
                    "id": c.id,
                    "kind": c.identity.kind,
                    "statement": c.identity.statement,
                    "check": c.identity.check.model_dump(mode="json"),
                    "strictness": c.identity.strictness,
                    "origin": c.identity.origin,
                    "layer": c.identity.layer,
                    "status": c.status,
                    "probes": c.probes,
                    "confirming": c.confirming,
                    "contradicting": c.contradicting,
                }
                for c in self.claims
            ],
            "unknowns": [
                {"id": u.id, "question": u.identity.question, "recommended_probes": u.recommended_probes}
                for u in self.unknowns
            ],
        }
