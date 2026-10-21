# Teardown: design decisions (v1)

*Decided 2026-10-19. The evidence behind these decisions is in `DECISION-REPORT.md`, `research/` and `spikes/`. This file records **what we are building**; the roadmap is in `ROADMAP.md`.*

## Product

**What it does.** Teardown is an open-source MCP toolkit for **clean-room, behavior-first analysis** of web, CLI, mobile and desktop apps. In one loop, it:
1. observes an app as a black box;
2. turns what it sees into falsifiable behavior claims;
3. compiles those claims into a sanitized spec;
4. lets a separate "clean" agent build a clone from that spec;
5. differential-tests the clone against the original.

### Decisions

| # | Decision | What it means in practice |
|---|---|---|
| 1 | **One profile, with user-declared purpose and opt-in strict mode** | See "Policy model" below. |
| 2 | **Human gate review only in strict mode** | Standard mode: automated gate checks plus an advisory LLM judge, and items are flagged rather than blocked. Strict mode: a human signs every spec release. |
| 3 | **Clean-side model: recommended, not enforced** | Docs and the intake wizard recommend a different provider and account for the clean implementer. The audit log records which model each role used. |
| 4 | **Open source** | Core license: **Apache-2.0**. It includes a patent grant and matches the main dependencies (Playwright and LearnLib are Apache, AALpy and uiautomator2 are MIT). If you would rather block hosted competitors, use FSL-1.1-Apache-2.0, which converts to Apache-2.0 after 2 years. **Confirm before the first commit.** |
| 5 | **Build order: CLI → web → barrier → Android → desktop (Linux → macOS → Windows) → iOS** | CLI is the cheapest to reset, has the strongest test oracles, and a spike already works for it. Web is where most of the value is. See `ROADMAP.md`. |
| 6 | **v1 scope-outs** | Listed under "v1 scope". Each one has a rough backlog task in `ROADMAP.md`. |

## Policy model

There is **one** policy profile. Users may analyze for any purpose, including building a substitute product, and **the user is responsible for the legal judgment.** Teardown records the user's choices and shows warnings; it does not adjudicate.

### Intake

- **Recorded at intake:**
  - declared purpose: `interop | substitute | own-legacy | research`;
  - jurisdiction;
  - a snapshot of the ToS or EULA;
  - the account used;
  - a target fingerprint.
- **The declared purpose only changes defaults and warnings.**
  - A **patent and trademark/trade-dress warning** is shown for every purpose except `own-legacy`.
  - `own-legacy` asks for an ownership declaration, with a note that code with outside contributors does not count as your own legacy (the chardet case).

### Always on, any mode

- **Hard refusals.** These are not configurable, because they are about circumvention and integrity, not policy preference:
  - bypassing CAPTCHAs or bot walls;
  - bypassing certificate pinning, root detection or attestation (no Frida, objection or repackaging);
  - bypassing FLAG_SECURE;
  - flipping Electron fuses, or re-signing apps to strip the hardened runtime;
  - fake accounts;
  - exceeding the configured rate limits.
  - Anything Teardown cannot observe becomes an `unknown`.
- **The three-tier evidence model.** Tier C (code bodies, decompilation) is never captured.
- **Gate checks.** Every gate check runs every time:
  - exact and near-verbatim match against the observed strings;
  - distinctiveness score;
  - quote ledger with a `compat_reason`;
  - identifier denylist;
  - codename map.

  In standard mode their findings are **warnings**.
- **The audit log** (hash-chained in-toto statements).

### Strict mode (opt-in)

- Gate findings **block** release until recorded approvals cover all of them: functional classes
  (expected outputs, interface names) can be approved as a class; prose only one finding at a time. Coverage gaps
  need an acknowledgement. Approvals are made at a terminal (`teardown approve`), never through the observer's MCP
  tools. See `docs/strict-gate.md`.
- Verdicts return symbols only.
- Memorization probes and canaries are mandatory.
- Trademark and trade-dress scrubbing is enforced.

## Architecture

The design follows `DECISION-REPORT.md` §3.

