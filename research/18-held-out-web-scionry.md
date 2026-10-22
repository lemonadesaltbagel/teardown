# Experiment: the fourth held-out web result (Scionry), measuring web.aria/v4 and coverage-gated release

*2026-10-22. App and hidden suite: `.teardown/novel-web4/inventor/`. Project `.teardown/obs-w4`, kit
`.teardown/cleanroom/w4-r1` (codename amber-lantern). Tooling frozen at `7b98a0e`: `web.aria/v4` landmarks,
releases that need coverage gaps exercised, explained or accepted, and the keyboard and unhappy-route playbook.*

## Setup

- **Target.** Scionry, a graft register for a heritage apple orchard: 612-line API and 1,260-line frontend.
  - A status flow (planned → grafted → taken or failed, with confirmation for failure).
  - Row space by rootstock.
  - Pollination partners (triploids cannot partner).
  - Roles: steward, grafter (own grafts only), observer (read only).
- **Neutral brief**, as in round 3, excluding the earlier domains.
- **Hidden oracle.** 130 Playwright tests. The original scores 130/130 (two inventor runs and one independent
  run).
- **Observer.** Opus 5.5, observer room, playbook, manual, four accounts. Released after about 25 minutes:
  58 rules (all corroborated), 39 fault actions, 8 probe rows, 4 claims, **77/79 coverage items**. The two gaps
  were explained (a control reachable only through crawler-created data, and an off-screen skip link). All 13
  endpoints × 3 fault classes were covered.
  - Round 3's observer released at 38/153. The release rule (refuse while gaps are neither exercised nor
    explained) is the change between them.
- **Implementer.** Opus 5.5, clean room, spec only. It got 201 passed, 0 failed, 1 inconclusive (the
  original's side). It did not recognize the app.
- **Isolation.** 11/11 and 9/9 probes; egress MCP, gate, API and model only.

## Result

| | Kilnroll (v1) | Kilnshare (v2) | Lockline (v3) | **Scionry (v4)** |
|---|---|---|---|---|
| Conformance | 224/224 | 197/197 | 116/116 (+1) | 201/201 (+1) |
| **Hidden suite** | 53% | 56% | 81.5% | **121/130 (93.1%)** |

## The 9 remaining failures

| cause | tests | kind |
|---|---|---|
| "⚠︎ Needs partner": the original draws the icon with CSS generated content. Chromium includes it in accessible names (so the snapshot showed "⚠︎ Needs partner"); element text does not. The clone wrote a literal ⚠︎. | 4 | **abstraction**: accessible names and element text differ for generated content |
| singular count text ("1 graft") | 2 | **not observed** (only plural lists were seen) |
| the session-expired message | 1 | **not observed** (listed as a weak spot) |
| a filter hidden for the read-only role | 1 | **not observed** |
| one list row's status cell | 1 | same as the generated-content case |

## Reading

- **Each held-out round removed the previous round's main failure class:**
  - v2 removed missing titles, focus and messages;
  - v3 removed missing tables;
  - v4 removed lossy landmarks and inline text.
- **The coverage-gated release turned a 38%-covered spec into a 97%-covered one.**
- **What is left is small and specific:**
  - generated content (CSS `::before`) that appears in accessible names but not in text;
  - behaviors that need a particular data state the observer did not create (exactly one result, an expired
    session).
- **The barrier and the rooms held in all four rounds.**
- **Next held-out run (round 5):**
  - record when an accessible name contains text that the element's own text does not (generated content);
  - add data-state prompts to the playbook (one item, none, many; expired sessions).
