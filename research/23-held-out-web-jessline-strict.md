# Experiment: the ninth held-out web result (Jessline), web.aria/v9 and combination coverage

*2026-10-23. App and hidden suite: `.teardown/novel-web9/inventor/`. Project `.teardown/obs-w9` (strict), kit
`.teardown/cleanroom/w9-r1` (codename ember-pebble), logs `.teardown/obs-w9-logs/`. Tooling frozen at `429253b`:*
- *`web.aria/v9` (named focus);*
- *coverage for route × session and route × record status;*
- *the two verification fixes found in round 8's inconclusive checks.*

## Why this round

Both `v8` rounds lost their last tests to combinations the observer never visited: a route in another session
state, a record's page in another status. One more was lost to focus on a heading that the spec could not name.
This round measures the fixes for both on a new app, under the same conditions as rounds 7 and 8.

## Setup

- **Target.** Jessline, a log for a falconry centre: a 626-line API and a 1,094-line frontend.
  - Birds, their weighings and their flights. A bird's condition (Fly-ready within ±3% of its target weight,
    Heavy, Low, Unweighed) comes from its latest weighing by date.
  - A flight needs a same-day Fly-ready weighing, and a weighing cannot be removed while a flight depends on
    it. Moulting birds are not flown; retired birds are read-only; birds with flights cannot be deleted.
  - Roles: mews master, falconer, apprentice.
- **Hidden oracle.** 127 Playwright tests. The inventor ran it twice at 127/127, and an independent run before
  the observer started also gave 127/127.
- **Observer.** Opus 5.5 in the observer room (11/11 isolation checks). It stopped at the gate after 23
  minutes (131 turns, $7.29):
  - about 66 rules (all corroborated), 41 probe rows, 18 claims, 4 unknowns;
  - **101/102 coverage items**, including **all 16 route × session items** and **both route × record-status
    items**. Bird pages were visited for 9 different birds, and edit pages for 4.
  - It rewrote all 16 prose findings, so none reached the person.
- **The person at the gate** ran three `approve` commands (expected-output 162, interface 2, the skip-link
  gap) and `release`, in one pass. The audit chain verified (247 entries).
- **Implementer.** Opus 5.5 in the clean room (9/9 isolation checks), spec only. Two verify calls:
  270/1/0 → **271 passed, 0 failed, 0 inconclusive**. That took 43 turns, 29 minutes and $3.35. It did not
  recognize the app.
  - **No check was inconclusive this time.** Round 8 had 18, caused by the two verification bugs fixed
    before this round.

## Result

| held-out round | abstraction | gate | hidden suite |
|---|---|---|---|
| 1–6 | v1–v6 | standard | 53% → 56% → 81.5% → 93.1% → 89.8% → 87.5% |
| Strewnfield | v8 | strict | 129/130 (99.2%) |
| Belfry | v8 | strict | 126/130 (96.9%) |
| **Jessline** | **v9** | **strict** | **125/127 (98.4%)** |

The result held on a second run.

## The two failures

| test | cause | kind |
|---|---|---|
| `delete_dialog_escape` | the delete dialog focuses its Cancel button; `v9` recorded the focused button as `generic:` | **tooling bug in v9** |
| `detail_non_numeric_id` | `/birds/falcon` (letters where ids are numbers) shows "Bird not found"; the clone showed its generic not-found page | **observer**: never opened a malformed id |

**The `v9` bug.** `v9`'s focus reading falls back to `generic` for elements it has no role for, and decides
that by checking whether an element's role equals its tag name. For `<button>` the role *is* the tag name, so
every focused button became `generic:`. The test for `v9` checked headings only. The clone matched the spec,
which said only that focus was on "something generic". Fixed in `17fc5a0`. The surface audit now includes
focus on a button (41 pairs), so this mistake cannot pass the audit again. `v9` had not been published, so it
was fixed in place.

**What the combination coverage did.** Nothing failed for a route in another session state or a record's page
in another status. Those were the misses of both `v8` rounds. Here coverage listed them and the observer
exercised every one.

## Observer reports, checked

- **The notes limit.** The observer reported "277, not the documented 280", and that the length search missed
  it. Both are wrong. The server's limit is 280 characters after trimming. The observer's own boundary
  actions were mislabeled by three characters, which the implementer noticed. With this round's tooling,
  `probe_web_field` on the live edit form finds the limit (≤ 280).
- **Discovery missed the bird-page forms because the first bird it opened was retired.** Discovery now
  explores one row per status value, up to four per table (`7f9fe62`).
- **Smaller fixes:** `retract_rule` reports the rules left by status. The guide says what custom coverage
  patterns match, and that `ingest_docs` takes text, not a path.

## Reading

- **Three rounds at 96.9–99.2%.** Since `v8`, the score has stayed near the top on three apps. The remaining
  misses are a few per app, none of them structure the abstraction cannot record.
- **The combination coverage did its job.** The class of miss it targeted did not recur, and the observer
  covered every item it listed.
- **This round's tooling defect was caught by its own hidden suite, not by the audit.** The audit had one
  focus case, and it was a heading. The general lesson: an audit case per *kind* of element, not just per
  property, would have caught it. It now covers headings and buttons for focus.
- **The verifier is now clean.** Zero inconclusive checks this round, against 18 in round 8, so conformance
  numbers again mean what they say.
