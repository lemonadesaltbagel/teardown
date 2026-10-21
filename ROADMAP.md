# Teardown roadmap

*This roadmap follows from `DESIGN.md`.*

- **Sizes** are relative effort: S, M, L, XL.
- **Exit criteria** are measurable against hidden oracles.
- **Spike code** in `spikes/` is a reference only. It gets rewritten into `teardown/`, not copied.

## Phase 0: core skeleton (M)

- [x] Repo setup: Python ≥3.12, uv, CI. (License deferred to the end; pre-commit not added.)
- [x] Schemas, content-addressed in the style of REA `ev_<sha256>`: `Evidence` (with `observation_tier`), `Trace`, `MapperVersion`, `Claim`, `Unknown`, `QuoteEntry`, `SpecRelease`, `AbstractVerdict`, `ModelRecord`, `SpecDraft`, `Intake`.
  - [ ] Still to add: `AbstractTrace` and `RefinementEvent` (land with mapper refinement in Phase 1); `Ticket` is plain JSON for now.
- [x] Trace store and persistent observation tree, used as the query cache for every learner.
- [x] Driver contract and a fake in-memory driver; the spike's signup wizard is ported as the fake target (`teardown.examples.signup`) and serves as the test ground truth.
- [x] EFSM IR, a reference interpreter with generate and trace-acceptance modes, and EARS / XState exporters. (Hypothesis/fast-check suite export: Phase 1.)
- [x] Gate v0:
  - [x] Observed-string corpus.
  - [x] Exact-match check with a suffix automaton.
  - [x] Quote ledger.
  - [x] Codename map.
  - [x] Warn / block switch for standard vs strict mode.
- [x] Clean MCP v0: `get_spec`, `ask_question`, `verify_against_original` returning abstract verdicts only.
- [x] Audit v0: hash-chained JSONL of in-toto statements, covering the `observation-session`, `spec-release` and `verdict` predicates.
- [x] Intake: declared purpose, jurisdiction, ToS snapshot, target fingerprint and warnings. Hard refusals live in the driver layer.
- **Exit (met 2026-10-19, `tests/test_roundtrip.py`, `teardown demo`):** one claim makes the full round trip: observe → gate → clean → verdict, using the fake driver.

## Phase 1: CLI (M)

- [ ] Driver:
  - [x] Pipe mode with per-stream `stdin_mode`/`stdout_mode` (pipe, null, closed, full). **PTY mode: not yet.**
  - [ ] `wait_for` (regex, screen predicate or quiescence) — needs PTY mode.
  - [x] An `env -i` canonical environment (image PATH kept so the implementation under test resolves).
  - [ ] asciicast v3 evidence plus a stderr sidecar (evidence is currently the JSON observation).
- [x] Isolation: a persistent locked-down container session per worker (no network, read-only root, uid 65534,
  no caps) driven by a shell loop on a private static busybox; ~24 ms per reset+step, so overlayfs/bwrap is not
  needed yet. Local runner for native CLIs.
- [ ] Interface discovery:
  - [x] Parse help into a neutral argument model (prose kept as dirty evidence only).
  - [ ] Completion scripts and man pages.
  - [x] Confirm the model by behavior: unknown-option reference, sentinel files, minimal valid invocation.
- [x] Probe planner:
  - [x] Pairwise combinations over accepted value classes only (two-phase planning).
  - [x] Single-fault probes for invalid values.
  - [x] Every argv element tagged as a factor; operand templates; stdio-mode probes.
  - [x] Permission faults: seeded `file_modes` on any invocation; planned unreadable-file probes.
- [x] `calibrate_noise`: reordered rerun plus a one-at-a-time env variation sweep (TZ, LC_ALL, LANG).
- [x] Comparison: behavior-level abstraction (`cli.behavior/v1`: exit, stdout, diagnostic + errno class, fs).
- [ ] Claim kinds:
  - [x] Decision-table claims (refusal / input-domain per option, operand, input, delivery mode, syntax edge,
    stdio mode), with value-class folding and multi-case checks.
  - [ ] `env-binding` (env dependence is recorded as an unknown for now), `config-precedence`, `signal-contract`.
- [ ] Learning:
  - [x] L#/KV over named CLI actions (`define_actions` + `learn_flow`), via the shared session.
  - [ ] TreeVada for file-input grammars.
- [x] Bench harness: jq (`tests/jq.test` 1.7.1, fetched at run time, pinned denominator 429). [ ] coreutils.
- **Exit:**
  - [x] The clean agent's jq clone is scored on the hidden jq tests: 394/429 (91.8%); conformance 1725/0.
    Memory-only control: 397/429 hidden, 132 conformance failures. The hidden suite is saturated by memorization
    for jq; the spec's value shows on observed behavior (see `research/09-jq-cleanroom-experiment.md`).
  - [ ] Uncontaminated benchmark: a CLI the implementer model cannot recognize (private/synthetic tool with its
    own hidden test suite), spec arm vs memory/docs arm. This is the only clean measure of spec value.
  - [ ] Observer-side coverage measurement (feature inventory per builtin/option, classes probed) so gaps like
    `abs`, path-expression errors and `strftime` errors are found before release.
  - [ ] Teardown specs beat README-only specs on a CLI-Tool-Bench subset.

