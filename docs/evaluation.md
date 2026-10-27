# How Teardown is evaluated

Teardown does not ship a universal benchmark. It ships a **method** you can repeat on your own targets, and the
results below come from applying it while building the tool. Each result is reported with what it measures and
what it does not.

## The method

1. **A hidden oracle the observer never sees.** This is the target's own test suite, or one written for a target
   by someone else. The observer may not read it, run it, or be told anything derived from it.
2. **A pinned denominator.** The oracle runs against the *original* under the same harness first. Tests the
   original fails, or tests that cannot apply, are excluded and listed. Scores are "clone passes / original
   passes".
3. **Separate agents for the two sides.**
   - The observer works only through Teardown's observe tools and the guide.
   - The implementer gets only the released kit and the gate's abstract verdicts.
4. **Arms that separate the spec's contribution from everything else:**
   - **spec**: kit only;
   - **docs**: the public manual only (an upper-bound baseline: it is not clean-room material);
   - **hybrid**: kit plus manual;
   - **memory**: no material at all, which measures what the model already knows about a famous target.
5. **Contamination is reported, not hidden.** Each implementer is asked whether it recognized the target. A famous
   target measures spec plus memory. A target the model cannot know measures the spec alone.
6. **No oracle leakage.**
   - Hidden-suite failures may guide changes to the tooling, never the observer's prompt or the spec of the same
     benchmark.
   - Results obtained after tuning against a suite are labeled **development set**.
   - A **held-out** result needs a target the tooling was not tuned on, with the tooling frozen before the run.

## Results

| target | how it was run | hidden suite | caveat |
|---|---|---|---|
| A novel command-line tool | spec only | 397/397 | a tile-layout language written for the benchmark; a clone built from the manual alone passed 395 |
| `jq` 1.7.1 | spec only | 394/429 (91.8%) | famous: the same model with no spec at all scored 397, so this measures spec plus memory |
| Novel web apps, held out (9 apps) | spec only, both sides confined | 53% → 99.2% across abstraction versions; **96.9–99.2% on the last three** | apps written for the benchmark; each round's misses were recorded in the next abstraction version, so the later rounds measure the improved tool |
| RealWorld "Conduit" frontend | spec plus its public selectors contract | 99/101 | development set: the tooling was tuned against this suite, and the implementer recognized the app |
| Novel Android apps (2 apps) | spec only, both sides confined | 113/118 (95.8%) and 100/119 (84.0%) | the second clone was built without any verification feedback (the emulator failed during the session) |
| Flipt v1.61.0, a real open-source web app | spec only, scored on its own Playwright suite | 17/55 (30.9%) with its announcement banner off, as in Flipt's CI (13/55 as built); the first round scored 9/55 | development set: the tooling was improved on the first round's misses. 21 of the 55 tests mock a read-only mode that the server leaves out of its responses, so observation never reached it (2 of those 21 pass, 15 of the other 34). The implementer's session ended at its 2-hour limit after four verify calls. Tests that reach elements by CSS or test id cannot be expected to match |

What these numbers support:

- **CLI:** on a tool the model cannot know, a Teardown spec alone was enough for a complete reimplementation.
- **Web, on apps written for the benchmark:** with the current abstraction (`web.aria`, which records every
  difference a user-facing Playwright locator or assertion can see), clones pass 96.9–99.2% of hidden suites. The
  remaining misses are states the observer did not exercise, not structure the spec failed to record.
- **Web, on a real application:** the method does not yet carry over to an application of Flipt's size. A
  second round with the improved tooling (time budgets, server-mode faults, faster verification) nearly
  doubled the score, to 31%. What remains is mostly sections the observer did not reach in its time (rule and
  rollout editing), a server mode that never appears in a response, and implementation time.
- **Strict gate:** in the strict rounds a person approved each release at their own terminal with two or three
  class-level decisions, and the audit log recorded each one.
- **Enforced isolation costs nothing in outcome:** releases reimplemented inside the clean-room container scored
  the same as with a prompt-only barrier.
- **Not yet measured:** desktop against a hidden suite.

## Repeating it on your own target

1. Pick a target with a test suite you can run but will not show the observer, and pin the original's score
   under your harness.
2. Run the observer ([observer playbook](observer-playbook.md)) and release in strict mode
   ([strict gate](strict-gate.md)).
3. Export the kit and run the implementer in the enforced clean room ([clean runtime](clean-runtime.md)).
4. Score the clone on the hidden suite, and report the score with its caveats.
