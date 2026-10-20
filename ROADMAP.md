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

- [ ] Driver:
  - [ ] Embedded Playwright-py on Chrome for Testing.
  - [ ] CDP used only for the full AX tree and for coverage that steers exploration.
  - [ ] Fast actions (force-click after our own checks).
  - [ ] Capture filter: HAR omits code bodies, DOM evidence has no `<script>`/`<style>`, `evaluate` is allow-listed.
- [ ] State key `(route_tmpl, overlay_stack, auth_role, H_aria, form_vec)`, with APE-style split and merge and secret masking.
- [ ] Determinism profile: clock, seeded PRNG, fixed timezone/locale/viewport, service workers blocked during replay.
- [ ] Reset:
  - [ ] DB/filesystem snapshots for self-hosted targets.
  - [ ] Checks after each reset: fingerprint, sequence witness and canary.
  - [ ] Limited-reset mode for SaaS.
- [ ] Classify each behavior as client, server or both, by comparing three runs: live, HAR-frozen, and direct API where policy allows.
- [ ] mitmproxy2swagger → OpenAPI → Schemathesis.
- [ ] Equivalence oracle:
  - [ ] Explicit budget.
  - [ ] LLM-proposed round-trip probes.
  - [ ] States learned versus budget reported as an `unknown`.
- [ ] Semantic output symbols, or comparison up to output renaming (port `compare.py`).
- [ ] Bench: TodoMVC (32 tests), then RealWorld (128 E2E tests plus API suites). Report raw and selector-adapted scores.
- **Exit:** RealWorld clone scored on its hidden E2E and API suites.

## Phase 3: the barrier as a product (M)

- [ ] Docker Compose for the dirty, gate and clean zones:
  - [ ] Default-deny egress via iptables.
  - [ ] Verdaccio/devpi mirror with a block list.
  - [ ] Fresh `CLAUDE_CONFIG_DIR`.
  - [ ] Managed settings template.
- [ ] Gate v1:
  - [ ] Winnowing and MinHash near-match checks.
  - [ ] Distinctiveness scoring.
  - [ ] Auto-built identifier denylist.
  - [ ] LLM judge (advisory).
  - [ ] Review UI for strict mode.
  - [ ] Verdict abstractor with budgets and closure of the equality oracle.
- [ ] Memorization probes (identification, completion, structural, cross-model) and spec canaries.
- [ ] Post-hoc similarity reports: Dolos and JPlag for web bundles, imagehash/PDQ for assets.
- [ ] Remaining audit predicates (`clean-session`, `similarity-report`), DSSE signing, RFC 3161 checkpoints.
- **Exit:** a full audit dossier for the RealWorld run. The clean runtime passes a leak test covering all 6 known channels, plus WebFetch.

## Phase 4: Android (L)

- [ ] Setup script: cmdline-tools, emulator and an arm64 `google_apis` image (about 10–20 GB); compose file for the macOS host and for Linux KVM.
- [ ] uiautomator2 driver:
  - [ ] Semantic actions (role + label + ordinal).
  - [ ] Normalized a11y-tree hash.
  - [ ] Never key on resource-id or activity names.
- [ ] Reset ladder (`pm clear` → snapshot load → wipe), with determinism settings re-applied after every load.
- [ ] Network tiers N0, N1 and N2.
- [ ] Logcat reduced to system-level events.
- [ ] Deep links and intent filters recorded as interface facts.
- [ ] Intake detectors: FLAG_SECURE, attestation failure, apps with no a11y tree (Flutter, Unity).
- [ ] Learning:
  - [ ] Passive EDSM from exploration traces, then active resolution of conflicts.
  - [ ] Soft "homing" resets.
- [ ] A "testability contract" section in the spec.
- [ ] Bench: Loop Habit Tracker, Omni-Notes, AntennaPod, and their hidden Espresso suites. JaCoCo runs in the harness only.
- **Exit:** clone pass rates on the hidden Espresso suites of the three apps.

## Phase 5: desktop, Linux then macOS (XL)

- [ ] AT-SPI backend in Docker + Xvfb, with Qt accessibility flags and XTest as the fallback.
- [ ] AX backend in Tart VMs:
  - [ ] TCC permissions baked into the image.
  - [ ] Guest clock control.
  - [ ] `reduceMotion` set in the guest.
  - [ ] Container-directory reset.
  - [ ] Fingerprint check after each reset.
- [ ] `menu_inventory()` as the seed for the feature list and the learning alphabet. Enabled states become predicates.
- [ ] `observe_effects`:
  - [ ] Prefs and data-directory diff.
  - [ ] mitmproxy local mode.
  - [ ] File-event tracer, limited to the `effect` tier.
- [ ] Electron apps routed to the web driver, but only when the app's fuses allow it.
- [ ] Bench: a GNOME app (dogtail), then Joplin (Playwright `_electron`).
- **Exit:** Joplin clone scored on its hidden integration tests.

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
