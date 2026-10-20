"""Intake: what the user declares before any observation, recorded in the audit log.

Teardown does not adjudicate the declared purpose; it records it and shows the warnings that apply. The hard
refusals in :mod:`teardown.drivers.policy` hold regardless of purpose.
"""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar

from pydantic import Field

from teardown.core.ids import sha256_hex
from teardown.core.model import ContentAddressed


class Purpose(StrEnum):
    INTEROP = "interop"
    SUBSTITUTE = "substitute"
    OWN_LEGACY = "own-legacy"
    RESEARCH = "research"


class Intake(ContentAddressed):
    PREFIX: ClassVar[str] = "itk"

    target: str = Field(description="Target fingerprint.")
    target_spec: str = Field(description="How the target was opened (driver-specific).")
    purpose: Purpose
    jurisdiction: str = ""
    account: str = ""
    terms_sha256: str | None = Field(default=None, description="Digest of the ToS/EULA snapshot taken at intake.")
    owner_declaration: str | None = None
    max_actions_per_second: float | None = None


def terms_digest(text: str | None) -> str | None:
    return sha256_hex(text.encode()) if text else None


def warnings_for(intake: Intake) -> list[str]:
    notes = [
        "You are responsible for the legal judgment about this analysis; Teardown records your declarations but "
        "does not adjudicate them. This is not legal advice.",
    ]
    if intake.purpose is not Purpose.OWN_LEGACY:
        notes.append(
            "A clean room is evidence of independent creation for copyright only. It does not avoid patents, "
            "trademarks or trade dress, and logged-in use may be bound by the target's terms of service."
        )
    if intake.purpose is Purpose.SUBSTITUTE:
        notes.append(
            "Consider strict mode (human sign-off on every spec release, symbol-only verdicts) and a different "
            "model provider/account for the clean implementer."
        )
    if intake.purpose is Purpose.OWN_LEGACY and not intake.owner_declaration:
        notes.append(
            "own-legacy needs an ownership declaration. Code with outside contributors is not your own legacy for "
            "relicensing purposes."
        )
    if intake.terms_sha256 is None:
        notes.append("No terms-of-service/EULA snapshot was recorded.")
    return notes
