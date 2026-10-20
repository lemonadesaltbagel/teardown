# Clean runtime (deploy/compose.yaml)

Two services, one barrier:

| | gate (dirty zone) | clean (implementer) |
|---|---|---|
| sees | the project directory, the kit (read-only), the Docker socket | the kit directory only |
| network | `cleanroom` + `outside` | `cleanroom` only (`internal: true`: no internet, no host) |
| runs | `teardown gate-serve` (spec, verify, tickets; bearer token) | your implementer; `teardown remote-verify --clone cli:build:/kit` |

```bash
TEARDOWN_PROJECT=/abs/project TEARDOWN_KIT=/abs/kit GATE_TOKEN=$(openssl rand -hex 16) \
  docker compose -f deploy/compose.yaml up -d --build
docker compose -f deploy/compose.yaml exec clean teardown remote-verify --clone cli:build:/kit
```

Verified behavior (2026-10-20): from `clean`, the gate answers, `https://example.com` does not resolve, `/project`
does not exist, and a remote verification of a 470-probe spec (the gate builds the clone image from the kit) returns
an abstract verdict.

What is still yours to add, depending on the implementer:

- **Model API egress.** An agent inside `clean` needs its model endpoint. Add an egress proxy (e.g. Squid/Envoy) on
  the `cleanroom` network that allows only that host, and point the agent at it. Do not attach `clean` to `outside`.
- **Agent configuration.** For Claude Code inside `clean`: a fresh `CLAUDE_CONFIG_DIR`, managed settings that deny
  `WebSearch`/`WebFetch`, sandbox on with `failIfUnavailable`, `allowUnsandboxedCommands: false`, and only the
  `teardown clean --gate-url http://gate:8765` MCP server registered.
- **Package mirror.** If the implementation may use third-party packages, provide a mirror on `cleanroom` that blocks
  the target's own packages.
- **Clone execution.** `cli:build:/kit` builds and runs the clone through the gate's Docker daemon with the same
  locked-down container settings as the original (no network, read-only root, unprivileged user).
