# Teardown — research notes: a clean-room, behavior-first analysis MCP

*Prepared 2026-10-18. Sources: a read of `morluto/rea` (cloned at `refs/rea`), a survey of academic and industrial prior art, and the legal and process background of clean-room design. Nothing here is legal advice.*

---

## 0. TL;DR

- **The thesis holds, with one correction.**
  - REA is not purely implementation-centric. It already has behavioral capture: `capture_browser_scenario`, `capture_process_scenario`, `compare_*_captures`, `verify_reconstruction`, and the obligation ledger.
  - What it lacks are the four things that make behavior the *primary product*:
    1. **Systematic probing.** The agent hand-writes every scenario. Nothing generates boundary, negative or sequence probes.
    2. **A behavioral spec model.** There is no first-class notion of input domain, default, refusal taxonomy or UI state machine.
    3. **An information barrier.** Decompiled code, recovered JS, strings and runtime traces all go to the same agent, in the same bundle. REA's docs say clean-room separation must be done with OS accounts or containers, outside the MCP (`refs/rea/docs/installation.md:177`).
    4. **Behavioral verification beyond processes.** `verify_reconstruction` behavioral claims cover only process captures (terminal, exit, filesystem), not browser or UI flows.
- **The niche is real and mostly empty.** Every neighbouring tool covers only part of it.
  - Cloners (open-lovable, screenshot-to-code, website-cloner skills) copy *appearance*.
  - QA-agent MCPs (Octomind, QA.tech, Meticulous) verify *intent you already have*.
  - Automata-learning tools (LearnLib, AALpy) learn rigorous state machines but need a hand-built "mapper".
  - `clean-room-skill` (npm, v0.8.0) enforces a dirty/clean split, but works from *source*.
  - No one combines black-box exploration, falsifiable behavior claims, a sanitized spec, executable conformance tests and differential testing of the clone.
- **The key insight:** the LLM is the missing **mapper and hypothesis generator** that classical black-box techniques always lacked. Classical tools supply the rigour; the LLM supplies the abstraction.
  - Classical tools: L\* / AALpy, GLADE / Arvada, PICT, Daikon-style falsification, Diffy-style differential testing.
  - LLM: picks the action alphabet, abstracts observations into states, names equivalence classes, and writes human-readable claims.
- **Legal footing is better for behavior-first than for decompilation, especially in the EU.**
  - EU Software Directive Art. 5(3) grants the right to "observe, study or test the functioning" of a program, and Art. 8 voids contract terms that override it. *SAS v. WPL* (CJEU 2012) applied this to running the program to learn its behavior.
  - In the US, EULAs can still bind (*Bowers*, *Blizzard v. bnetd*).
  - A clean room never protects against patents, trademarks or trade dress.
- **Recommended MVP:** web apps first (Playwright), written in Python (so it can use AALpy, Hypothesis and Arvada directly), and shipped as **two physically separate MCP servers** — observer/dirty and implementer/clean — with a sanitizing gate between them.

---

## 1. What REA gives you, and where it stops

### Worth borrowing (concepts, not code)

| REA idea | Where | Why it matters here |
|---|---|---|
| Content-addressed Evidence (`ev_<sha256>`) | `src/domain/evidence.ts` | Fields: `confidence` (observed/derived/inferred), `authority`, `environment`, `limitations`, `evidence_links`. Every spec claim can cite evidence that can't be tampered with. |
| **"Missing coverage is unknown, not absence"** | `docs/mcp-contracts.md` | The single most important epistemic rule for a black-box spec. |
| Obligation ledger | `docs/reconstruction-obligation-ledgers.md` | Case kinds `positive / negative / malformed / cancellation / teardown`; statuses `unowned → characterized → implemented → verified`; authority ranking. This is almost a behavior-requirement model already. |
| Process trace specification | `src/domain/process/processTraceSpecification.ts` | `partial_order` / `finite_traces` assertions are the honest way to specify nondeterministic event ordering. |
| Declarative scenarios with stable `step_id`s | `docs/browser-scenario-contract.md` | Step alignment makes original-vs-clone diffs possible. Artifacts not requested are recorded as `not_requested`, never as "empty". |
| Residual unknowns | `src/domain/residualUnknown.ts` | Hash-chained revisions; resolution only by evidence (`withdrawn` / `out-of-scope` are explicitly not truth claims). Good for open spec questions. |
| `authority-independence` proof | `src/domain/reconstructionCoverage.ts` | Proves the clone doesn't secretly call the original. |
| Typed effects per tool | `src/contracts/toolEffects.ts` | Flags such as `mutatesTarget`, `accessesNetwork` and `changesUiState` drive MCP annotations. They are also needed for safe probing. |
| `_meta.provenance.untrusted_content` | `src/server/toolResult.ts` | Prompt-injection hygiene. Still required, but it is **not** an information-flow control. |

