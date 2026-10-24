"""CLI invocations: what one CLI action does (argv, stdin, seed files, environment, stdio modes).

Byte payloads are stored as latin-1 strings so every byte value round-trips through JSON unchanged.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

StdinMode = Literal["pipe", "null", "closed"]
StdoutMode = Literal["pipe", "null", "closed", "full"]

# PATH is deliberately absent: the target image (or host) PATH is kept so the implementation under test resolves.
BASE_ENV = {"LC_ALL": "C", "TZ": "UTC", "LANG": "C", "HOME": "/w/home"}


def to_bytes(text: str | None) -> bytes | None:
    return None if text is None else text.encode("latin-1")


def from_bytes(data: bytes | None) -> str | None:
    return None if data is None else data.decode("latin-1")


class Invocation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    argv: list[str] = Field(description="Full argv including the program name.")
    stdin: str | None = Field(default=None, description="latin-1 encoded bytes fed to stdin (stdin_mode=pipe).")
    files: dict[str, str] = Field(default_factory=dict, description="Files written into the work dir first.")
    file_modes: dict[str, str] = Field(
        default_factory=dict, description="Octal permission modes for seed paths (files or their directories), e.g. "
                                          "{'in.txt': '000'} (unreadable) or {'out': '555'} (read-only directory). "
                                          "Part of the starting state: the program runs as an unprivileged user.")
    env: dict[str, str] = Field(default_factory=dict, description="Overrides on top of the canonical environment.")
    stdin_mode: StdinMode = "pipe"
    stdout_mode: StdoutMode = "pipe"
    timeout_s: float = 10.0

    def full_env(self) -> dict[str, str]:
        return {**BASE_ENV, **self.env}
