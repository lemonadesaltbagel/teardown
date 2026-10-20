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
  - [ ] Pipe and PTY modes, with a per-stream `stdio_mode` setting.
  - [ ] `wait_for` (regex, screen predicate or quiescence).
  - [ ] An `env -i` canonical environment.
  - [ ] asciicast v3 evidence plus a stderr sidecar.
- [ ] Isolation: one container per batch with fresh directories per probe. Add an overlayfs/bwrap fast path on Linux. Benchmark reset cost in week 1.
- [ ] Interface discovery:
  - [ ] Parse help, completion scripts and man pages into a neutral argument model.
  - [ ] Confirm the model by behavior: unknown-option reference, sentinel files, minimal valid invocation.
- [ ] Probe planner:
  - [ ] Pairwise combinations over valid value classes only.
  - [ ] Single-fault probes for invalid values.
  - [ ] Every argv element tagged as a factor.
- [ ] `calibrate_noise`: repeated runs plus a reprotest-style one-at-a-time variation sweep.
- [ ] Comparison: the behavior-level tiers (side effects → exit/error class → normalized stdout) and the normalization stack.
- [ ] Claim kinds:
  - [ ] `stdio-mode-dependence`
  - [ ] `env-binding`
  - [ ] `config-precedence`
  - [ ] `exit-code`
  - [ ] `signal-contract`
  - [ ] `stream-attribution`
- [ ] Learning:
  - [ ] L#/KV for REPL modes.
  - [ ] TreeVada for file-input grammars.
- [ ] Bench harness: jq (`tests/jq.test`) and 5 coreutils against the GNU tests, run hidden and fetched at test time, never vendored.
- **Exit:**
  - The clean agent's jq clone is scored on the hidden jq tests.
  - Teardown specs beat README-only specs on a CLI-Tool-Bench subset.

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
