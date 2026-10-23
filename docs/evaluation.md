# How Teardown is evaluated

Teardown does not ship a universal benchmark. It ships a **method** you can repeat on your own targets, plus the
results of the rounds run while building it. Read the results with their caveats: each one says what it measures
and what it does not.

## The method

1. **A hidden oracle the observer never sees.** This is the target's own test suite: `jq`'s `tests/jq.test`,
   RealWorld's Playwright E2E suite, or a private JSONL suite written for a novel tool. The observer may not read
   it, run it, or be told anything derived from it.
2. **A pinned denominator.**
   - Run the oracle against the *original* under the same harness first.
   - Tests the original fails, or tests that cannot apply (e.g. ones that intercept a public demo host), are
     excluded and listed.
   - Scores are "clone passes / original passes".
3. **Separate agents for the two sides.**
   - The observer works only through Teardown's observe tools and the guide.
   - The implementer gets only the released kit (spec, plus any *public* document such as a markup contract)
     and the gate's abstract verdicts.
   - Prompts are fixed per series. When they change, the change is recorded.
4. **Arms that separate the spec's contribution from everything else:**
   - **spec**: kit only;
   - **docs**: the public manual only (an upper-bound baseline: it is not clean-room material);
   - **hybrid**: kit plus manual, the realistic deployment;
   - **memory**: no material at all, which measures what the model already knows about a famous target.
5. **Contamination is reported, not hidden.** Each implementer is asked whether it recognized the target and how
   that influenced it. A famous target (`jq`, RealWorld Conduit) measures spec plus memory. A target the model
   cannot know (a private, novel tool) measures the spec alone.
6. **No oracle leakage.**
   - Hidden-suite failures may guide *tooling* changes, but never the observer prompt or the spec for the same
     benchmark.
   - Results obtained after tuning tooling against a suite's failures are labeled **development-set**.
   - A **held-out** result needs a target the tooling was not tuned on.
