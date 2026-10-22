# Teardown

Clean-room, behavior-first reimplementation of application features.

A **dirty side** observes a target program as a black box: what it accepts, refuses and defaults to, what it does
at the edges, and how its UI is sequenced. It states that as falsifiable claims and rules, and releases a sanitized
specification through a **gate**. A **clean agent**, fed only that release, reimplements the feature independently.
It checks its work against the original but gets back abstract verdicts only, never the original's code, text or
evidence.

```
 dirty zone (your machine)                                    clean zone (isolated container)
 ┌───────────────────────────────────────────┐               ┌──────────────────────────────┐
 │ target ──drivers──▶ observations          │   released    │ implementer agent            │
 │   ▼ mapper (behavior-level symbols)       │   spec (kit)  │   reads spec.json            │
 │ claims · rules · probe tables · models    │ ────────────▶ │   writes impl/               │
 │   ▼ gate (verbatim / near-verbatim /      │               │   asks `verify`              │
 │          denylist / strict approvals)     │ ◀──────────── │                              │
 │ verifier: runs original vs clone ─────────┼─ verdicts ───▶│   pass/fail + abstract diffs │
 │ audit log (hash-chained, signed)          │               │ egress: gate + model API only│
 └───────────────────────────────────────────┘               └──────────────────────────────┘
```

Teardown is an MCP toolkit plus a command line. Behavior is the valuable knowledge about a feature, and tracing an
implementation from binaries or obfuscated bundles does not scale to industrial targets. Teardown never captures
implementation-tier data at all.

## Status

| platform | driver | status |
|---|---|---|
| CLI | containerized runner (no network, read-only, unprivileged), help discovery, probe planner, decision-table mining, permission and stdio faults | **stable**: complete reimplementation of a private tool from the spec alone |
| Web | Playwright, accessibility-tree symbols, field probing, rules over action sequences, fault injection, contract selectors, API contract | **stable**: 99/101 on RealWorld's E2E suite (development-set, see caveats) |
| Android | adb plus an on-device UiAutomation agent, network-off fault, Gradle-free clone builds | **working**: 113/118 on a novel app's hidden suite, both sides confined (one round) |
| Desktop (Linux) | Xvfb plus AT-SPI in a container | experimental: works on an example app |
| macOS, Windows, iOS | — | not started |

How these results were measured, and what they do and do not show: [`docs/evaluation.md`](docs/evaluation.md).

## Install

```bash
uv sync                                   # Python 3.12+
uv run playwright install chromium        # web targets
# Docker: needed for CLI targets (isolated runner) and for the enforced clean room
uv run teardown demo                      # observe -> gate -> clean -> verdict on a fake signup wizard
uv run pytest -q
```

## The loop

1. **Observe** (dirty side). Give an agent the observe MCP server and the guide
   ([`docs/observer-guide.md`](docs/observer-guide.md)):
   ```bash
   teardown observe --project P            # MCP on stdio: open_target, probe_cli / probe_web_field,
                                           # check_rules, learn_flow, coverage, compile/review/release
   ```
   Open the target with `strict=True` if every release should need your approval.
2. **Gate** (you). Review and approve at a terminal, then release. Approvals are recorded and signed
   ([`docs/strict-gate.md`](docs/strict-gate.md)):
   ```bash
   teardown review  --project P --feature F
   teardown approve --project P --feature F --by you@example.com --class expected-output --reason test-oracle
   teardown release --project P --feature F
   teardown export-clean --project P --out KIT [--api http://127.0.0.1:8000/api]
   ```
3. **Reimplement** (clean side). Start the enforced clean room and run your implementer inside it
   ([`docs/clean-runtime.md`](docs/clean-runtime.md)):
   ```bash
   teardown cleanroom up    --project P --kit KIT --claude-token-file ~/.config/teardown-claude-token
   teardown cleanroom check --project P              # isolation probes, run from inside the container
   teardown cleanroom shell --project P -- claude    # the agent sees only /kit; `verify` asks the gate
   teardown cleanroom down  --project P
   ```
   The clean MCP server (`teardown clean --gate-url ...`) offers the same through MCP: `get_spec`,
   `list_unknowns`, `ask_question`, `verify_against_original`.
4. **Audit.** `teardown audit-verify --project P` checks the hash chain of every intake, release, approval and
   verification.

## What Teardown never does

- Bypass CAPTCHAs, bot protection, certificate pinning, root or attestation checks, or FLAG_SECURE.
- Flip Electron fuses or re-sign binaries.
- Use fake accounts or exceed configured rate limits.
- Capture implementation-tier data (code bodies, decompilation, stack traces; traces are redacted at capture).

What cannot be observed becomes an explicit *unknown*. These refusals are not configurable.

You declare the purpose of an analysis at intake and own its legal assessment. Teardown records your declarations
and shows applicable warnings. A clean room addresses copying of expression; it does not address patents,
trademarks or trade dress.

## Documentation

- [`docs/observer-guide.md`](docs/observer-guide.md): driving the dirty side (CLI and web)
- [`docs/strict-gate.md`](docs/strict-gate.md): reviewing and approving releases
- [`docs/clean-runtime.md`](docs/clean-runtime.md): the enforced clean room
- [`docs/evaluation.md`](docs/evaluation.md): the evaluation method and results
- `DESIGN.md` (decisions and architecture), `ROADMAP.md` (status and plan), `research/` (experiment reports)

## Layout

```
src/teardown/
  core/      content-addressed records, workspace, observation tree
  drivers/   cli/ web/ android/ desktop/ + driver contract, hard-refusal policy, observation session
  engine/    mapper and built-in abstractions, learner (AALpy KV / L#), claims, rules, mining, field probes
  spec/      EFSM IR, EARS / XState exports, spec drafts and release projection
  gate/      matchers, gate review/release and approvals, verifier, gate service, egress proxy
  audit/     hash-chained in-toto statements with DSSE signatures
  mcp/       observe and clean MCP servers
deploy/      clean-room containers (cleanroom.yaml), desktop and Android agents
bench/       harnesses for hidden-suite scoring
```

License: not yet chosen.
