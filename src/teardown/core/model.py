"""Core records: evidence, traces, mapper versions, claims and unknowns.

Immutable records derive from :class:`ContentAddressed`. Their id is a hash of every field except ``id``, so the
same observation always gets the same id and an edited record no longer validates.

Claims and unknowns have a content-addressed *identity* (what is being claimed or asked) and mutable *state*
(status, probe counts) that the ledger updates; every state change is also written to the audit log.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from teardown.core.ids import content_id


class TamperedRecord(ValueError):
    pass


class ContentAddressed(BaseModel):
    """An immutable record whose ``id`` is the hash of its other fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    PREFIX: ClassVar[str] = "obj"

    id: str = ""

    def semantic_projection(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"id"})

    @model_validator(mode="after")
    def _assign_or_verify_id(self) -> ContentAddressed:
        expected = content_id(self.PREFIX, self.semantic_projection())
        if not self.id:
            object.__setattr__(self, "id", expected)
        elif self.id != expected:
            raise TamperedRecord(f"{self.PREFIX} record id {self.id} does not match its content ({expected})")
        return self


class ObservationTier(StrEnum):
    """Where a piece of evidence sits relative to the clean-room line.

    ``behavior`` may support claims. ``steering`` may guide exploration but never appears in claim content.
    ``implementation`` (code bodies, decompilation, syscall sequences, ...) is never captured at all.
    """

    BEHAVIOR = "behavior"
    STEERING = "steering"
    IMPLEMENTATION = "implementation"


class Evidence(ContentAddressed):
    PREFIX: ClassVar[str] = "ev"

    session: str
    seq: int
    target: str
    driver: str
    operation: str
    action: dict[str, Any] | None = None
    payload: Any = None
    tier: ObservationTier = ObservationTier.BEHAVIOR

    @model_validator(mode="after")
    def _no_implementation_tier(self) -> Evidence:
        if self.tier is ObservationTier.IMPLEMENTATION:
            raise ValueError("implementation-tier observations are never captured")
        return self


class MapperRule(BaseModel):
    """One normalization step applied to a concrete observation (a JSON object)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str = Field(description="Dotted key path; '*' matches any key at that level.")
    op: str = Field(
        description="'drop', 'mask' (replace with `value`), 'rename' (key becomes `value`), "
        "or 'classify' (first matching regex wins)."
    )
    value: str | None = None
    classes: list[tuple[str, str]] = Field(default_factory=list, description="(regex, class) pairs for 'classify'.")
    default: str | None = Field(default=None, description="Class used by 'classify' when nothing matches.")


class MapperVersion(ContentAddressed):
    """A deterministic, versioned abstraction function from concrete observations to output symbols."""

    PREFIX: ClassVar[str] = "map"

    target: str
    rules: list[MapperRule] = Field(default_factory=list)
    parent: str | None = None
    note: str = ""


class Trace(ContentAddressed):
    """A concrete run: the actions taken after one reset and the evidence each produced."""

    PREFIX: ClassVar[str] = "tr"

    session: str
    target: str
    reset_evidence: str
    steps: list[tuple[str, str]] = Field(description="(action name, evidence id) pairs.")


class ClaimKind(StrEnum):
    SEQUENCE = "sequence"
    REFUSAL = "refusal"
    DEFAULT = "default"
    INPUT_DOMAIN = "input-domain"
    INVARIANT = "invariant"
    ORDERING = "ordering"
    SIDE_EFFECT = "side-effect"


class Strictness(StrEnum):
    MUST = "must"
    MAY_EXTEND = "may-extend"
    IMPLEMENTATION_DEFINED = "implementation-defined"


class Origin(StrEnum):
    OBSERVED = "observed"
    INFERRED_INTENT = "inferred-intent"


class Layer(StrEnum):
    CLIENT = "client"
    SERVER = "server"
    BOTH = "both"
    UNKNOWN = "unknown"


class ClaimStatus(StrEnum):
    HYPOTHESIZED = "hypothesized"
    CORROBORATED = "corroborated"
    FALSIFIED = "falsified"
    CONTESTED = "contested"


class TraceCheck(BaseModel):
    """An executable claim: after a reset, apply ``inputs``; output i must equal ``expect[i]`` (None = don't care)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    inputs: list[str]
    expect: list[str | None]

    @model_validator(mode="after")
    def _same_length(self) -> TraceCheck:
        if len(self.inputs) != len(self.expect):
            raise ValueError("inputs and expect must have the same length")
        return self


class ClaimIdentity(ContentAddressed):
    PREFIX: ClassVar[str] = "clm"

    feature: str
    kind: ClaimKind
    statement: str
    check: TraceCheck
    strictness: Strictness = Strictness.MUST
    origin: Origin = Origin.OBSERVED
    layer: Layer = Layer.UNKNOWN
    reference: str = Field(description="Fingerprint of the reference build the claim was observed on.")
    mapper: str = Field(description="Mapper version that defines the output symbols in `check`.")


class Claim(BaseModel):
    """A falsifiable behavior claim with its current evidence state."""

    model_config = ConfigDict(extra="forbid")

    identity: ClaimIdentity
    status: ClaimStatus = ClaimStatus.HYPOTHESIZED
    probes: int = 0
    confirming: int = 0
    contradicting: int = 0
    evidence: list[str] = Field(default_factory=list)
    counterexamples: list[list[str | None]] = Field(default_factory=list)

    @property
    def id(self) -> str:
        return self.identity.id


class UnknownStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    OUT_OF_SCOPE = "out-of-scope"


class UnknownIdentity(ContentAddressed):
    PREFIX: ClassVar[str] = "unk"

    feature: str
    question: str


class Unknown(BaseModel):
    """Missing coverage is unknown, not absence."""

    model_config = ConfigDict(extra="forbid")

    identity: UnknownIdentity
    status: UnknownStatus = UnknownStatus.OPEN
    recommended_probes: list[str] = Field(default_factory=list)
    note: str = ""

    @property
    def id(self) -> str:
        return self.identity.id
