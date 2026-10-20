# Teardown: decision report (research round 2)

*2026-10-19. Builds on `RESEARCH.md` (round 1). Evidence:*
- *six desk-research tracks: `research/01-web.md`, `02-cli.md`, `03-desktop.md`, `04-mobile.md`, `05-core-engine.md` and `06-gate-barrier-audit.md`;*
- *three hands-on spikes with measured results: `spikes/cli-differential/`, `spikes/web-learning/` and `spikes/desktop-ax/`.*

*This is not legal advice.*

---

## 1. Bottom line

**The full loop is technically feasible on all four platforms, but not equally.** What sets the difficulty on each platform is the same three things:

1. **Reset cost.** Active learning needs many resets, and their cost decides whether it is affordable.
2. **Accessibility-tree quality.** It decides whether observations are clean enough to write falsifiable claims.
3. **Legal and technical protections.** Bot walls, certificate pinning, attestation, FairPlay and FLAG_SECURE limit what may be observed.

| Platform | Full-loop feasibility | Why |
|---|---|---|
| **CLI** | 🟢 **High** | 3–8 ms per probe once batched. Strong hidden oracles (jq, GNU tests, CLI-Tool-Bench). The spike proved it end to end. |
| **Web (self-hostable)** | 🟢 **High** | Playwright covers every surface. Reset can be exact with DB snapshots. Ready-made hidden E2E suites (RealWorld, 128 tests). |
| **Web (remote SaaS)** | 🔴 Low–medium | Low reset fidelity. Bot walls and terms of service. Server time is out of your control. |
| **Android (open-source or sideloadable)** | 🟢 High | Native arm64 emulator, 2–10 s snapshot reset, uiautomator2, good open-source targets with hidden Espresso suites. |
| **Android (commercial Play apps)** | 🟡 Medium | About 25% of apps detect emulators, attestation fails, pinning applies. Expect specs that are mostly UI and carry many unknowns. |
| **Desktop: Linux** | 🟡 Medium-high | Containers with Xvfb and AT-SPI give cheap, parallel resets. Accessibility quality is uneven. |
| **Desktop: macOS** | 🟡 Medium | The best accessibility tree (spike: 239 nodes in 0.15 s, the full menu as a feature list). But Apple caps you at 2 VMs per Mac, and the hardened runtime blocks time faking. |
| **Desktop: Windows** | 🟡 Medium | Mature UIA, but about 62% of agent failures are controls UIA can't see (UFO2), so vision is mandatory for a meaningful share of apps. Heavy VM images. |
| **iOS (third-party apps)** | 🔴 Low | FairPlay rules out the Simulator, real devices reset poorly. Cheap fallback: "Designed for iPad" apps on Apple Silicon run through the macOS desktop driver. |

**Three findings change the design from round 1:**

1. **Compare behavior, never text.**
   - In the CLI spike, normalizing error-message text raised agreement by only 1.5 points.
   - Comparing at the behavior level instead (exit code, stdout bytes, whether a diagnostic appears, errno class, filesystem diff) raised it from 69.9% to 89.7%.
   - It is also the right legal stance: message wording is expression, while the condition that triggers a refusal is behavior.
