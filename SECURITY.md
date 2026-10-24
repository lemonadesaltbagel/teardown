# Security policy

Teardown's purpose is a barrier between what the observer sees and what the clean implementer receives. Anything
that weakens that barrier is a security issue.

## In scope

- **Leaks to the clean side:** the target's text, evidence, real names or other dirty-side detail reaching the
  clean side outside a gate release (verdicts, error messages, kits, gate service responses).
- **Escaping a room:** reaching the internet, the host, the original or the project from the clean or observer
  room, or bypassing the egress allowlist.
- **Gate bypasses:**
  - releasing in strict mode without recorded approvals;
  - approving through the observer's tools;
  - relaxing strict mode.
- **Audit-log tampering** that `teardown audit-verify` does not detect.
- **Capturing implementation-tier data**, or bypassing a hard refusal.

## Reporting

Report privately through GitHub's
[private vulnerability reporting](https://github.com/lemonadesaltbagel/teardown/security/advisories/new). Do
not open a public issue.

Include:
- the version (`teardown --version`);
- the target type;
- the steps to reproduce;
- what crossed the barrier and where it appeared.

Supported versions: the latest release.