### Lessons from its shape

- **About 208 tools is too many.**
  - REA manages the size with schema profiles, summary/paging and a routing skill.
  - A behavior-first MCP should aim for **15–25 tools per server**, organised by task shape: observe, probe, claim, verify.
  - REA's own `docs/tool-design.md` warns against inventing orchestration languages. Keep the probe planners as internal algorithms, not a DSL the agent must learn.
- **Contamination paths you must design out.**
  - REA puts decompiled pseudocode, recovered JS sources (`recover_javascript_sources`, `export_web_scripts`), strings, IPC channel names and runtime captures into **one** session and **one** exportable bundle.
  - Raw PTY data, full DOM, accessibility text and response bodies are kept verbatim. These are behavioral, but may carry copyrighted prose.

---

## 2. Legal and process foundations

*Not legal advice. The goal here is to show which constraints the tool should enforce.*

### Free to describe vs. protected expression

| Generally free to specify | Risky or protected |
|---|---|
| Functionality, validation rules, edge-case outcomes, default *values*, state machines, refusal conditions (Baker v. Selden; 17 USC §102(b); SAS v. WPL) | Verbatim prose: help text, tutorials, manuals, long or distinctive messages (SAS v. WPL — WPL infringed by copying manual text) |
| Menu/command hierarchy as a "method of operation" (*Lotus v. Borland*, 1st Cir.; Supreme Court split 4–4) | Wholesale copy of a large, arbitrary taxonomy outside the 1st Circuit (Whelan / Altai SSO risk) |
| Short labels, error codes, command names (37 CFR 202.1; *Mitel*) | Icons, images, sounds, screenshots, pixel-exact layout and visual design (*Tetris v. Xio*; trade dress) |
| Public API names, kept for compatibility (*Google v. Oracle*, fair use; *Oracle v. Rimini* 2024) | Internal/private identifiers, code structure, pseudocode |
| File and protocol formats (SAS v. WPL) | Anything learned under NDA, from leaks or from ex-employees (trade secret) |

### Statutes that set the posture

- **EU 2009/24/EC Art. 5(3)** allows observing, studying and testing while running the program, and **Art. 8** says a contract can't override that. This is the strongest legal basis for black-box observation.
- **Art. 6** (decompilation) is limited to interoperability. That is one more reason to keep static analysis *out* of the product.
- **US:** DMCA §1201 applies only if you circumvent a TPM, and plain observation circumvents nothing. EULA reverse-engineering bans are often enforced.
- **Web targets:**
  - The CFAA is narrowed by *Van Buren*.
  - ToS still binds logged-in use (*hiQ* lost on breach of contract).
  - Never bypass authentication, rate limits or blocks, and never use fake accounts.
- **Trade secrets:** reverse engineering a lawfully acquired product is explicitly not "improper means" (DTSA §1839(6)(B); EU 2016/943 Art. 3).
- **Patents, trademarks and trade dress are not addressed by a clean room.** Flag this in the product.

### Process precedent

- **Classic pattern:** dirty team → spec → lawyer/reviewer gate → clean team. Questions go back as written queries through the same gate. Everything is logged as it happens.
  - Used by Phoenix BIOS and Compaq.
  - Accepted as evidence in *NEC v. Intel* 1989 and *CA v. Altai* 1992.
- **What a clean room actually buys you:** *evidence of independent creation*. It is not immunity. The audit log is the product.
- **Wine / ReactOS / Samba / nouveau:** black-box conformance tests and protocol traces. Samba and nouveau are the closest existing examples of "behavior-first".

### The AI wrinkle (2025–2026)