2. **Proving equivalence costs far more than learning the model.** Equivalence testing is more than 90% of total query cost (the L# appendix and Kruger et al.).
   - Learning strategy must therefore be chosen per platform from reset cost.
   - Active L# works on CLI and web. Mobile and desktop need a passive/active hybrid with soft resets.
3. **LLMs are good at naming states and bad at stating structure.** On PSMBench, LLMs score up to 0.82 F1 on states but at most 0.38 on transitions.
   - So the LLM writes the *mapper*: deterministic, versioned code that turns UI and program observations into abstract symbols.
   - Automata learners and falsifiers supply the structure.
   - **No transition gets into the spec on an LLM's word alone.**

---

## 2. Measured spike results

### 2.1 CLI differential spike (`spikes/cli-differential/`, details in `research/07-spike-cli-differential.md`)

- **Targets:** GNU coreutils 9.7 as the reference; uutils 0.12, BusyBox 1.38, uutils 0.2.2 and GNU 9.10 as candidates. Commands: cut, seq, sort, head.
- **Speed:** the whole loop takes **47 s** from one command.
  - 1,775 probes and 17,750 executions run in 21 s of wall time.
  - That is **3.4–8 ms per probe in batches**, versus 139–202 ms with one container per probe.
- **Isolation held:** reset fidelity was exact (shuffled versus ordered runs differed only on `sort -R`).
- **Agreement with GNU at the behavior level:**
  - uutils 0.12: 89.7%
  - BusyBox: 75.8%
  - GNU 9.10: 99.8%, which is drift within the same lineage
- **Findings:** 111 behavior claims mined automatically; **ten real differences verified by hand**. Examples:
  - BusyBox `seq 1 0 3` loops forever.
  - uutils `sort -o` leaves the output file untouched on empty input. **Only the filesystem diff shows this.**
  - GNU applies the last of `head -c`/`-n`; BusyBox always lets `-c` win.
- **81 of uutils' 183 divergences are edges the GNU test suite does not cover.** That is direct evidence that probing finds behavior a vendor's own tests miss.
- **Discovering options from `--help` alone is unreliable.** Probing with the actual behavior caught a phantom `-M` option and several undocumented options (GNU `sort -y`, BusyBox `sort -S`, `-T`, `-m`).

### 2.2 macOS accessibility spike (`spikes/desktop-ax/`)

- **Read Calculator's accessibility tree:** 239 nodes in 0.146 s; 71% carry a stable `AXIdentifier`.
- **The menu bar works as a feature inventory:** 94 app-owned commands, 25 with keyboard shortcuts, plus the enabled state of each.
- **Probes took 11–18 ms each and found real claims:**
  - `1÷0` gives `Undefined` (a refusal);
  - `7+1===` gives `10` (repeats the last operation);
  - `0.1+0.2` gives `0.3` (decimal arithmetic).
- **Four gotchas:**
  - an invisible U+200E character in every displayed value;
  - accessibility identifiers that change with state (`AllClear` becomes `Clear`);
  - the system's own menus adding noise;
  - **state that persists across relaunch**, so a reset must clear the app's sandbox container.

### 2.3 Web learning spike (`spikes/web-learning/`, full report in `research/08-spike-web-learning.md`)

**What the loop does.**
- Playwright drives the app using role and name locators only.
- The page's accessibility snapshot is masked and hashed into an abstract state.
- AALpy KV or L# learns a state machine from those abstract states.
- Field probes and a differential runner compare the original against a clone.
- All of this works end to end against a 3-step signup wizard whose true model has 19 states.

**The learned models are exact.**
- With a large equivalence-oracle budget (random W-method, 100 walks × 20 steps), both KV and L# learned all **19 states, isomorphic to ground truth**, in about 650 s.
- That cost 2,184 resets and about 37k steps, at 48 ms per reset, 13 ms per action and 2 ms per snapshot.
- **The equivalence oracle took 88% of the time.** This confirms §1 finding 2.
- KV and L# use about 6× fewer learning queries than L*. **Drop L\*.**

**Silent incompleteness is the main danger.**
- With smaller oracle budgets, every learner stopped at **14 states**: 5 states of hidden memory were missing, and nothing warned about it.
- Those states sit behind a 9-step counterexample: the terms box stays ticked after going back twice and forward twice.
- Simulator replay confirms it: a 25×12 budget reached the full model in 0 of 5 seeds; 100×20 reached it in 4 of 5 seeds for KV and 2 of 5 for L#.

**Field probing was fast and precise.**
- 25 probes in 3.4 s recovered the email rule exactly: trimmed, required, contains `@`, at most 40 characters.
- They also surfaced permissive behavior: `@` alone, a double `@`, emoji and HTML-like input are all accepted.

**Differential testing caught both injected differences, with no false positives.**
- **"Back clears the password":** found in 1–3 queries and shrunk to the minimal `email_ok next pw_ok next back`.
- **"Max length 50 instead of 40":** found **only after the probe-derived boundary classes were added as learning inputs.**
- Control runs against an unchanged copy found nothing, across 3 × 600 random W-method queries, 15k random-walk steps and 1,974 exhaustive W-method queries.

**Noise calibration has to vary timing.**
- When calibration ran without random delays, masked toast *text* passed, yet toast *presence* still flickered and broke learning after 54 resets.
- Adding 0–900 ms timing jitter fixed it: 30 resets, 35 s.

**Data needs a cap.** TodoMVC learned 21 states with the item count capped at 2, and 45 states with a cap of 3. Unbounded data needs a counting or register abstraction.

**Cost extrapolation (about 50 states and 20 inputs):**

| Setup | Time |
|---|---|
| Fast local single-page app, sequential | about 35–40 min |
| Network-backed app, sequential | about 3–15 h |
| Network-backed app, 8 parallel browser contexts | about 0.5–2 h |

**Implication for the clean room:**
- Hashed output symbols only work when comparing an app against a modified copy of itself.
- A clone written from the spec words things differently, so its states will hash differently.
- So clean-room conformance needs **semantic output symbols named by the LLM**, or a comparison that treats renamed outputs as equal. The spike includes one: `compare.py`.

---

## 3. Architecture decisions (recommended)

### D1. One engine with four driver adapters, in a Python core

```
                ┌──────────────── teardown core (Python) ───────────────────┐
 driver adapters│ mapper svc → trace store/observation tree → learner orch. │
 ─────────────► │ refinement · noise calibrator · claim engine · spec compiler│
 web  (Playwright-py + CDP)        │ conformance runner · coverage/stop monitor  │
 cli  (pexpect/pipe + overlay/bwrap)└───────────────────────────────────────────┘
 desk (AX / UIA / AT-SPI + vision fallback)          │
 mobile (uiautomator2 / adb; WDA later)              ▼
                                      teardown-gate → teardown-clean MCP
```

**The driver contract:**
- `reset(hard|soft)`, `home()`, `step(action)` and `observe()`, each returning a raw evidence ID;
- plus capability metadata: reset cost, parallelism and snapshot support.

**Why Python:** AALpy (L#, KV, adaptive L#, hW, ONFSM, passive learners), Hypothesis, uiautomator2, pyobjc/pywinauto/pyatspi and Playwright-py are all Python. TypeScript is used only to export XState and fast-check suites.

### D2. A learning strategy chosen per platform

| Reset cost | Strategy |
|---|---|
| CLI, about 10 ms | Full active L#-ADS, plus TreeVada grammar inference |
| Web, 1–3 s with parallel contexts | Active L# **per feature** (n ≤ 60, k ≤ 20) |
| Mobile, 2–10 s | Hybrid: passive EDSM from exploration traces, active queries only on conflicts, soft "homing" resets |
| Desktop VM, 3–30 s | Same hybrid, plus decomposition by menu or feature |

Two rules apply on every platform:
- The observation-tree cache is persistent, so every trace answers future queries for free.
- The equivalence-testing budget is set explicitly.
- When the clone is re-learned, use Adaptive L# with the original's model as the reference (up to 100× fewer inputs).

### D3. Spec IR: a symbolic extended Mealy machine (EFSM) with claims attached

- **Structure:**
  - hierarchical states;
  - typed abstract inputs, each with a JSON Schema and named equivalence classes;
  - guards over input classes and **registers**;
  - outputs as multisets of abstract symbols, plus a nondeterminism tag;
  - claims written in EARS style, each carrying a Beta posterior, coverage, strictness (must-refuse vs may-extend), the reference build fingerprint, a layer (client/server) and an observation tier.
- **Exports:**
  - EARS text, XState v5 and decision tables, for human review;
  - Hypothesis or fast-check model-based suites, for conformance;
  - SCXML or Quint, optionally.
- **Precedent:** Quviq's model-as-spec conformance testing on Volvo's AUTOSAR stack found more than 200 issues across vendors.

### D4. One clean-room line for all platforms (`observation_tier` on every evidence record)

| Tier | Meaning | Examples | Allowed use |
|---|---|---|---|
| **A: behavior** | What the shipped artifact presents at its interfaces | Accessibility tree and visible UI; HTML constraint attributes and `validity`; routes; request/response *shapes*; exit codes and streams; output files and formats; user-visible prefs; deep links and intent filters as the OS reports them; system-level log events | May back a claim |
| **B: steering** | Grey-area data | DOM classes and test IDs, private file or plist layout, activity names, strace/eBPF path sets, JS/AFL coverage, app-tagged logcat | Guides exploration only; every claim must be re-established from tier A. Feeds the denylist. |
| **C: implementation** | How the program works inside | JS/CSS/WASM bodies, source maps, decompilation, heap snapshots, syscall sequences, `evaluate` against app globals | **Excluded at capture time** |

### D5. Things the tool refuses, enforced in code

- bypassing CAPTCHAs or bot walls;
- bypassing certificate pinning, root detection or attestation (Frida, objection, repackaging);
- bypassing FLAG_SECURE;
- flipping Electron fuses or re-signing an app to strip its hardened runtime;
- fake accounts;
- exceeding rate limits.

**Anything that cannot be observed becomes an explicit `unknown`.** Network observation has three tiers:
- **N0:** UI only.
- **N1 (default):** network metadata.
- **N2:** TLS interception through the device's trust store only, on devices you own.

### D6. Barrier, gate and audit: build it as three services

1. **`teardown-observe`** (dirty zone): all drivers, the evidence store and the claim engine.
2. **`teardown-gate`** (dirty zone), which runs:
   - a reference corpus of every observed string;
   - exact matching (suffix automaton) and near matching (winnowing, MinHash);
   - a distinctiveness score, so "OK" and "Cancel" pass;
   - a quote ledger requiring a `compat_reason` for every literal;
   - an automatic identifier denylist and codename map;
   - an advisory LLM judge;
   - human review;
   - a ticket router;
   - a **verdict abstractor**, which returns only symbols, closes the "guess the string" equality oracle, and enforces query budgets;
   - in-toto/DSSE signing.
3. **`teardown-clean`** (clean zone, MCP): `get_spec`, `ask_question` and `verify_against_original`. It has server-side authorization and its names and descriptions carry no reference to the real product.

**The clean runtime:**
- its own VM or rootless container, under a separate OS user;
- a fresh `CLAUDE_CONFIG_DIR`, so no CLAUDE.md or memory carries over;
- managed settings that deny WebSearch and WebFetch;
- a default-deny iptables egress allowlist: the model API, a package-registry mirror (with the target's packages blocked) and the gate;
- a fresh git repo with no remote;
- denylist linting on commits.

This closes the six leak channels found by bigsnarfdude/agent-clean-room and the WebFetch gap in clean-room-skill.

**The audit log:** a hash-chained JSONL of in-toto statements with five predicates: `observation-session`, `spec-release`, `clean-session`, `verdict` and `similarity-report`. Only checkpoints are anchored externally, via RFC 3161 or Rekor.

**Memorization probes**, run before and after implementation:
- identification ("name this product");
- completion of distinctive strings;
- structural ("likely module names");
- a cross-model check;
- **canaries planted in the spec**, to prove the clone was built from the spec.

The tool reports probe scores; it never claims the clone is "clean".

### D7. Three policy profiles

- **interop / bug-compatible:** exact public names, codes and bytes are allowed with a `compat_reason`; review is by sampling.
- **substitute (strict):** symbol-only verdicts, a human signs every release, memorization probes are mandatory, and trademark and trade dress are scrubbed.
- **own-legacy migration:** the gate is relaxed but the audit trail is kept. This profile requires a signed ownership declaration, and **relicensing code that has outside contributors does not qualify** (the chardet case).

---

## 4. Build order (recommendation)

Sizes are relative effort, not calendar time.

| Phase | Scope | Size | Exit criterion |
|---|---|---|---|
| **0. Core skeleton** | Evidence and claim schemas (content-addressed, REA-style), trace store, driver contract, EFSM IR, the 3-tier evidence model, gate v0 (exact matching and quote ledger), clean MCP v0 | M | Round-trip one claim from observe → gate → clean → verdict |
| **1. CLI** | Promote the spike to a driver: pipe and PTY modes, overlayfs/bwrap reset, `calibrate_noise`, the probe planner, L# for REPL modes, TreeVada | M | **jq + 5 coreutils**: the clean agent's clone run against the *hidden* jq and GNU tests. Also measure Teardown specs against README-only specs on **CLI-Tool-Bench** (94 repos; the published best is 43.8%) |
| **2. Web** | Playwright-py driver, state key, HAR freeze, three-way client/server layering, DB-snapshot reset, per-feature L# | L | **TodoMVC (32 hidden tests) → RealWorld (128 E2E + API suites)**, scored raw and selector-adapted |
| **3. Barrier productized** | Docker compose for the dirty, gate and clean zones; egress firewall; full sanitizer; in-toto log; memorization probes | M | A full audit dossier generated for the RealWorld run |
| **4. Android** | uiautomator2 driver, emulator snapshot ladder, N0/N1/N2 network tiers, intake detectors (attestation, FLAG_SECURE, apps with no tree) | L | **Loop Habit Tracker, Omni-Notes and AntennaPod** against their hidden Espresso suites |
| **5. Desktop** | AT-SPI on Linux (Docker + Xvfb) → AX on macOS (Tart VMs) → UIA on Windows (Hyper-V); menu inventory; `observe_effects`; vision fallback | XL | **GNOME app → Joplin → Windows Calculator** (its WinAppDriver suite) |
| **6. iOS** | iOS-on-Mac through the AX driver first; Simulator for open-source apps (Wikipedia, and Firefox's `FxScreenGraph` as ground truth for the state machine); real device plus WebDriverAgent last | L | Firefox iOS screen-graph recall |

**Why CLI first:**
- It is the cheapest platform to reset, which makes the learning research cheap.
- It has the strongest public oracles, plus a published human baseline (uutils took about 4 years to reach ~95% of GNU's tests).
- It has a ready-made comparison benchmark, CLI-Tool-Bench.
- The spike already works.
- **Web second** because most of the commercial value is there.

**The benchmark is the project's credibility story; nobody has published one like it.**
- Take open-source apps that ship external-interface test suites.
- Run Teardown black-box and have a clean agent implement the clone.
- Run the original project's own tests against the clone.
- Report:
  - spec recall (hidden tests passed);
  - claim precision;
  - probe cost;
  - leakage (similarity scores and memorization probes).
- Always pin the oracle version and publish the denominator, as the uutils and Deno/Bun lesson shows.

---

## 5. Biggest risks (ranked)

1. **Mapper validity is the real oracle.** A mapper that is wrong but consistent produces a confident, wrong spec. Nobody has measured LLM-mapper error on real UIs.
   - Mitigation: our own benchmark of apps with known statecharts plus seeded mutants (Firefox iOS `FxScreenGraph`, Loop Habit's acceptance steps); mapper consistency checks; refinement events triggered by nondeterminism.
2. **Silent model incompleteness.** The web spike learned 14 of the 19 true states under a modest equivalence budget, with no warning. The 5 missing states were hidden memory behind a 9-step sequence. Mitigations:
   - Spend budget on the oracle, not the learner.
   - Add LLM-proposed "round-trip" oracles of the form "change it, leave, come back".
   - Feed boundary classes found by field probes into the learning alphabet.
   - Report states versus budget as an `unknown`, never as "done".
3. **Equivalence cost on mobile and desktop.** Soft resets and hW learning on real GUIs with hidden server state are unproven.
   - Mitigation: decompose by feature, use passive learning first, and report m-completeness honestly ("1-complete under mapper v7").
4. **Legal and contract exposure on SaaS and commercial mobile apps.** A logged-in session is bound by the terms of service.
   - Mitigation: intake gates, the profiles, UI-only probing, and recommending self-hostable or licensed targets for the substitute profile.
5. **Contamination of the AI implementer.** Its weights may already contain the target (GEMA v. OpenAI).
   - Mitigation: probes, codenames and canaries reduce and document the risk; they cannot remove it.
6. **Hidden test suites are tied to the original's DOM or IDs.** Selector-adapted scoring is needed, and so is a "testability contract" in the spec (the clone must expose a11y roles and labels for every element the spec names).
7. **Platform tooling decay.** WinAppDriver is abandoned; Wayland blocks synthetic input; macOS asks for screen-recording permission again every month. All of these are solved by running targets in VMs or containers, never on the analyst's host.

---

## 6. Decisions you need to make

1. **Profile priority.** Should v1 ship interop + own-legacy only (lower risk), or the strict substitute profile too?
2. **Build order.** Do you accept CLI → web → barrier → Android → desktop → iOS, or should web come first for product reasons?
3. **v1 scope-outs:**
   - canvas and game-engine apps;
   - remote SaaS with bot protection;
   - pinned or attested commercial mobile apps (UI-only mode);
   - third-party iOS apps on real devices.

   Accept these?
4. **Human at the gate.** Is a human reviewer required for every spec release, or only in the substitute profile?
5. **Implementer models.** Same provider for the dirty and clean sides (with separate accounts), or a different provider for the clean side?
6. **Open-source or hosted.** A hosted clean room gives a stronger audit trail; open source spreads faster.

---

## 7. What to reuse

| Need | Reuse | Licence or notes |
|---|---|---|
| Automata learning | AALpy 1.6.2 (L#, KV, Adaptive L#, hW, ONFSM, RPNI/EDSM) | MIT |
| Optional JVM learning | LearnLib 19 (`learnlib-cli`, AAAR, procedural, TTT), RALib (SL^λ) | Apache-2.0 |
| Web driver | Playwright-py ≥1.64 + CDP | Apache-2.0 |
| Android driver | openatx/uiautomator2 | MIT |
| Desktop drivers | pyobjc / pywinauto / FlaUI / pyatspi; OmniParser v2 for vision | various |
| Grammar inference | TreeVada (deterministic) / Arvada | check licences |
| Combinatorial testing | PICT | MIT |
| Conformance suites | Hypothesis, fast-check, @xstate/graph, Schemathesis | MPL / MIT |
| API inference | mitmproxy2swagger, Optic | MIT |
| Similarity checks | datasketch, Dolos, JPlag, imagehash, PDQ | various |
| Audit | in-toto attestation, DSSE, rekor-tiles | Apache-2.0 |
| Design ideas | REA (evidence IDs, "unknown ≠ absent", obligation ledger, trace specs, effects flags); clean-room-skill (roles, hooks, `public_surface`) | MIT / check |
| Baselines | CLI-Tool-Bench, AndroidWorld, OSWorld and WindowsAgentArena harnesses | — |
