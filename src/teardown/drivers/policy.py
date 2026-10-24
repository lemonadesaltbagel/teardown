"""Hard refusals and rate limits.

These are not policy preferences and are not configurable: they are circumvention of technical protection measures
or of the target operator's controls. When something cannot be observed without them, it becomes an ``unknown``.
"""

from __future__ import annotations

import time

from teardown.drivers.base import Action

PROHIBITED_CATEGORIES: dict[str, str] = {
    "bypass-captcha": "solving or bypassing CAPTCHAs or bot-protection challenges",
    "bypass-pinning": "bypassing certificate pinning (Frida/objection hooks, repackaging, Xposed/Magisk)",
    "bypass-attestation": "bypassing root, emulator or attestation detection",
    "bypass-flag-secure": "capturing screens the app protects with FLAG_SECURE or equivalents",
    "flip-fuse": "flipping Electron fuses or enabling debug ports the app disabled",
    "resign-binary": "re-signing or modifying the target to strip hardened-runtime or other protections",
    "fake-account": "creating accounts under false identities",
    "decompile": "decompiling, disassembling or reading code bodies of the target (implementation tier)",
}


class HardRefusal(PermissionError):
    def __init__(self, category: str):
        super().__init__(
            f"refused: {PROHIBITED_CATEGORIES.get(category, category)}. Teardown never does this; record what "
            "cannot be observed as an unknown instead."
        )
        self.category = category


def check_action(action: Action) -> None:
    if action.category in PROHIBITED_CATEGORIES:
        raise HardRefusal(action.category)


class RateLimiter:
    """Simple minimum-interval limiter; the budget comes from intake and is never exceeded."""

    def __init__(self, max_actions_per_second: float | None):
        self.interval = 1.0 / max_actions_per_second if max_actions_per_second else 0.0
        self._last = 0.0

    def wait(self) -> None:
        if not self.interval:
            return
        now = time.monotonic()
        delay = self._last + self.interval - now
        if delay > 0:
            time.sleep(delay)
        self._last = max(now, self._last + self.interval)