- **chardet 7.0 relicensing (Mar 2026).** It was done with Claude Code. Willison found the agent had consulted the old source, and stylistic rewriting can defeat JPlag-style similarity checks.
- **Malus "Clean Room as a Service".** A satirical but working spec-agent / impl-agent split.
- **H. Peter Anvin on LKML.** Argued a clean team must be "certified to have never seen the code".
- **GEMA v. OpenAI (Munich, Nov 2025).** Memorised material in model weights counted as reproduction.
- **Thaler / US Copyright Office.** Purely AI-generated output may not be copyrightable.
- **Implication:** an LLM implementer is never provably "clean". It may have been trained on the target. The tool should *reduce and document* that risk: codename the target, strip identifying strings, probe for memorisation, and run a post-hoc similarity check. It must not claim to eliminate the risk.

---

## 3. Technical prior art (condensed)

| Problem | Best existing technique / tool | How to use it |
|---|---|---|
| Drive the app | Playwright MCP (accessibility-tree refs), Chrome DevTools MCP, mobile-mcp, Appium MCP, macOS AX MCPs, computer-use as fallback | Use them as **actuators**. Wrap or embed them rather than reimplementing. |
| Explore cheaply | LLM-Explorer (MobiCom '25): the LLM keeps knowledge, cheap logic picks actions, ~148× cheaper. Crawljax/DroidBot state graphs; APE adaptive state abstraction | The LLM keeps a **feature inventory**; a crawler enumerates the elements you can act on. |
| Feature inference | AutoE2E (ICSE '25), WebTestPilot (2026, symbolic pre/postconditions per step) | The closest academic work to "a spec from a running app". |
| UI sequencing → state machine | Angluin L\*, TTT; **AALpy** (Python, Mealy / ONFSM / stochastic); LearnLib (Java); protocol state fuzzing (de Ruiter & Poll, TLS) | The LLM is the **mapper**: abstract action ↔ concrete calls, and observation → output symbol. Reset = a fresh context or DB snapshot. |
| Accepted input formats | GLADE, **Arvada / TreeVada** (black-box grammar inference from accept/reject) | Oracle = "did a validation error appear, or did the request go out?" |
| Edge cases across fields | Boundary-value analysis, equivalence partitioning, **PICT** / NIST ACTS (pairwise / t-way) | The LLM proposes the classes; PICT plans a minimal set of probes. |
| Invariants and ordering | Daikon-style template falsification, Texada / Synoptic (LTL / FSM from logs) | **The LLM proposes, the tool falsifies.** |
| API behavior | mitmproxy2swagger (HAR → OpenAPI), Schemathesis | Recover the backend contract from observed traffic. |
| Executable spec | **fast-check / Hypothesis stateful model-based testing**, XState + `@xstate/graph` path generation, JSON Schema, decision tables | The model *is* the spec; failures shrink to minimal counterexamples. |
| Equivalence check | **Diffy** three-way noise calibration (original A vs original B vs clone), metamorphic relations, Meticulous-style visual diffs | Diff *abstracted observations*, not pixels. |

---

## 4. Proposed design

### 4.1 Roles and the barrier: two MCP servers

```
 ┌──────────────── DIRTY ZONE (has target access) ─────────────────┐        ┌──────── CLEAN ZONE ────────┐
 │                                                                 │        │                             │
 │  Observer agent ──► teardown-observe MCP ──► Playwright/AX/ADB ──┼─► target│  Implementer agent          │
 │        │              (explore, probe, claim, falsify)           │        │        │                    │
 │        ▼                                                         │        │        ▼                    │
 │   Evidence store ──► Claim ledger ──► Spec compiler ──► GATE ────┼──────► │  teardown-clean MCP         │
 │   (raw, never leaves)                     (sanitize + review)    │  spec  │  (get_spec, ask, verify)    │
 │        ▲                                                         │ bundle │        │                    │
 │        └──── conformance runner ◄──── abstract verdicts ◄────────┼────────┼── clone build              │
 └─────────────────────────────────────────────────────────────────┘        └─────────────────────────────┘
```

- **Enforce the barrier with the OS, not with prompts.**
  - The two servers run under different OS users or containers, with different filesystem roots.
  - The clean side has no network route to the target and no access to the evidence store.
  - REA reached the same conclusion; your MCP should *ship* this setup (Docker compose / devcontainers) rather than only document it.
- **The clean side can still ask the oracle.**
  - Through the gate, `verify_against_original(clone_endpoint, suite)` runs the conformance suite against both apps on the dirty side.
  - It returns **abstract verdicts only**: claim ID, pass/fail, and a minimised sequence of abstract steps. No raw DOM, screenshots or response bodies.
  - This replaces the slow "written query to the dirty team" loop of classic clean rooms, and keeps the wall intact.
- **Clarification tickets.** `ask_question` from the clean side becomes a ticket. The observer answers it with new probes, and the answer becomes new claims that pass through the gate again.

### 4.2 Core data model: the falsifiable Behavior Claim

```yaml
claim_id: clm_<hash>            # content-addressed, like REA evidence
feature: checkout.coupon
kind: input-domain | default | transition | refusal | output-invariant | ordering | side-effect | timing
statement: >                     # EARS-style, implementation-agnostic
  When the user submits a coupon code longer than 20 characters,
  the system shall reject it with a field-level validation error and shall not send a network request.
formal:                          # optional machine-checkable form
  json_schema: { type: string, maxLength: 20, pattern: "^[A-Z0-9-]+$" }
  # or statechart fragment / decision-table row / LTL template
case_kinds: [negative, malformed]
status: hypothesized | corroborated | falsified | contested | out-of-scope
confidence: { probes: 14, confirming: 14, contradicting: 0, nondeterminism: none|partial-order|stochastic }
origin: observed | inferred-intent   # separates "does" from "probably means to"; bugs show up as observed-only
evidence: [ev_…]                 # dirty-side only; stripped by the gate
expression_risk: none | label | prose | visual   # filled in by the sanitizer
compat_reason: null              # required if the claim keeps a verbatim public name
```

- **Lifecycle:** `hypothesize → probe → corroborate/falsify → sanitize → hand off → verify on clone`.
- **Unknowns** (borrowed from REA) are first-class. "We never reached the admin role" is an explicit unknown, not silence.

### 4.3 Pipeline

1. **Intake.**
   - Record target identity (URL + build fingerprint / app bundle hash), licence or ToS snapshot, account, jurisdiction, purpose (interop vs substitute), and the probe budget and rate limits.
   - Refuse anything that needs circumventing protection.
2. **Explore.**
   - Crawl the accessibility tree, and have the LLM build a feature inventory (AutoE2E-style).
   - Record traces: action, normalised accessibility-tree hash, URL, network shape, storage diff, console.
3. **Abstract.**
   - State equivalence = a normalised, masked accessibility-tree hash, refined adaptively (APE).
   - The LLM names the states.
4. **Hypothesize.** The LLM writes candidate claims for each feature, along with the equivalence classes of each input.
5. **Probe.** Each probe confirms or falsifies a claim, and keeps its evidence link.
   - *Fields:* boundary values, PICT pairwise across fields, and Arvada for free-text formats.
   - *Flows:* AALpy L\*/KV with the LLM as mapper, under a query budget. Use stochastic or ONFSM learners where behavior varies.
   - *Defaults:* fresh-state snapshots across N resets.
   - *Refusals:* a taxonomy of field validation, permission, rate limit, server error and silent no-op.
6. **Calibrate noise.** Run every probe twice against the original, Diffy-style. Fields that differ between runs become masks, and claims become `partial-order` or stochastic where needed.
7. **Compile the spec.** From the claim ledger, produce:
   - EARS statements;
   - an XState/SCXML statechart;
   - JSON Schema / OpenAPI;
   - decision tables;
   - a list of unknowns.
8. **Gate (sanitize and review).**
   - n-gram match against every string captured from the target, with a quote budget and a `compat_reason` required for any quote.
   - Identifier denylist and perceptual-hash check of any images.
   - No screenshots cross the gate. Replace the target's name with a codename.
   - Human (or separate-LLM) sign-off, recorded in a hash-chained log.
9. **Generate conformance tests.**
   - fast-check/Hypothesis model-based suites whose model is the statechart.
   - Gherkin examples, plus Schemathesis for the API.
   - All tests go through an adapter interface so they run against `{original, clone}`.
10. **Differential verification.**
    - Run the same command sequences in lockstep on both apps and diff the abstracted observations.
    - Shrink each failure to a minimal counterexample and return it as an abstract verdict.
    - Optionally re-learn the clone's automaton and check it for equivalence with the original's.
11. **Similarity audit (dirty side).** After the clone is built, compare its strings and assets with the original's and record the result. Low similarity is necessary, but it is not proof.

### 4.4 Tool surface sketch (keep it small)

**`teardown-observe`** (dirty side, about 15 tools)

| Group | Tools |
|---|---|
| Session | `open_target(intake)`, `reset_target(strategy)`, `target_status` |
| Observe | `snapshot` (abstracted state + raw evidence id), `act(abstract_action)`, `explore(budget, goal)` |
| Probe | `probe_field(locator, classes?)`, `probe_combinations(fields, strength=2)`, `learn_flow(alphabet, budget)`, `probe_defaults(n_resets)` |
| Claims | `propose_claim`, `falsify_claim(claim_id, budget)`, `record_unknown`, `list_claims(feature?, status?)` |
| Spec | `compile_spec(feature)`, `submit_to_gate(spec_id)` |
| Verify | `run_conformance(target=original\|clone)`, `diff_runs` |

**`teardown-clean`** (clean side, about 5 tools)

- `get_spec(feature?)`
- `list_unknowns`
- `ask_question(text)`
- `verify_against_original(clone_endpoint, suite?)`, which returns abstract verdicts only
- `get_conformance_suite`

### 4.5 Coverage metrics without code

- Feature-inventory coverage.
- State and transition coverage of the learned automaton.
- Equivalence-class coverage per input.
- Case-kind coverage per claim (positive / negative / malformed / cancellation / teardown).
- API endpoint × status coverage.
- Optional grey-box signal: JS coverage via CDP on the dirty side, used *only* to steer exploration toward unvisited code. It must never feed the content of spec claims.

---

## 5. Hard problems and recommended stances

| Problem | Stance |
|---|---|
| **Reset and isolation.** L\* needs a reliable `reset()`. | Web: a fresh browser context plus a seeded account. Ideally use a self-hostable target or a DB snapshot (WebArena-style). Treat live shared SaaS as "probe-budget-limited, no destructive probes", using REA-style effect flags. |
| **Nondeterminism.** | Diffy noise calibration, masks, partial-order and stochastic claims. Confidence is a count of probes, never a boolean. |
| **Oracle problem.** Bugs get copied. | Tag each claim `observed` or `inferred-intent`. A human decides whether a quirk is part of the spec ("bug-compatible" mode for interop). |
| **Abstraction choice.** Too fine and the state space explodes; too coarse and distinct states merge. | Start coarse (role + route + modal + form-validity), split on a counterexample (APE). Let the agent ask for refinement. |
| **Hidden server logic, rare paths, time-based features.** | Keep them as explicit unknowns with recommended probes. Never infer absence from not observing something. |
| **Auth, MFA, CAPTCHA, rate limits.** | A human does the auth once, and session state is seeded. Respect rate limits and never bypass blocks (legal and ethical line). |
| **Spec as infringing paraphrase.** | Abstraction rules in the schema; the gate rejects prose-heavy claims. Describe *what* happens, never *how*. |
| **LLM implementer memorisation.** | Codename, stripped identifiers, a memorisation probe ("what product is this?"), a post-hoc similarity audit, disclosure. |
| **Cost.** | LLM-Explorer split: cheap deterministic crawler and probe planners, with the LLM called only for abstraction and hypotheses. |

---

## 6. MVP recommendation

1. **Scope.**
   - Web applications only, driven by Playwright.
   - Desktop (AX), mobile (ADB/Appium) and CLI follow later. For CLI, REA's process-capture design is a good template.
2. **Language: Python.**
   - It has the MCP Python SDK, Playwright for Python, AALpy, Hypothesis stateful testing, and Python implementations of Arvada/TreeVada; PICT can be called as a binary.
   - TypeScript is fine if you prefer fast-check and XState, but you'd have to reimplement automata learning.
3. **Milestone 1 — one form, end to end.**
   - `probe_field` / `probe_combinations` → claims → spec (JSON Schema + EARS) → gate → clean agent builds the form → `verify_against_original`.
4. **Milestone 2 — flows.** `learn_flow` with AALpy, statechart output, and model-based conformance tests.
5. **Milestone 3 — the barrier as a product.** Two containers, a hash-chained audit log, sanitizer with n-gram, identifier and pHash checks, and an exportable "clean-room dossier".
6. **Evaluation (do this early; it's the credibility story).**
   - Take open-source web apps that have their own E2E suites, such as RealWorld/Conduit, TodoMVC variants, Excalidraw features and WebArena's self-hosted apps.
   - Run Teardown black-box, let a clean agent implement, then **run the original project's own E2E tests against the clone**.
   - Report:
     - spec recall (hidden tests passed);
     - claim precision (falsified claims);
     - probe cost;
     - leakage, measured as the n-gram overlap of the clone with the original source.
   - Nobody has published this benchmark. It could be the project's headline.

---

## 7. Open questions for you

1. **Use case:** interoperability (bug-compatible), competitive substitute, or internal legacy-migration? This decides how strict the gate is and whether verbatim public names are allowed.
2. **Target types after web:** desktop, mobile or CLI?
3. **Who sits at the gate:** a human reviewer, a separate LLM, or both?
4. **Shipping model:** open-source tool, or a hosted "clean room" with a stronger audit trail?

---

## References (selected)

- **REA:** https://github.com/morluto/rea (local: `refs/rea`)
- **clean-room-skill** (source-based dirty/clean split, prior art for the barrier): https://github.com/whit3rabbit/clean-room-skill
- **Automata learning:**
  - AALpy https://github.com/DES-Lab/AALpy
  - LearnLib https://learnlib.de
  - Vaandrager, "Model Learning", CACM 2017 https://cacm.acm.org/research/model-learning
- **GUI and feature inference:**
  - LLM-Explorer https://arxiv.org/abs/2505.10593
  - AutoE2E https://arxiv.org/abs/2408.01894
  - WebTestPilot https://arxiv.org/abs/2602.11724
  - DroidAgent https://github.com/coinse/droidagent
- **Grammar inference:**
  - Arvada https://arxiv.org/abs/2108.13340
  - TreeVada https://arxiv.org/abs/2308.06163
  - GLADE https://arxiv.org/abs/1608.01723
- **Combinatorial testing:** PICT https://github.com/microsoft/pict
- **Specification mining:** Texada https://www.cs.ubc.ca/~bestchai/papers/ase15-texada-tool-demo.pdf
- **Property-based and model-based testing:**
  - Hypothesis stateful https://hypothesis.readthedocs.io/en/latest/stateful.html
  - fast-check model-based https://fast-check.dev/docs/advanced/model-based-testing/
  - Schemathesis https://github.com/schemathesis/schemathesis
- **Differential testing:** Diffy https://blog.x.com/engineering/en_us/a/2015/diffy-testing-services-without-writing-tests
- **Traffic to API spec:** mitmproxy2swagger https://github.com/alufers/mitmproxy2swagger
- **Actuators:**
  - Playwright MCP https://github.com/microsoft/playwright-mcp
  - Chrome DevTools MCP https://github.com/ChromeDevTools/chrome-devtools-mcp
  - mobile-mcp https://github.com/mobile-next/mobile-mcp
- **UI-to-code:**
  - Interaction2Code https://arxiv.org/abs/2411.03292 (models are weak at behavior compared with layout)
  - Design2Code https://github.com/NoviScl/Design2Code
- **Legal:**
  - EU 2009/24/EC https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32009L0024
  - SAS v WPL https://www.ippt.eu/sites/ippt/files/2012/IPPT20120502_ECJ_SAS_Institute_v_WPL.pdf
  - Google v Oracle https://www.supremecourt.gov/opinions/20pdf/18-956_d18f.pdf
  - Lotus v Borland https://en.wikipedia.org/wiki/Lotus_Development_Corp._v._Borland_International,_Inc.
  - Oracle v Rimini (2024) https://www.eff.org/deeplinks/2024/12/ninth-circuit-gets-it-interoperability-isnt-automatic-first-step-liability
  - Wine clean-room guidelines https://wiki.winehq.org/Clean_Room_Guidelines
- **AI clean-room debate:**
  - LWN https://lwn.net/Articles/1061534/
  - Simon Willison https://simonwillison.net/2026/Mar/5/chardet
  - Heather Meeker https://heathermeeker.com/2026/04/09/the-chardet-controversy-open-source-and-the-ai-clean-room/
  - GEMA v OpenAI https://www.medialaws.eu/gema-v-openai-decision-of-the-munich-regional-court/
