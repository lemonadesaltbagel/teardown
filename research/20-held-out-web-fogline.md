# Experiment: the sixth held-out web result (Fogline), measuring web.aria/v6

*2026-10-23. App and hidden suite: `.teardown/novel-web6/inventor/`. Project `.teardown/obs-w6`, kit
`.teardown/cleanroom/w6-r1` (codename juniper-pebble). Tooling frozen at `f377055`:
- `web.aria/v6`: dialog roles and accessible descriptions;
- the playbook's prompts for empty submits, encoded values and history.*

## Setup

- **Target.** Fogline, a registry for a fog-harvesting net cooperative: a 604-line API and a 1,044-line frontend.
  - Nets on four ridges. Each net's water ceiling per reading is mesh rate × area. A live preview shows it on
    the create/edit form.
  - Readings by season day, damage reports, repair, retirement.
  - Roles: steward, harvester (own nets), observer (read only).
  - A filtered, sorted, paged list and a ridges summary.
- **Neutral brief**, as in rounds 3–5, excluding all earlier domains.
- **Hidden oracle.** 128 Playwright tests. The original scores 128/128.
- **Observer.** Opus 5.5 in the observer room. It released after 24 minutes (96 turns, $5.08):
  - 50 rules, all corroborated. It retracted 14 along the way: 6 corrections and 8 rewordings the gate
    asked for.
  - No probe rows or claims. It stated everything as rules, read values through a "scratch" feature, and
    retracted what was superseded.
  - **106/112 coverage items** at release. The 6 open items were explained: repeated table states on other
    nets, and a ridge summary that always has four rows.
- **Implementer.** Opus 5.5 in the clean room, spec only. It needed **one verify call** and passed it with
  201/0/0. That took 45 turns (25 minutes) and $4.17. It did not recognize the app.
- **Isolation.** 9/9 clean-room probes passed. Egress was limited to the MCP server, the gate, the API and the
  model.

## Result

| held-out round | abstraction | hidden suite |
|---|---|---|
| Kilnroll | v1 | 64/120 (53%) |
| Kilnshare | v2 | 73/131 (56%) |
| Lockline | v3 | 106/130 (81.5%) |
| Scionry | v4 | 121/130 (93.1%) |
| Wickward | v5 | 114/127 (89.8%) |
| **Fogline** | **v6** | **112/128 (87.5%)** |

**What round 6 targeted held.** No test failed on these:
- dialog roles;
- accessible descriptions: the API's field errors are attached with `aria-describedby`, and the clone
  matched every one;
- empty submits;
- query encoding (`+` for spaces);
- history: filters replace the entry, and status messages clear on navigation.

The observer covered each of them deliberately.

## The 16 remaining failures

| cause | tests | kind |
|---|---|---|
| readings-table day cells are row headers (`<th scope="row">`); the clone used plain cells | 7 | **abstraction**: `tables` records cell values, not which cells head their row |
| fields marked `aria-invalid="true"` after a refused submit | 4 | **abstraction**: `invalid` reads only the browser's constraint validation |
| net actions sit in a named group (`role="group"`, "Net actions") | 2 | **abstraction**: groups are not recorded |
| create/edit 5xx message ("…Your changes were not saved.") | 2 | **observer gap hidden by a tooling bug**: coverage credited GET faults to POST/PATCH |
| the ceiling preview with an out-of-range height | 1 | **observer gap**: the derived value was checked only with valid inputs |

The clone guessed where the spec was silent, and the guesses were reasonable. It even used row headers on the
ridges table, which the hidden suite did not check.

## The coverage bug

Coverage credited a fault item `fault POST /api/nets 5xx` to any sequence that injected a 5xx on a matching
path, whatever the method, and whether or not the call was ever made while the fault was active. The observer
injected 5xx faults on `GET /api/nets…` and never on the create or edit calls, yet coverage showed those items
as covered. The observer noticed this and reported it ("over-credits the create/edit fault items"). It also
listed the forms' failure messages as a weak spot.

Fixed in `6931663`. A fault item now counts only when a recorded probe or rule observation shows that method
and path made while a matching fault was active. Recomputed on this project, the fix leaves
`POST /api/nets` and `PATCH /api/nets/{id}` × {5xx, network, malformed} uncovered. Release would have
refused them until they were exercised or explained.

## Fixes made after scoring

- **`web.aria/v7`** (the default for new projects):
  - an `invalid` control flag for `aria-invalid`, kept apart from constraint validation;
  - `row_headers` per table;
  - `groups`: each named group, radiogroup or toolbar, with the controls inside it.
- **Fault coverage** credited from recorded calls only (`6931663`).
- **Observer-reported issues.**
  - Inline action objects in a check now get a validation error instead of a `TypeError`.
  - Nested `null` in an expectation asserts absence (`{"controls": {"button:Delete": null}}`).
  - `ingest_docs` reports paragraphs the corpus already held. A second ingest returned 0, which the observer
    read as having gone to another project.
- **Playbook.** Derived values are also checked with out-of-range or unfinished inputs.

## Reading

- **Round 6 removed every failure class it targeted:** dialog roles, descriptions, empty submits, encoding and
  history.
- **13 of the 16 misses are again accessibility semantics the abstraction did not record:** row headers,
  `aria-invalid` and named groups. Each is a structural fact a test suite reaches through a role locator, and
  each is now in `v7`.
- **The other 3 are observer gaps.** Two of them were hidden by a coverage bug the observer itself reported.
- **Across six held-out apps the clones always matched their specs.** This round's clone needed one verify call.
  Every remaining gap was something the spec did not record or the observer did not exercise.
- **The pattern is consistent:** each round removes the classes it targeted, and the next suite reaches for one
  more kind of structure. The score has stayed between 87.5% and 93% since `v4`. The open question is whether
  the abstraction's coverage of role-addressable structure converges. A seventh round, measuring `v7`, would
  show it.
