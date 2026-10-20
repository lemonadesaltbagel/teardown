# Spike: web learning loop (Playwright + AALpy)

*Code: `spikes/web-learning/` (uv venv: Python 3.12, playwright 1.64, aalpy 1.6.2). All targets were served from localhost. The TodoMVC run was stopped early, so its results are partial. Run 2026-10-19.*

**Verdict:** the loop works end to end. Driver → masked accessibility-tree abstraction → AALpy learning → field probing → differential testing all ran, and both injected differences were found and shrunk to minimal abstract counterexamples. **The main weakness is the equivalence oracle.** With a modest budget it *silently* returns an incomplete model (14 of 19 states).

## Setup

### Targets

- **`signup_a.html`:** a 3-step wizard.
  - Email is trimmed, required, must contain `@`, and is at most 40 characters.
  - Password needs at least 8 characters and a digit, with a live strength meter.
  - Submit is disabled until the terms box is ticked.
  - A success page and a "Start over" link.
  - Values persist across Back/Next.
- **`signup_b.html`:** the same wizard with two differences.
  - Email max length is 50.
  - Back from step 3 clears the password.
- **`?noise=1` flag:** adds a random "N people signed up" counter and timestamped toasts that disappear after 200–800 ms.
- **`todo.html`:** a mini TodoMVC.

### Driver and mapper

- The driver uses role/name locators only.
  - An absent control returns `NA`; a disabled one returns `DISABLED`. Neither costs a snapshot.
- The output symbol is `<heading-slug>.<sha1[:6]>`, computed over the normalized aria snapshot:
  - `/url` lines dropped;
  - textbox values replaced with `<filled>`;
  - configurable masks applied.
- The abstraction is cached.

### Ground truth (experimenter-side only)

Breadth-first search plus minimization over the simulator gives **19 states for A and 22 for B**.

## Learning target A (9 inputs, 19 true states)

| Learner + equivalence oracle | States | Resets | Steps | Wall time |
|---|---|---|---|---|
| L* + random W-method 10×8 | 14 ✗ | 1,371 | 8,289 | 203 s |
| L* + random W-method 25×12 | 14 ✗ | 1,577 | 11,449 | 280 s |
| KV + random W-method 25×12 | 14 ✗ | 519 | 5,108 | 114 s |
| L# + random W-method 25×12 | 14 ✗ | 508 | 4,843 | 111 s |
| KV + random walk, 5,000 steps | 9 ✗ | 482 | 5,481 | 90 s |
| KV + k-way transition coverage (k=2) | 15 ✗ | 583 | 12,653 | 164 s |
| KV + state-prefix 50×15 | 17 ✗ | 1,119 | 19,467 | 317 s |
| **KV + random W-method 100×20** | **19 ✓** | 2,184 | 37,622 | 655 s |
| **L# + random W-method 100×20** | **19 ✓** | 2,193 | 35,517 | 644 s |

- **The two 19-state models are isomorphic to the ground truth.** The 14 output symbols map 1:1, so the abstraction neither merged nor split states.
- **The 5 missing states are hidden memory.** The terms checkbox stays ticked after Back, Back, Next, Next. The counterexample is 9 steps long, and random walks rarely reach that deep.
- **The equivalence oracle took 88% of the time** (577 of 655 s for KV).
  - KV and L# used about 6× fewer learning queries than L* (326 vs 1,255).
- **Simulator replay over 5 seeds:**
  - With random W-method 100×20, KV reached 19 states in 4 of 5 seeds and L# in 2 of 5.
  - With 25×12, every learner reached 19 in 0 of 5 seeds.
- **Per-operation cost** (measured under parallel load, so somewhat inflated):

  | Operation | Cost |
  |---|---|
  | Reset, new browser context | 37–53 ms |
  | Reset, `goto` only | 7 ms |
  | Snapshot | ~2 ms |
  | Action | 13–17 ms (the dominant cost) |
  | Playwright `click()` with its actionability waits | 33.6 ms |
  | `click(force=True)` | 2.0 ms |
  | "Stable" settle mode | ~31 ms per snapshot |

- **Fast mode** (forced actions plus our own enabled/present checks) learned the identical model at 7.9 ms per action instead of 13.3.
- **Lazy reset saved almost nothing**: 2,184 real resets for 2,226 logical queries.
- **Replaying access prefixes is 42% of all steps** (15,762 of 37,310).

## Field probing (email)

- **Cost:** 25 probes in 3.4 s.
  - 15 equivalence-class probes.
  - 8 boundary-search probes, exponential then binary.
  - 2 confirmations.
- **Rule derived:** required after trimming, contains `@`, at most 40 characters after trimming. There are three distinct error classes.
- **Permissive behaviors found.** All of these are accepted:
  - `@` alone, `@example.com`, a double `@`;
  - inner spaces, emoji;
  - SQL-like and HTML-like input;
  - Unicode.
- **On target B:**
  - Re-deriving gives a max of 50 (25 probes).
  - Replaying A's suite (25 probes, 3.4 s) flagged exactly the 4 lengths between 41 and 64.
- **Caveat:** the error text "at most 40 characters" itself states the rule. The gate must handle message text.

## Differential testing against B

### diff_base (model learned with the base alphabet)

