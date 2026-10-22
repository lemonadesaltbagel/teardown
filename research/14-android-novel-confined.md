# Experiment: Android, a novel app, both sides confined

*2026-10-22. App and hidden suite: `.teardown/novel-android/inventor/`. Project `.teardown/obs-android1`, kit
`.teardown/cleanroom/and-r1` (codename ember-orchid).*

## Setup

- **Target.** Wickwright, a candle-batch planner written for this benchmark by a separate inventor agent.
  - 581 lines of Java, with the UI built in code.
  - Three screens:
    - a planner with four validated inputs, refusal messages in a fixed order, derived values and a warning;
    - a pour queue capped at 5, with duplicate detection;
    - settings with Save/Defaults/Cancel.
  - No model can know it.
- **Hidden oracle.** 118 scenarios run by `bench/android/harness.py` (adb + `uiautomator dump`), which is
  independent of Teardown's Android driver. The original scores 118/118 (two inventor runs plus one independent
  run).
- **Observer.**
  - A fresh agent (Opus 5.5) in the observer room. It worked only through the observe MCP server and a workspace
    holding the guide and the app's public one-page manual.
  - Isolation: 13/13 probes, including no route to adb (5037) or the emulator (5554/5555).
  - Egress: MCP and the model API only.
  - Released after 38 minutes: about 26 rules (all corroborated, 12 earlier versions retracted), 60 probe rows,
    30 claims, 20 unknowns, 34/34 inventory items.
- **Implementer.**
  - A fresh agent (Opus 5.5) in the clean room with the spec only, no manual.
  - It compiled locally against the SDK stub; the gate built, installed and verified the APK.
  - Isolation: 9/9 probes. Egress: the gate and the model API only.

## Results

| | |
|---|---|
| Conformance (the last build, verified after the session) | **163 / 0 / 0** |
| Hidden suite (pinned 118) | **113 / 118 (95.8%)** |

- **Failures (5).** All are behaviors the implementer listed as guesses the spec did not settle:
  - two orders of validation checks (a dot-only diameter; range before decimals);
  - a trailing-zero load;
  - an error that should clear on typing in Settings;
  - one queue entry with normalized numbers.

  These are observer coverage gaps, not barrier effects.
- **Recognition.** The implementer did not recognize the app.

## Infrastructure incidents (fixed)

- **The emulator crashed mid-session** (GL context errors with the software renderer). The implementer's verify
  calls 2–4 failed on the gate, so its final build was verified only afterwards (163/0/0). The crash also showed
  that **the gate forwarded an unexpected exception's text, naming the original's real package**, to the clean
  side. The gate now returns only the clone's own build/install errors and its own refusals; anything else is a
  generic 500 (`b68490f`).
- **Observer-side MCP problems.** Long probe batches outlived the client's tool timeout while still running on the
  host, and the next call then collided with them on the single device. Fixes: calls are serialized on the
  server, the observer room sets a one-hour tool timeout, and `list_rules`, `list_feature_unknowns` and
  `run_sequence(symbols_only=...)` were added (`b46278c`).
- **Observer-reported tool issues, open:**
  - `outcome` checks compare nested maps (such as `controls`) exactly rather than as a subset;
  - field probes label valid min/max values as "refused" for number fields;
  - the length search mistakes value-range errors for length limits.

## Reading

This is the first measured result on mobile, and the first round with both sides enforced from the start on a
target no model can know. A spec produced through MCP alone, by a confined observer, was enough to rebuild a
three-screen app to 95.8% of its hidden tests. The remainder were unobserved orderings and messages.