### Python core plus four driver adapters

```
teardown/
  core/        evidence + claim schemas (content-addressed), trace store / observation tree,
               mapper service, learner orchestrator (AALpy), refinement, noise calibrator,
               claim engine, spec compiler (EFSM IR), conformance runner, coverage monitor
  drivers/     cli/ web/ android/ desktop/{atspi,ax,uia}/ ios/      (driver contract below)
  gate/        corpus, matchers, quote ledger, denylist/codename, LLM judge, verdict abstractor, signer
  mcp/         observe server, clean server
  audit/       in-toto predicates, hash-chained log, checkpoints
  bench/       hidden-oracle harnesses (jq, coreutils, TodoMVC, RealWorld, …)
```

### Driver contract

- **Methods:** `reset(hard|soft)`, `home()`, `step(action) -> evidence_id`, `observe() -> evidence_id`.
- **Capability metadata:** reset cost, parallelism, snapshot support, and observation tiers.

### Spec IR

- **Structure:** a symbolic extended Mealy machine:
  - hierarchical states;
  - typed inputs with JSON-Schema equivalence classes;
  - guards over input classes and registers;
  - outputs as multisets of semantic symbols, with a nondeterminism tag.
- **Claims attached to the IR:**
  - EARS-style text;
  - a Beta posterior plus coverage cap;
  - strictness (`must-refuse` or `may-extend`);
  - reference build fingerprint;
  - `layer` and `observation_tier`.
- **Exports:**
  - EARS text;
  - XState v5;
  - decision tables;
  - Hypothesis or fast-check suites.

### Learning

- **Never L\*.**
  - **CLI and web:** KV or L#.
  - **Mobile and desktop:** passive EDSM, then active conflict resolution.
  - **When re-learning the clone:** Adaptive L#.
- **Equivalence oracle:**
  - Its budget is explicit.
  - It includes LLM-proposed "round-trip" probes aimed at hidden memory.
  - States learned versus budget is always reported as an `unknown`.
- **Field-probe boundary classes are fed back into the learning alphabet.**

### Comparison

- Comparisons are made at the **behavior level, never on message text**:
  - exit code and error class;
  - output bytes or abstract symbols;
  - side effects.
- **Noise calibration** is Diffy-style and three-way, with timing jitter.
- **Conformance** uses semantic output symbols, or comparison up to output renaming.

### Services

- **`teardown-observe`** (dirty side).
- **`teardown-gate`** (dirty side).
- **`teardown-clean`** (clean side, MCP).
  - Ships with a Docker Compose setup for the clean runtime: its own OS user, egress allowlist, fresh `CLAUDE_CONFIG_DIR`, web tools denied, and a registry mirror.
  - Separating models is recommended, not enforced.

## v1 scope

### In scope

- **CLI:**
  - pipe and PTY modes;
  - TUIs at the screen-abstraction level;
  - daemon lifecycle, after which the daemon is handed to the web/API driver.
- **Web:** self-hostable apps, plus SaaS in **limited-reset mode** (UI-only, no active learning on flows that change data, low-confidence claims).
- **Android:**
  - open-source and sideloaded apps on a native arm64 emulator;
  - commercial apps in UI-only mode at network levels N0/N1, with weak trees and attestation failures recorded as unknowns.
- **Desktop:** Linux (AT-SPI + Xvfb) and macOS (AX, in Tart VMs). Electron apps go through the web driver.

### Out of v1 (rough backlog tasks are in ROADMAP.md)

- Canvas, WebGL and game-engine apps, where the a11y tree is empty and a vision-only observer is needed.
- Windows desktop (UIA, Hyper-V, vision fallback).
- iOS. Phase 6 comes after v1: iOS apps running on Mac first, then the Simulator for open-source apps, then real devices.
- SaaS behind bot protection. The challenge detector ends the session; there is nothing more to build.
- Realtime collaboration as a first-class target (multi-context lockstep).
- Register-automata learning (RALib) and LearnLib sidecars.
- A hosted clean-room service.