## Phase 1.5: spec quality — done (round 2: spec arm 100%, `research/11-novel-benchmark-round2.md`)

Round 1 (`research/10`): spec arm 84.7% vs docs arm 97.0% on a novel CLI. After the items below, round 2 on a new
novel tool with an independent observer agent: **spec arm 397/397**, hybrid (spec + manual) 397/397, docs arm 395/397.

- [x] Observer-authored rule claims (`check_rules`: outcome / same / differs), released with observed symbols and
  verified as relations on the clone; works for CLI invocations and UI action sequences.
- [x] Feature inventory + coverage report; uncovered items become unknowns (`coverage`).
- [x] Generic input mutations and observer mutation lines; designed probes; per-option value classes.
- [x] Docs ingestion (gate corpus) and documentation/behavior conflicts as unknowns.
- [x] Observer guide (`docs/observer-guide.md`) for observer agents.
- [x] Re-run the novel benchmark: done (round 2).
- [x] Coverage gate that *blocks* release in strict mode when inventory items are uncovered (or coverage was never
  measured), unless a named human acknowledges the gaps (audited).
- [x] Rule-authoring loop: falsified rules come back with concrete rewrite suggestions from the observed symbols.
- [x] Explicit gate decision for byte-exact prose required by behavior: `approve_observed_output` approves help/
  usage/version output as functional quotes (compat_reason user-required, approver recorded). User decision
  2026-10-20: approve as functional quote; applied to the round-2 release.
- [ ] More rounds (more tools, other domains, several runs) for variance; observer effort/quality as a variable.

## Phase 2: web (L)

- [x] Driver: embedded Playwright-py (Chromium), role/name actions, fast forced actions after own presence/enabled
  checks, network-aware settle (in-flight requests), post-action grace, third-party hosts blocked, relative `goto`.
- [x] Capture filter: accessibility snapshot, URL path, constraint-validation state, API exchanges (method, path
  template, status) and value-free JSON body shapes only. No script/style bodies, no `evaluate` on app globals.
- [x] Determinism profile: timezone/locale/viewport, reduced motion, seeded PRNG, service workers blocked.
- [x] Reset for self-hosted targets: `reset_command` (Conduit: SQLite restored inside the API container) +
  `reset_check_url` (fails loudly on leaked state). Shared backends run episodes sequentially.
- [x] Client vs server classification of field refusals (no request / disabled submit vs API 4xx).
- [x] API contract skeleton (OpenAPI-style, shapes only) released with web specs.
- [x] Field probing with length boundaries; web rules over action sequences; learning (19-state signup = truth).
- [x] Web clean-room kits (`export-clean`, `verify-web`), clean-side adapters, web testability contract.
- [x] RealWorld E2E harness (`bench/conduit/e2e.py`); original passes 101/123 (pinned denominator).
- [x] Query strings in route and network symbols.
- [x] Fault-injection action (`op: fault`: 5xx / abort / timeout / malformed JSON on matching API calls) so error
  handling is observable; documented in the observer guide.
- [x] Re-run the Conduit experiment with query strings + fault probes: 93/101 (was 80; target ≥ 95). The remaining 8
  are empty elements (page wrapper after a failed load, empty bio) that the accessibility view cannot see.
- [x] Contract-selector observations (`contract_selectors` with a public source): absent/hidden/empty/content.
- [x] `hang` / `release` faults: calls held pending so loading/disabled states are observable.
- [x] Conduit round 3 with both: 95/101 (target met). Found: CDN icon fonts blocked during observation (fixed:
  `profile.asset_hosts`), server-clock dates drifting across days (fixed: `mask_dates` + compile-time unknown).
- [x] Conduit round 4 with `asset_hosts` + `mask_dates`: 99/101; conformance 576/576. The last 2 need DOM beyond
  the public contract.
- [ ] Held-out web benchmark (an app with its own hidden E2E suite that the web tooling was not tuned on).
- [ ] CDP coverage for exploration steering; APE-style state-key refinement; HAR freeze for 3-way layering.
- [ ] TodoMVC benchmark; SaaS limited-reset mode.
- **Exit:** Conduit clone from a Teardown web spec + the public selectors contract, scored on the hidden E2E
  suite — see `research/12-web-conduit.md`.

## Phase 3: the barrier as a product (M)

- [x] Gate HTTP service (`gate-serve`, bearer token) and remote clean room (`clean --gate-url`, `remote-verify`).
- [x] Docker Compose clean runtime: internal network (no internet, no host), kit-only volume, read-only root, no
  caps; verified end to end (`docs/clean-runtime.md`). `cli:build:<dir>` clones built by the gate.
- [x] DSSE-signed audit entries (ed25519 per zone) + chain verification.
- [x] Winnowing near-verbatim detection; functional-quote approval; strict-mode coverage gate.
- [x] Stack traces redacted at capture.
- [x] Strict gate for one developer: classified findings (expected-output / interface / prose), recorded
  approvals (class scope only for functional classes), terminal-only `teardown approve`, no approvals through
  the observer's MCP tools (`docs/strict-gate.md`).
