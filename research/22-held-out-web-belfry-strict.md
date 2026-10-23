# Experiment: the eighth held-out web result (Belfry), a second web.aria/v8 round under the strict gate

*2026-10-23. App and hidden suite: `.teardown/novel-web8/inventor/`. Project `.teardown/obs-w8` (strict), kit
`.teardown/cleanroom/w8-r1` (codename basalt-meadow), logs `.teardown/obs-w8-logs/`. Tooling frozen at
`931c0d9`: round 7's tooling plus its post-round fixes (named-list data states, the minimum-length search,
server-side refusal signals).*

## Why this round

Round 7 scored 99.2% (`research/21`), up from 87.5%, but it changed two things at once: the abstraction (v7 to
v8) and the app. This round repeats round 7's conditions with a new app: v8, strict gate, both sides
confined, a neutral brief. If v8 explains the jump, the score should stay near the top. If round 7's app was
just easier, it should fall back toward the 87–93% of rounds 4–6.

## Setup

- **Target.** Belfry, a planner for summer carillon recitals: a 666-line API and a 1,197-line frontend.
  - Performers create recitals (tower, date, 30/45/60-minute slot, programme note), then add and reorder
    pieces.
  - A piece cannot need more bells than its tower has, and the programme must fit the slot.
  - A tower cannot be booked twice on one date; dates fall within the season; a performer has at most one
    recital a day.
  - Recitals go draft → submitted → approved or returned. Tower keepers review them; visitors browse the
    public schedule and the towers.
- **Hidden oracle.** 130 Playwright tests. The inventor ran it twice at 130/130, and an independent run before
  the observer started also gave 130/130.
- **Observer.** Opus 5.5 in the observer room (11/11 isolation checks). It stopped at the gate after 27
  minutes (84 turns, $4.89):
  - 66 rules (all corroborated), 40 probe rows, 12 claims, 2 unknowns;
  - **98/99 coverage items**. The one gap was a skip link that appears only on keyboard focus; the observer
    explained it.
  - It rewrote every prose finding, so none reached the person.
- **The person at the gate** ran `teardown review`, three `teardown approve` commands (expected-output 142,
  interface 26, the coverage gap) and `teardown release`, in one pass. The audit chain verified (233
  entries), with exactly the two class approvals by the person.
- **Implementer.** Opus 5.5 in the clean room (9/9 isolation checks), spec only. It made three verify calls:
  188/49/18 → 208/29/18 → **237 passed, 0 failed, 18 inconclusive**. The 18 are checks on which the original
  diverged from its own spec; they were not investigated. That took 63 turns, 41 minutes and $5.81. It did not
  recognize the app.

## Result

| held-out round | abstraction | gate | hidden suite |
|---|---|---|---|
| Kilnroll | v1 | standard | 64/120 (53%) |
| Kilnshare | v2 | standard | 73/131 (56%) |
| Lockline | v3 | standard | 106/130 (81.5%) |
| Scionry | v4 | standard | 121/130 (93.1%) |
| Wickward | v5 | standard | 114/127 (89.8%) |
| Fogline | v6 | standard | 112/128 (87.5%) |
| Strewnfield | v8 | strict | 129/130 (99.2%) |
| **Belfry** | **v8** | **strict** | **126/130 (96.9%)** |

The result held on a second run.

## The four failures

| test | cause | kind |
|---|---|---|
| `submitted_recital_cannot_be_edited`, `approved_recital_is_locked_for_owner` | the edit page of a submitted or approved recital is its own "Cannot edit recital" screen; the observer never opened a locked record's edit page | **observer**: a route in a record status not visited |
| `sign_in_page_redirects_when_signed_in` | a signed-in user who opens the sign-in page is sent to their recitals | **observer**: a route in a session state not visited |
| `move_piece_up_in_longer_programme` | after a move in the middle of a programme, focus stays on the move button | **observer**: only moves to an edge were observed. There the button becomes disabled and focus goes to a heading, which the clone generalized. |

**None of the four is a structure v8 does not record.** One representation weakness did contribute to the
last one. Focus on a heading is recorded as `h2:`, the element's tag without its text. The spec showed that
focus moved to *a* heading, but not to which one.

## A gate finding: a real name that is also an ordinary word

The product's name, Belfry, is also part of the data: one tower is called "Old Granary Belfry". The gate
replaces every real name with the codename, data included, so the spec showed "Old Granary basalt-meadow".
The clone could only match by rewriting that word in the API's data. It did so, and reported it as a
workaround. After scoring renamed the codename back, the rewrite does nothing, so the score is unaffected.

Fixing this inside the gate is hard: the gate cannot tell which occurrences are the product. The guide now
advises listing only distinctive forms in `real_names`, and says what to expect otherwise.

## Fixes made after scoring

These were made in a separate worktree while the clean room ran and merged afterwards (`3b3073d`):

- `discover_ui` runs accumulate. One run per role used to replace the previous inventory, so the observer
  lost the performer's fields from coverage.
- Fault suggestions show the observed path (`/api/recitals/{id}/pieces/{id}`) next to the contract path
  named by `api_templates` (`…/pieces/{piece}`).
- `propose_claim` lists the valid kinds; `run_sequence` takes `keys` to return only those parts of each
  symbol.
- The playbook now asks the observer to:
  - visit each route signed out and signed in, the sign-in page included;
  - open each record's pages in every status;
  - reorder in the middle as well as at the edges, checking focus each time.

## Reading

- **v8 explains most of the jump.** The two v8 rounds scored 99.2% and 96.9%, against 87.5–93.1% for rounds
  4–6. In both v8 rounds every miss was a state or route the observer did not exercise, not page structure the
  spec failed to record.
- **The remaining gap is the observer's.** The misses are unvisited combinations: a route × a session state, a
  route × a record status, an interaction in the middle rather than at the edges. Coverage measures routes,
  controls, faults and data states one at a time; these misses are about combinations. The playbook now names
  them. Coverage items for route × session and route × record status are the next step if they recur.
- **One known representation weakness:** focus on non-interactive elements (headings) is recorded without a
  name. Fixing it changes recorded symbols, so it belongs in a versioned abstraction (a `v9`), not in place.
- **The strict gate's cost stayed small.** Two rounds in, one person makes three class-level decisions per
  release, because the observer rewrites its own prose and explains its gaps.
