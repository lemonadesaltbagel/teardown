# Clean runtime: an enforced clean room on one machine

The dirty zone is your machine: the project, the original, and the gate. The clean zone is a container. The
implementer agent runs inside it and can reach three things only:

1. the gate, which serves the released spec, answers tickets, and verifies clones built from the kit;
2. the model API, so the agent can think;
3. optionally, one backend API that the kit names (for web clones whose frontend calls a shared backend).

Everything else is unreachable: the internet, the host, the original, and the project directory.

```bash
teardown export-clean --project P --out KIT [--api http://127.0.0.1:8000/api]
teardown cleanroom up    --project P --kit KIT [--api http://127.0.0.1:8000/api] [--clone web:kit|cli:build:/kit]
teardown cleanroom check --project P [--original-port 4300]   # isolation probes, run from inside the container
teardown cleanroom shell --project P                          # a shell in the clean zone (or: ... shell -- claude)
teardown cleanroom down  --project P
```

### A backend on the same port as the UI

When the original serves its frontend and its API on one port, allowing that port as `--api` would also let the
implementer fetch the original's frontend (`cleanroom check` reports it as a failed refusal). Put the API-only
proxy in front and give its port instead:

```bash
teardown api-proxy --listen 18090 --backend http://127.0.0.1:8080 --allow /api /auth
teardown export-clean --project P --out KIT --api http://127.0.0.1:18090
teardown cleanroom up --project P --kit KIT --api http://127.0.0.1:18090
```

Requests under the allowed prefixes are forwarded; everything else answers 404.

## What `up` starts

| | where | sees | network |
|---|---|---|---|
| gate (`gate-serve --kit`) | host process | project, kit | 127.0.0.1 only |
| `egress` | container | nothing (read-only, no capabilities) | `cleanroom` + `outside` |
| `clean` | container (`deploy/Dockerfile.clean`: Python, Node, Claude Code, Teardown) | the kit at `/kit` | `cleanroom` only (`internal: true`) |

- **The gate in kit mode** accepts only `web:kit` (it serves `<kit>/impl` itself) and `cli:build:/kit` (it
  builds the kit's Dockerfile). Any other target spec, such as a URL, a local command or a Python class, is
  refused with 403. The token is generated per session and stored in `<project>/.cleanroom/`, never in the kit.
- **The egress proxy** (`teardown egress-proxy`) forwards CONNECT and plain HTTP only to an exact `host:port`
  allowlist:
  - the gate (`host.docker.internal:<port>`);
  - `api.anthropic.com:443`, unless `--no-model-api`;
  - the `--api` host;
  - any `--allow` you add.

  Every attempt, allowed or refused, is a JSON line in `<project>/.cleanroom/egress.jsonl`.
- **The clean container** runs read-only, as an unprivileged user, with no capabilities, with `/tmp` and its home
  on tmpfs, and with the proxy set in `HTTP(S)_PROXY`. `verify` inside it runs `teardown remote-verify` against
  the gate. `$TEARDOWN_API_URL` is the kit's API as reachable from the container. The clone itself still calls the
  address the kit's README gives, because the gate runs it on the host.
- **Claude Code inside** reads `/etc/claude-code/managed-settings.json`, which denies `WebSearch` and `WebFetch`
  and turns off telemetry and other non-essential traffic. Pass credentials from your shell, e.g.
  `CLAUDE_CODE_OAUTH_TOKEN=$(claude setup-token)` or `ANTHROPIC_API_KEY`, before `up`. They stay in the
  container's environment and never enter the kit.

## Checking it

`cleanroom check` runs these probes inside `clean`:
- the gate answers through the egress proxy;
- there is no direct route to the internet or to the original;
- the proxy refuses `example.com` and the original's port;
- the proxy allows the model API;
- the project directory is not visible, and the kit is the only bind mount.

It exits non-zero if any probe fails.

## Limits

- The container shares the kernel and Docker Desktop VM with your machine. It is isolation by namespaces and
  networks, not a separate machine.
- The model API is reachable by design. What the agent sends there is governed by your model provider's terms,
  not by Teardown.
- A web clone runs in the gate's browser on the host, with the same third-party blocking as the original.

## The observer room

The same pattern confines the dirty side's *agent*: it can observe the target only through Teardown's drivers.

```bash
teardown observerroom up    --project P --workspace W --claude-token-file ~/.config/teardown-claude-token
teardown observerroom check --project P --target-port 4300 --target-port 8000
teardown observerroom shell --project P -- room-claude      # Claude Code with only the observe MCP server
teardown observerroom down  --project P
```

- The observe MCP server runs on the host over HTTP (`teardown observe --port`, bearer token, Host-header check).
  The drivers keep their privileges there (Docker, browser, adb).
- The observer container mounts only its scratch workspace at `/work`. Put public documents there (the guide, a
  manual, a public markup contract).
- Egress allows the observe server and the model API, never the target. The agent cannot fetch bundles, read the
  target's files or source, or reach the internet. What it learns comes through behavior-tier observations.
- `check` probes for the target's ports, the internet, the project directory and the Teardown repository (which
  may hold reference sources).

This makes "behavior-first" a property of the environment, not of the prompt. One gap remains that no room can
close: what the observer's model already remembers about a famous target.