7. **Everything is recorded:**
   - the kit and spec release ids;
   - verify calls used;
   - conformance counts (Teardown's own suite against the original);
   - hidden-suite counts, and per-test differences between rounds.

## Results so far

| target | kind | arm | hidden suite | conformance | caveat |
|---|---|---|---|---|---|
| `jq` 1.7.1 | CLI, famous | spec | 394/429 (91.8%) | 1714 / 0 / 11 | memory alone scored 397/429: measures spec + memory (`research/09`) |
| novel tool, round 1 | CLI, private | spec / docs | 337/398 (84.7%) / 386/398 (97.0%) | 470/470 | examples-only spec (`research/10`) |
| novel tool, round 2 | CLI, private | spec / hybrid / docs | 397/397 / 397/397 / 395/397 | 1144 / 0 / 1 | after rules + coverage; different tool than round 1 (`research/11`) |
| RealWorld Conduit, rounds 1–4 | web, famous | spec + public selectors contract | 80 → 93 → 95 → 99 of 101 | 342 → 576 passing | development-set: tooling tuned between rounds; implementer recognized the app (`research/12`) |
| Kilnroll (novel web app), **held out** | web, private | spec only, both sides confined, tooling frozen | 64/120 (53%) | 224 / 0 / 0 | misses were behaviors `web.aria/v1` did not record (tables, flash messages, focus, titles); fixed in `v2` afterwards (`research/15`) |
| Kilnshare (novel web app), **held out** | web, private | spec only, both sides confined, tooling frozen (`web.aria/v2`) | 73/131 (56%) | 197 / 0 / 0 | no misses in what v2 added; 54 were table structure, fixed in `v3` afterwards (`research/16`) |
| Lockline (novel web app), **held out** | web, private | spec only, both sides confined, tooling frozen (`web.aria/v3`), neutral brief | 106/130 (81.5%) | 116 / 0 / 1 | thinnest spec (38/153 coverage); misses split between unvisited pages and lossy regions/inline text (`research/17`) |
| Scionry (novel web app), **held out** | web, private | spec only, both sides confined, tooling frozen (`web.aria/v4`, coverage-gated release), neutral brief | 121/130 (93.1%) | 201 / 0 / 1 | 77/79 coverage; misses: CSS-generated icon text (5), unprobed data states (4) (`research/18`) |
| Wickward (novel web app), **held out** | web, private | spec only, both sides confined, tooling frozen (`web.aria/v5`, data-state coverage), neutral brief | 114/127 (89.8%) | 313 / 0 / 2 | 108/111 coverage; misses: alertdialog role (7), accessible descriptions (2), 4 behaviors (`research/19`) |
| Fogline (novel web app), **held out** | web, private | spec only, both sides confined, tooling frozen (`web.aria/v6`), neutral brief | 112/128 (87.5%) | 201 / 0 / 0 | one verify call; misses: row headers (7), `aria-invalid` (4), named groups (2), 3 observer gaps, 2 of them hidden by a fault-coverage bug, since fixed (`research/20`) |
| Strewnfield (novel web app), **held out** | web, private | spec only, both sides confined, **strict gate** (a person approved at a terminal), tooling frozen (`web.aria/v8`), neutral brief | 129/130 (99.2%) | 332 / 0 / 1 | one verify call; 102/105 coverage; one miss, an empty list's message the observer never produced (`research/21`) |
| Belfry (novel web app), **held out** | web, private | as Strewnfield: strict gate, `web.aria/v8`, both sides confined | 126/130 (96.9%) | 237 / 0 / 18 | 98/99 coverage; four misses, all states or routes the observer never exercised (`research/22`) |
| Wickwright (novel Android app) | Android, private | spec only, both sides confined | 113/118 (95.8%) | 163 / 0 / 0 | first and only round; implementer did not recognize the app (`research/14`) |
| Conduit (round-4 release) and the round-2 novel tool, in the enforced clean room | web / CLI | as above | 99/101 · 397/397 | 570 / 0 / 6 · 1144 / 0 / 1 | implementer inside the isolated container; same outcomes as with a prompt-only barrier (`research/13`) |

What these numbers support:

- **CLI:** on a tool the model cannot know, a Teardown spec alone was enough for a complete reimplementation
  (round 2). Round 1 showed examples alone are not enough; observer-stated rules and coverage closed that gap.
- **Web:**
  - On Conduit (development set), the tooling grew to capture what a real app's E2E suite checks: routing,
    error handling under faults, empty structure named by a public contract, environment-dependent layout.
  - **On eight held-out apps it scored 53% (v1), 56% (v2), 81.5% (v3), 93.1% (v4), 89.8% (v5), 87.5% (v6),
    99.2% and 96.9% (v8).** Each clone reproduced its spec. Each round found the next layer of user-visible structure the abstraction lacked:
    - titles, focus and messages;
    - then tables and description lists;
    - then regions and inline text;
    - then CSS-generated text;
    - then dialog roles and accessible descriptions;
    - then row headers, `aria-invalid` and named groups.

    `v8` stopped following the suites. It records everything a user-facing Playwright locator or assertion can
    tell apart (an audit of 39 page pairs, plus 7 that must stay identical). On both `v8` apps every miss was
    a state or route the observer never exercised, not structure the spec failed to record.
- **Strict gate:** in the seventh round a person approved at their own terminal. It took three class-level
  decisions and a release, because the observer rewrote its own prose findings. The audit log recorded each
  decision.

    Coverage-gated release took the observer from 38/153 covered items to 77/79.
- **Enforced isolation costs nothing in outcome:** the same releases reimplemented inside the clean-room
  container scored the same as with a prompt-only barrier.
- **Android:** a spec released by a confined observer through MCP alone rebuilt a novel three-screen app to 95.8%
  of its hidden tests. The rest were orderings and messages the observer did not probe.
- **Not yet measured:** desktop against a hidden suite.

## Repeating it on your own target

- Pick a target with a test suite you can run but will not show the observer.
- Pin the original's score under your harness.
- Run the observer (`docs/observer-guide.md`) and release in strict mode (`docs/strict-gate.md`).
- Export the kit and run the implementer in the enforced clean room (`docs/clean-runtime.md`).
- Score the clone on the hidden suite and report it with the caveats above.
- `bench/` holds the harnesses used here (`bench-jq`, `bench-jsonl`, `bench/conduit/e2e.py`).
