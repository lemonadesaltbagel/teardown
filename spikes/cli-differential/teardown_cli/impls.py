"""Registry of implementations under test.

Each implementation is a container image in which the command name resolves (via PATH)
to that implementation. The harness never uses the implementation's own coreutils to
*measure*: setup is done by `tar` + shell builtins, and diffing happens on the host.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Impl:
    key: str          # short id used in results
    image: str        # docker image
    family: str       # gnu | uutils | busybox
    version: str
    # regexes (anchored at line start) for the "program name:" prefix this impl
    # puts on diagnostics; used only by normalization, never by probing.
    progname_prefixes: tuple[str, ...] = ()


IMPLS: dict[str, Impl] = {
    i.key: i
    for i in [
        Impl("gnu", "debian:stable-slim", "gnu", "9.7", (r"{cmd}: ",)),
        Impl("uutils", "teardown/uutils:0.12.0", "uutils", "0.12.0", (r"{cmd}: ", r"uu_{cmd}: ")),
        Impl("busybox", "busybox:latest", "busybox", "1.38.0", (r"{cmd}: ", r"busybox: ")),
        # bonus: the uutils that Ubuntu 25.10 ships as its default coreutils (version-drift datapoint)
        Impl("uutils022", "ubuntu:25.10", "uutils", "0.2.2", (r"{cmd}: ", r"uu_{cmd}: ")),
        # bonus: newer GNU (same lineage) -> how much do two GNU releases differ?
        Impl("gnu910", "fedora:latest", "gnu", "9.10", (r"{cmd}: ",)),
    ]
}

# Deterministic baseline environment for every probe.
BASE_ENV = {"LC_ALL": "C", "TZ": "UTC", "HOME": "/w"}
