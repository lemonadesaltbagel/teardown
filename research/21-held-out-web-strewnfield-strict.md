# Experiment: the seventh held-out web result (Strewnfield), web.aria/v8 under the strict gate

*2026-10-23. App and hidden suite: `.teardown/novel-web7/inventor/`. Project `.teardown/obs-w7` (strict),
kit `.teardown/cleanroom/w7-r1` (codename fjord-falcon). Tooling frozen at `5a006ee`:
- `web.aria/v8`: the user-facing Playwright surface (`outline`, `properties`);
- live-output coverage;
- `teardown review` showing coverage gaps of rules-only drafts.*

## What was new

- **The abstraction came from a principle, not from a failure.** Before this round, `v8` was built from an audit:
  pages that differ in one thing a user-facing Playwright locator or assertion can check (39 pairs), and pages
  that differ only in implementation (7 pairs). `v7` told apart 17 of the 39. `v8` tells apart all 39 and
  keeps the 7 identical (`teardown.drivers.web.surface`, pinned by a test).
- **The strict gate, used by one developer.** Earlier rounds ran in standard mode. Here the person running the
  gate created the project in strict mode, and the observer was told it could not approve. A person then
  reviewed and approved at their own terminal.

## Setup

- **Target.** Strewnfield, a custody ledger for a meteorite vault: a 654-line API and a 1,197-line frontend.
  - Specimens and fragments split from them. A split takes mass from the parent, which keeps at least 1 g.
  - Loans and returns; quarantine blocks splitting and lending.
  - Deletion is refused while a specimen is on loan or has fragments; edits are logged with the changed
    fields.
  - Roles: curator, researcher (own records), visitor (read only). A vault summary page.
- **Neutral brief**, as in rounds 3–6, excluding all earlier domains.
- **Hidden oracle.** 130 Playwright tests. The inventor ran it twice at 130/130, and an independent run before
  the observer started also gave 130/130.
- **Observer.** Opus 5.5 in the observer room (11/11 isolation checks). It stopped at the gate after 32
  minutes (108 turns, $6.49):
  - 64 rules (all corroborated, 16 retracted along the way), 94 probe rows, 20 claims, 3 unknowns;
  - **102/105 coverage items**, including every endpoint × {5xx, network, malformed} and session expiry;
  - all 11 statements the gate flagged as prose were rewritten in its own words, so **no prose finding was
    left**;
  - one `release_spec` call to see what still blocked, as instructed; no attempt to work around the gate.
- **Implementer.** Opus 5.5 in the clean room (9/9 isolation checks), spec only. **One verify call: 332 passed,
  0 failed, 1 inconclusive** (the original diverged from its own spec on one check). That took 37 turns, 26
  minutes and $3.26. It did not recognize the app.

## The strict gate, from the person's side

`teardown review` listed what blocked the release:

| what | count | decision |
|---|---|---|
| expected-output findings (app text in recorded expectations) | 180 | one class approval, reason `test-oracle` |
| interface findings (action names from accessible names) | 11 | one class approval, reason `accessibility-name` |
| prose findings | 0 | none needed: the observer rewrote them |
| coverage gaps (the one-row state of three fixed-size tables) | 3 | one acknowledgement, with a note |

**The person ran three `teardown approve` commands and one `teardown release`.** Each `approve` showed what it
covered and asked them to type the codename. The audit log (324 entries, chain verified) records each decision
once, with the approver's handle, in order: two class approvals, the coverage acknowledgement, the release.

**One rough edge.** The person ran the command block twice. The class approvals had succeeded in the first run,
so the second run printed `recorded 0 approval(s)`. That looked as if nothing had happened. A repeat now says
who already approved.

The end-to-end test added before this round (`tests/test_strict_web.py`) drives the same loop automatically:
the observer over MCP/HTTP, and approvals typed into a real pseudo-terminal. That test found one bug before the
round: `teardown review` hid the coverage gaps of drafts that had no probe rows.

## Result

| held-out round | abstraction | gate | hidden suite |
|---|---|---|---|
| Kilnroll | v1 | standard | 64/120 (53%) |
| Kilnshare | v2 | standard | 73/131 (56%) |
| Lockline | v3 | standard | 106/130 (81.5%) |
| Scionry | v4 | standard | 121/130 (93.1%) |
| Wickward | v5 | standard | 114/127 (89.8%) |
| Fogline | v6 | standard | 112/128 (87.5%) |
| **Strewnfield** | **v8** | **strict** | **129/130 (99.2%)** |

The result held on a second run.

## The one remaining failure

`summary_nothing_on_loan`: once every loan is returned, the summary page says "Nothing is on loan." in place
of the list of loans. The observer never returned every loan, so the spec never showed that state. The
implementer flagged the wording as its own guess ("No specimens are on loan.").

This is an **observer gap of a known kind**: a data state, here of a named list rather than a table, which
coverage did not count until now.

## Fixes made after scoring

These were made in a separate worktree while the clean room ran, so the gate's code stayed frozen, and merged
afterwards (`466cf6a`, `0e3216f`):

- **Data states of named lists.** Named lists in the `v8` outline get none/one/several coverage items, like
  tables.
- **Length search.**
  - The search now finds a minimum length first. The observer reported a missed 200-character limit. The real
    cause was a 5-character minimum: the search started at 3 characters, was refused, and gave up.
  - Field probes treat an API 4xx, a dialog that stays open and an `aria-invalid` field as refusals.
  - On the live app, the Reason field now probes as 5–200 characters.
- **Coverage.**
  - An expected empty object means none, as `[]` does. `controls: {}` used to pass vacuously.
  - A control whose recorded clicks all came back `NA` is no longer counted as covered.
- **Usability.** Discovery-style `click[role:name]` names define themselves in `check_rules`. Undefined names
  for folded table rows used to reject a whole batch.

## Reading

- **The principled abstraction closed the structural gap.** Every earlier round lost 5–15 tests to structure
  the spec did not record. This round lost none. The audit enumerates what a user-facing suite can check rather
  than waiting for a suite to show it, which is why the misses did not simply move to the next layer.
- **One held-out app is one data point.** The jump from 87.5% to 99.2% coincides with `v8`. It also coincides
  with an app whose behavior may have been easier to observe. A second app measured with `v8` would separate
  the two.
- **The strict gate is usable by one person when the observer does its part.** The observer rewrote its prose
  findings, so the person's decisions were three class-level ones. The functional text a clone must reproduce
  (180 findings) is approved in one step, because the gate classifies it rather than listing it line by line.
- **Isolation, strictness and outcome are independent.** The observer could not approve, the implementer saw
  only the approved spec, and the clone still passed 129 of 130 hidden tests.