- **"Back clears password" found by random W-method in 1–3 queries** (6–38 steps, under 1 s) on all 3 seeds.
  - Random walk found it on 2 of 3 seeds (7–9 queries) and missed it on seed 1 (484 queries).
  - Exhaustive W-method (bound = 19) found it after 445 queries (117 s).
- **Every counterexample shrank to `email_ok next pw_ok next back`** (10 shrink queries). A three-way check against A classified it as a **behavior difference**, not a gap in the model.
- **No false positives.** Control runs against A found nothing:
  - random W-method: 3 × 475 queries;
  - random walk: 3 × 5,000 steps;
  - exhaustive W-method: 1,974 queries (417 s).
- **The max-length difference was not detectable.** The base alphabet has no long-email input.

### diff_refined (probe-derived inputs `email_at_max` and `email_over_max` added)

- The learned model has 24 states. This matches a hand derivation; it was not audited by machine.
- **Both differences were found:**
  - Back difference: random W-method, 1–3 queries.
  - Length difference: random walk, 11–18 queries.
  - Exhaustive W-method found `email_over_max next` after 81 queries (10 s).
- Controls against A were clean: 0 counterexamples over 3 × 600 random W-method queries, 3 × 5,000 random-walk steps and 1,974 exhaustive W-method queries.
- **Each oracle stops at its first counterexample.** The real tool must keep searching, for example by learning the diff model.

### Learning B and comparing models

- B was learned at 22 states in 1,069 s, matching the ground truth.
- Comparing the two models up to output renaming gives the same counterexample.

## Noise (`?noise=1`, KV + random W-method 100×20)

| Abstraction | Result |
|---|---|
| Raw | Nondeterminism after 10 resets (1.5 s); the counter changes |
| Drop toast regions only | Same failure, after 1.5 s |
| Regex masks + drop toasts | 19 states, isomorphic to the clean model, 920 s |
| Calibrated, no timing jitter | **Nondeterminism after 54 resets.** Toast *text* was masked, but whether a toast is *present* depends on timing |
| **Calibrated with 0–900 ms jitter** (30 resets, 35 s) | Catches both the volatile counter and the flaky toast presence. 19 states, isomorphic |

**Lesson: calibration must vary timing.** Otherwise timing noise passes calibration and only shows up mid-learning.

## TodoMVC (partial)

- With the mapper limited in how many items it may add:
  - **cap 2:** 21 states (1,308 resets, 342 s);
  - **cap 3:** 45 states (2,712 resets, 597 s).
- Runs without a cap were killed.
- **The state count grows with the data bound.** Unbounded data needs a deliberate cap in the mapper or a counting/register abstraction.

## Cost extrapolation (~50 states, 20 inputs)

- **Learning, perfect oracle** (random 50×20 Mealy machines):
  - KV / L#: about 2.2–2.5k resets and 8.4–9.2k steps.
  - L*: about 20k resets and 72k steps. **Drop L\*.**
  - At 50 ms per reset and 15 ms per step, learning takes about 4 minutes.
- **Equivalence oracle**, at the budget that actually worked here (100 walks × ~25 steps per state):
  - About 5k resets and 125k steps.
  - **About 35–40 minutes sequential** on a fast local single-page app.
- **Real network-backed apps** (100–500 ms per step):
  - Roughly 3–15 hours sequential.
  - Roughly 0.5–2 hours with 8 parallel browser contexts.
- **These figures are optimistic.** Random machines are easy for random oracles: 25×12 always succeeded on them, but never on the real wizard.

## Lessons

1. **Spend budget on the oracle, not the learner.**
   - Use KV or L#.
   - Add oracles aimed at hidden memory, e.g. LLM-proposed round-trips ("change it, leave, come back").
   - **Report state count vs. budget as an unknown, never as "done".**
2. **Field probes feed the learning alphabet.** Boundary classes become abstract inputs; that is the only way the max-length difference got into the model.
3. **Calibrate noise Diffy-style with timing jitter.** Drop regions whose presence is flaky; mask volatile text.
4. **Hashed output symbols only work for regression checks** (A vs. a modified A). **A clean-room clone with different wording needs semantic output symbols named by the LLM**, or comparison up to output renaming (`teardown_spike/compare.py`).
5. **Use fast actions.** Force-click after checking presence and enabled state yourself, and use a cheap reset. The next big win would be checkpoint/restore of app state, because prefix replay is 42% of steps.
6. **Mask secrets in the abstraction.** The aria snapshot exposes password values.
7. **Keep the three-way check** (original / model / target). It cleanly separated real differences from gaps in the model.

## Files

- **Library, `teardown_spike/`:**
  - `abstraction.py`
  - `driver.py`
  - `sul.py` (prefix cache with lazy reset)
  - `signup_mapper.py`, `todo_mapper.py`
  - `learn.py`, `probe.py`, `calibrate.py`, `compare.py`, `sim.py`
- **Scripts:** `run_learn.py`, `run_probe.py`, `run_diff.py`, `run_noise.py`, `run_sim.py`, `run_todo.py`, `bench.py`, `summarize_runs.py`
- **Results, `results/`:**
  - `learn_*.{json,dot,states.txt}`
  - `probe_email.json`
  - `diff_base.json`, `diff_refined.json`
  - `noise_*`
  - `sim_costs.json`, `sim_truth_{A,B}.dot`
  - `todo_cap{2,3}.*`
  - `bench.json`
- **Logs:** `logs/`
