# Teardown core engine: research report

*Checked against primary papers, repo trees and registries; **(unverified)** marks claims that weren't. Collected 2026-10-19.*

## 1. Query cost of active learning

**Asymptotic cost.** n = states, k = inputs, m = counterexample length.

| Algorithm | Membership queries |
|---|---|
| L\* | O(k·m·n²) |
| L\* with Rivest-Schapire counterexample handling, KV, TTT, L# | ~O(k·n² + n·log m) |

All of them need at most n equivalence queries; in practice about 0.5n.

**Measured cost.** From the L# appendix (arXiv 2107.05419, TACAS'22), with LearnLib baselines.

| Model | n / k | Learning resets (L#-ADS / TTT) | Learning symbols | Testing resets | Testing symbols |
|---|---|---|---|---|---|
| model1 | 35 / 15 | 795 / 1,681 | 6.8k / 9.9k | ~700 | ~11k |
| TCP_Linux_Server | 57 / 12 | 2,515 / 3,760 | 27.7k / 35.2k | ~41k | ~790k |
| OpenSSH | 31 / 22 | 1,665 / 2,488 | 10.8k / 14.4k | 86k–119k | 1.5M–2.1M |

- **Learning cost is k·n to 4·k·n resets.** L#-ADS was fastest on every model; L\* with Rivest-Schapire was the worst.
- **Equivalence testing is more than 90% of the total cost.** Kruger et al. (arXiv 2406.19714) note a 31-state, 22-input machine "may need several million inputs".
- Two ways to cut that cost:
  - bandit-chosen test suites (arXiv 2401.12703);
  - **Adaptive L# with a reference model**, which needs up to 100× fewer inputs (arXiv 2406.19714). This fits re-learning the clone with the original as reference.

**Wall-clock extrapolation.** About 10 symbols per query and a bounded equivalence budget. Per-action costs: CLI 20 ms, web 300 ms, mobile 1 s, desktop 1 s.

| Size | Resets / symbols | CLI (50 ms reset) | Web (2 s reset) | Mobile (15 s reset) | Desktop VM (30 s reset) |
|---|---|---|---|---|---|
| S: n=20, k=10 | ~2k / 15k | ~7 min | ~2.4 h (18 min with 8 parallel) | ~12 h | ~21 h |
| M: n=60, k=20 | ~12k / 120k | ~50 min | ~17 h (~2 h with 8 parallel) | ~83 h | ~130 h |
| L: n=200, k=50 | ~100k / 1M | ~7 h | ~140 h | weeks | infeasible |

**What this means per platform.**

- **CLI:** full active learning works.
- **Web:** active learning works **per feature** (n ≤ 60, k ≤ 20) with parallel contexts.
- **Mobile and desktop:** use a **hybrid**.
  - Learn passively (EDSM, k-tails) from exploration traces.
  - Use active queries only for targeted conflicts.
  - Prefer soft resets (homing to a fingerprinted home state) and hW reset-free learning.
  - Decompose by feature.
- **Everywhere:** keep a persistent observation-tree cache, so every trace gives free query answers, and set an explicit equivalence budget.

## 2. Libraries

**AALpy** (v1.6.2, Aug 2026, MIT, Python ≥3.10) — **primary engine**. It has almost everything:

- **Active learning:** L\*, KV, **L#** (ADS) and **Adaptive L#**.
- **Reset-free learning:** **hW**.
- **Nondeterministic and stochastic:** L\*_ONFSM, abstracted ONFSM, non-deterministic Moore, L\*_MDP, L\*_SMM.
- **Pushdown:** KV_VPA.
- **Passive learning:** RPNI, EDSM and k-tails (GSM), Alergia and IOAlergia, PAPNI.
- **Equivalence oracles:** W, Wp, random walk/word, state-prefix, k-way state/transition coverage, PAC, cache-based, BBC, provided sequences.

**LearnLib** (19.0.0, Aug 2026; now has `learnlib-cli`) — optional JVM backend for:

- TTT, L#, ADT, L-lambda, DHC, NL\*;
- **AAAR** (alphabet abstraction refinement);
- procedural systems (SPA/SBA/SPMM, for decomposing by feature);
- Mealy machines with timers, RPNI, OSTIA, parallel oracles.

**Other learners:**

- **flexfringe:** passive EDSM over logs, for probabilistic automata.
- **DAALder** (arXiv 2406.07208): a research prototype mixing passive and active learning.

**Register automata** (for data parameters):

- **RALib** has SL\* and SL^λ, which uses up to 10× fewer queries (arXiv 2401.14324).
  - **Practical only for small systems** (a few registers, equality or ≤ comparisons) **(unverified at UI scale)**.
- **Tomte** appears unmaintained.
- **Pragmatic path:** use Tomte's *idea*.
  - The LLM-designed mapper turns data relations into abstract symbols, e.g. `login(pw=REGISTERED|FRESH|PREV)`.
  - Learn a finite Mealy machine over those symbols.
  - The spec compiler lifts the result back to an EFSM with registers.

**Learning without reset:**

- **hW-inference** (Groz, Simão, Petrenko, Oriat; ICTSS'15, JSS'20, EFSM extension 2023) uses homing plus characterizing sets. It is reported to scale to hundreds of states, and AALpy ships it.
- **No "L# without reset" paper exists.** Related work:
  - L# for Mealy machines with timers (arXiv 2403.02019);
  - stochastic-delay learning (arXiv 2508.16384), which matters for UI latency.

## 3. Abstraction refinement and the LLM as mapper

**Prior art:**

- **AAR** (Howar, Steffen and Merten, VMCAI'11): nondeterminism under the current abstraction triggers a split of a symbol, using the concrete representatives that diverged. LearnLib calls this `aaar`.
- **Tomte:** CEGAR-style refinement of the mapper.
- **APE** (ICSE'19): a decision-tree GUI abstraction refined when one action has non-uniform effects.
- **Krumrey, Margaria and Steffen** (LNCS 16470, 2026): an LLM extracts the web-UI alphabet, a human edits it, and the LLM writes the symbol implementations. It uses source code, but the workflow transfers.
- **ALEX** (LearnLib): an older Selenium harness for Mealy learning.

**Design: classify observation-tree conflicts.** A conflict means the same abstract word produced different outputs. The L# observation tree doubles as the persistent cache.

1. **Noise.** Replay N times, plus a Diffy-style second original instance. Varying fields become a mask or a nondeterministic transition.
2. **Input abstraction too coarse.** The LLM sees both concrete traces and their diff and proposes a split predicate, e.g. `coupon(len>20)` vs `coupon(valid)` (AAR).
3. **Output abstraction too coarse, or hidden state.** The LLM proposes a new observable to add to the fingerprint (APE) or a register (Tomte).
4. **Too fine.** Symbols or states that are never apart get merged, shrinking k.

**Each refinement creates a new mapper version.** Cached concrete traces are re-abstracted at no cost.

## 4. LLM plus automata learning (2023–2026)

- **pMAT** (arXiv 2408.02999): an LLM teacher with persistent errors, discrimination and verification prompts, TTT, and refinement of the query cache.
- **CAPAL** (ICLR'26): learning under persistent noise.
- **L\*LM** (PMLR v288, 2025): the LLM answers membership queries from natural language.
- **ChatAFL** (NDSS'24): the LLM extracts grammars and breaks plateaus. **+47.6% transitions and +29.6% states vs AFLNet.**
- **ProtocolGPT** (arXiv 2405.00393): white-box (reads code), so not usable here.
- **ATLAS** (arXiv 2608.14352, Aug 2026, Tappler et al.): fully LLM-driven trace abstraction plus probabilistic automata learning. **The closest "LLM as mapper" precedent.**
- **GraphDroid** (arXiv 2609.10031): tiered GUI state equivalence, pHash/SSIM first and a multimodal LLM only when ambiguous **(details unverified)**.
- **PSMBench** (NeurIPS'25 Datasets & Benchmarks): 9 LLMs extracting protocol state machines from RFCs reached **≤0.82 F1 on states but ≤0.38 F1 on transitions.**
  - **LLMs are good at naming and proposing, poor at asserting transition structure. Structure must come from the learner.**

**Making the LLM mapper robust:**

1. **The LLM writes the mapper as code**: deterministic normalizer and classifier functions, versioned and unit-tested against the cached corpus.
2. **Memoize by content hash.** When a per-observation LLM call is unavoidable, use temperature 0, a closed vocabulary and a 3–5-way majority vote. Ties go to refinement.
3. **Consistency checks.** Re-abstract a held-out sample. If agreement is low, freeze learning and send the mapper for review.
4. **LLM-proposed models are priors only.** Use them as the Adaptive L# reference or as seeds for tests.

## 5. Nondeterminism

- **ONFSM learning** uses "all-weather" sampling. **Expect a 5–20× query multiplier.**
- **Stochastic Mealy learning** needs thousands of samples per state. That is realistic only for CLIs or offline bulk traces.

**Stance for UI targets:**

- (a) Diffy-style three-way calibration: fields that vary between two runs of the original become masks.
- (b) Outputs are multisets of abstract events. Order is kept only where it is consistently observed.
- (c) Residual nondeterminism is kept as set-valued outputs, with probabilities only when frequency is itself a claim (e.g. retry/backoff).

**Precedent:** QuickCheck's Dropbox model (Hughes, Pierce, Arts and Norell, ICST'16) tests nondeterministic behavior without seeing the system's internal choices.

## 6. Spec representation and test generation

**Options checked:**

- **XState 5.33 + @xstate/graph 3.0.4.**
  - Functions: `getShortestPaths`, `getSimplePaths`, `getAdjacencyMap`, `getPathsFromEvents`, `createTestModel` (merged from @xstate/test).
  - Events can be state-dependent, and `serializeState` can include context.
  - Good for review (Stately visualizer) and for TypeScript.
- **SCXML:** portable, but its tooling is mostly dead. Export only.
- **Hypothesis `RuleBasedStateMachine`:** Bundles work like registers. Fits Python drivers.
- **fast-check 4.x:** `fc.commands`, `asyncModelRun`, and a race scheduler.
- **Quviq QuickCheck state machines — the precedent for "the model is the spec":**
  - Volvo/AUTOSAR: 3,000+ pages of spec turned into models found **200+ issues** across vendors (Arts and Hughes, ICSTW'15).
  - Dropbox.
  - quickcheck-state-machine adds parallel linearizability checks.
- **P / PObserve:** heavyweight for UI.
- **Quint `run --mbt`:** produces ITF traces, and quint-connect replays them against an implementation.
- **TLA+ trace validation** (arXiv 2404.16075): **the model for a trace-acceptance oracle.**

**Recommendation: a neutral JSON IR, a symbolic extended Mealy machine (EFSM).**

- **States:** hierarchical (feature → state), named by the LLM.
- **Inputs:** abstract actions with typed parameters, each a JSON Schema with named equivalence classes.
- **Guards:** predicates over parameter classes and typed **registers**. Complex guards become decision tables.
- **Updates:** register assignments.
- **Outputs:** multisets of abstract observation symbols, plus order constraints and a nondeterminism tag (none, set, partial-order, stochastic).
- **Claims:** attached to states, transitions and invariants, as EARS text plus a formal fragment.
- **Provenance:** learner, mapper version, test counts.

**Why this IR:**

- It is exactly what a Mealy learner plus Tomte-style abstraction lifts into, so it is learnable.
- It compiles to XState, EARS and decision tables, so a person can review it.
- Data is covered by registers, schemas and guards.
- A small reference interpreter in Python and TypeScript runs it in two modes:
  - **generate:** paths, or Hypothesis/fast-check commands, with values drawn from the schema classes;
  - **trace-acceptance:** does the model admit this observed trace?

**Exports:** XState, SCXML, Quint (optional) and Hypothesis/fast-check suites. Do not make P or TLA+ canonical.

## 7. Claims, invariants and confidence

**Mining and falsifying claims:**

- **Deterministic falsifier (Daikon-style).** Templates cover:
  - unary bounds, enums and nullability;
  - request-to-response field relations;
  - pre/post deltas;
  - set membership.
  - Daikon's justification test rejects invariants that could hold by chance (p > 0.01).
- **Ordering claims:** Texada LTLf templates (response `G(a→F b)`, precedence, absence), mined from abstract traces.
- **LLM role:** proposes semantic claims. The falsifier designs probes to break them.
- **ClassInvGen** (arXiv 2502.18917) co-generates invariants and test inputs, prunes failures and checks completeness with mutants. It beat both Daikon and pure-LLM generation.

**Confidence:**

- Each claim gets a Beta(1+s, 1+f) posterior, where s = probes that confirmed it and f = probes that contradicted it. The ledger stores P(violation rate < ε).
- With no failures, the **rule of three** gives a 95% upper bound of about 3/n, so 100 clean probes means at most 3%.
- **Probes aren't independent, so confidence is capped by coverage.** A claim can't be confident until every relevant input class × reachable enabling state has at least one probe.
- **Mutation discrimination:** a claim must reject plausible variants of itself (±1, a dropped guard), otherwise it is too weak.

**Choosing the next probe:**

1. **Disagreement first:** the distinguishing sequence that best separates rival hypotheses (query-by-committee or apartness).
2. **Uncertainty:** the widest posterior times the risk.
3. **Cost-aware:** expected information gain divided by (reset cost + steps), preferring probes that extend a cached prefix.
4. **Bandit over probe generators,** as in Kruger et al.

## 8. Coverage and when to stop

- **Formal guarantee.** A W/Wp/H/ADS suite that is **m-complete** proves equivalence if the target *under the current abstraction* has at most n+Δ states.
  - Suite size is about n·k^(Δ+1)·|W|. Affordable for Δ=0–1 on small to medium web and CLI targets; not on mobile or desktop.
  - Report it honestly, e.g. "1-complete under mapper v7".
- **Stop exploring a feature when all of these hold:**
  - (a) The hypothesis survives a budgeted k-way transition-coverage sweep (Δ=1 where affordable).
  - (b) **Discovery saturation:** by a Good-Turing / STADS estimate (Böhme, TOSEM'18), P(next trace finds a new state) ≈ f₁/N is below 1%.
  - (c) Every inventory feature, every input class × state, and every claim case-kind has at least one probe.
  - (d) No refinements in the last B queries.
- **Anything left uncovered becomes an explicit `unknown`** with a recommended probe.

## Recommended core architecture

**Languages:**

- Python core: AALpy, Hypothesis, LLM SDK, ledger.
- TypeScript: web adapter, XState export, fast-check.
- Optional JVM sidecars: LearnLib CLI and RALib.

**Components:**

1. **Driver adapter**
   - `reset(hard|soft)`, `home()`, `step(concrete_action)`, `observe()`, each returning a raw evidence id.
   - Capability metadata: reset cost, parallelism, snapshot support.
2. **Mapper service**
   - LLM-authored, deterministic, versioned code with a memo cache.
   - `abstract_input`, `concretize` (draws from a class or register relation), `abstract_output` (masked multiset).
3. **Trace store and observation tree**
   - Every trace is stored once and re-abstracted when the mapper is upgraded. It serves as the cache for all learners.
4. **Learner orchestrator**, choosing per feature:

   | Situation | Strategy |
   |---|---|
   | Cheap reset | L#-ADS |
   | Expensive reset | passive GSM/EDSM, then active conflict resolution |
   | No reset | hW |
   | Clone re-learning | Adaptive L# with the original as reference |
   | Nondeterminism | ONFSM |

   Budgets are explicit and workers run in parallel.
5. **Refinement engine**
   - Classifies conflicts, asks the LLM to split or merge, re-validates, and bumps the mapper version.
6. **Noise calibrator**
   - Three-way runs; outputs masks and nondeterminism tags.
7. **Claim engine**
   - Daikon/Texada templates plus LLM proposals, falsified by probes.
   - Beta posteriors with coverage caps.
   - Probe planner ranks by information gain per unit cost.
8. **Spec compiler**
   - Mealy machine plus data abstraction → EFSM IR, then EARS, XState v5, SCXML and optional Quint.
9. **Conformance runner**
   - @xstate/graph paths and Hypothesis/fast-check commands.
   - Trace-acceptance oracle.
   - Lockstep runs, shrinking, and abstract verdicts only.
10. **Coverage and stopping monitor**
    - m-complete level, STADS estimate, class×state coverage, refinement quiescence.

**Data model**, all content-addressed:

- `Trace`
- `MapperVersion`
- `AbstractTrace`
- `Hypothesis` (EFSM IR, learner, budget)
- `Claim` (with posterior and coverage)
- `RefinementEvent`
- `Unknown`

## Open research risks

1. **Validity of the abstraction is the real oracle.** A wrong but consistent mapper produces a confident wrong spec. No published work measures LLM-mapper error on real UIs, so **we need our own benchmark: apps with known statecharts plus seeded mutants.**
2. **Equivalence-testing cost on mobile and desktop.** It is unproven that homing soft-resets and hW work on real GUIs with hidden server state.
3. **Data and hidden server state.** Register learners don't scale to UI-sized data. Time- and quota-dependent behavior is still open.
4. **Telling noise from a too-coarse abstraction.** The refinement classifier can loop, so it needs budgets and human escalation.
5. **LLMs are poor at structure** (PSMBench transition F1 ≤ 0.38). Never let LLM-asserted transitions bypass the learner.
6. **Probes are not independent**, so Beta posteriors overstate confidence without honest coverage caps.
7. **Leakage through the mapper.** Mapper code and symbol names come from observing the target, so the gate must sanitize them too.
8. **Maturity.** AALpy's Adaptive L# and hW, and RALib's SL^λ, are research-grade. Plan to fork and fix them.