- [x] Enforced clean room on one machine (`teardown cleanroom up/check/shell/down`): kit-only gate (clone target
  allowlist), allowlisting egress proxy with a per-attempt log, clean image with Claude Code and managed settings,
  isolation probes (8/8) (`docs/clean-runtime.md`).
- [x] Full rounds with the implementer inside the clean room: web 99/101, CLI 397/397, matching the
  prompt-only rounds; only allowlisted egress (`research/13-enforced-clean-room-rounds.md`).
- [x] Observer room: the observer agent confined to the observe MCP server (HTTP) and a scratch workspace; the
  target is never in its egress allowlist (11 isolation probes). Round 6 with both sides confined: 93/101
  (`research/13`); its gaps led to automatic endpoint x fault coverage.
- [ ] Package registry mirror with a block list (for implementations that may use third-party packages).
- [ ] MinHash, distinctiveness scoring, auto-built identifier denylist, advisory LLM judge, review UI.
- [ ] Memorization probes and spec canaries; post-hoc similarity reports (Dolos/JPlag/PDQ); RFC 3161 checkpoints.

## Release readiness (CLI + web)

- [x] README and docs match the code; evaluation method documented (`docs/evaluation.md`).
- [x] Fresh clone: `uv sync`, `teardown demo`, test suite pass. CI workflow (lint + tests).
- [ ] License (owner's decision) and the go-ahead to publish.

## Phase 4: Android (L)

- [x] SDK + emulator installed (cmdline-tools, platform-tools, emulator, android-34 google_apis arm64, AVD).
- [x] adb driver: role/accessible-name actions, `pm clear` + resolved launcher activity reset, animations off.
- [x] On-device observer agent (UiAutomation over a forwarded socket): 4-16 ms dumps, exact hint detection;
  steps 0.26-0.36 s, reset 0.65 s (vs ~6 s / 4.8 s with uiautomator dump).
- [x] Resource ids / activity names kept out of observations; one device = sequential episodes.
- [x] Example target + variant built without Gradle; end-to-end test (probe, rules, release, verify, variant caught).
- [ ] Snapshot-load reset tier; determinism after load (clock via root on google_apis).
- [ ] Network tiers N0/N1/N2; logcat reduced to system events; deep links/intent filters as interface facts.
- [ ] Intake detectors (FLAG_SECURE, attestation failure, no-tree apps).
- [ ] Bench: Loop Habit Tracker / Omni-Notes / AntennaPod with hidden Espresso suites (needs Gradle builds).

## Phase 5: desktop, Linux then macOS (XL)

- [x] Linux AT-SPI backend in a container (Xvfb + D-Bus + AT-SPI + GTK) with an in-container agent; GTK example
  target; end-to-end test (probe, rules, release, verify, variant caught).
- [ ] macOS AX backend: Tart VM (≈25 GB image; disk is tight) or an explicitly consented host mode.
- [ ] Windows UIA backend.
- [ ] Menu inventory as feature list; `observe_effects` (prefs/data diff, mitmproxy local mode).
- [ ] Electron apps routed to the web driver when fuses allow; Qt accessibility flags; XTest fallback.
- [ ] Bench: GNOME app, Joplin.

## Later: rough tasks, not scheduled

- [ ] **Windows desktop.** A UIA backend (FlaUI or `uiautomation`), Hyper-V checkpoints, RDP-loopback isolation, and UFO2-style fusion of UIA with OmniParser. Bench: Windows Calculator UI tests via NovaWindows.
- [ ] **iOS.** iOS-on-Mac through the AX backend (tag `platform: ios-on-mac`), then the Simulator for open-source apps (Wikipedia, and Firefox's `FxScreenGraph` as state-machine ground truth), then real device plus WDA.
- [ ] **Canvas, WebGL and game apps.** A vision-only observer (OmniParser v2 / UI-TARS / CUA), serialization-based observation (export, clipboard, IndexedDB), and masked visual hashes. Spike on tldraw and Penpot first.
- [ ] **Realtime collaboration.** Several browser contexts in lockstep, partial-order claims, WebSocket replay, stochastic learners. Bench: Mattermost and Element.
- [ ] **Register automata.** A RALib sidecar for data-dependent flows. Evaluate Tomte-style abstraction vs SL^λ.
- [ ] **LearnLib sidecar.** AAAR alphabet refinement and procedural (SPA) decomposition for large apps.
- [ ] **Checkpoint/restore of app state.** Prefix replay was 42% of web steps.
- [ ] **TUI frame-claim suite.** Own hidden suites for nnn/tig/lazygit.
- [ ] **Mapper-validity benchmark.** Apps with known statecharts plus seeded mutants, to measure how often the LLM-written abstraction is wrong. This is a research risk to track.
- [ ] **Publish the benchmark.** Clean-room behavior extraction measured against hidden oracles, with pinned oracle versions and published denominators.
- [ ] **Hosted clean-room service.** Optional, built on the open-source core.
