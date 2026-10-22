# Experiment: the third held-out web result (Lockline), measuring web.aria/v3

*2026-10-22. App and hidden suite: `.teardown/novel-web3/inventor/`. Project `.teardown/obs-w3`, kit
`.teardown/cleanroom/w3-r1` (codename cobalt-willow). Tooling frozen at `7b08dcc`: `web.aria/v3`, plus the
discovery fixes from round 2.*

## Setup

- **Target.** Lockline, a canal-lock passage booking app: 570-line API and 1,048-line frontend. Skippers
  register boats and book passages; lock keepers mark passages and close or reopen locks. Server-side rules
  cover size, closure, clashes, direction and chamber length.
- **Neutral brief.** Unlike round 2, the inventor brief named only app-level features (sign-in, browse,
  view, create/change with validation, remove, roles) and left the UI to the inventor. It listed none of the
  mechanics that `v2`/`v3` record, and it excluded the earlier domain.
- **Hidden oracle.** 130 Playwright tests. The original scores 130/130 (four inventor runs and one independent
  run).
- **Observer.** Opus 5.5, observer room, playbook, manual, three accounts. It released after 22 minutes:
  29 rules (17 scratch or reworded rules retracted), no field probes, 38/153 coverage items, 115 unknowns,
  prose findings left unfixed. `discover_ui` worked this time ("very useful"). Coverage was flooded by
  per-record items (every row link, every record id), so `suggest_probes` only offered row clicks.
- **Implementer.** Opus 5.5, clean room, spec only. 3 verify calls; the last passed 116/0, with 1 test
  inconclusive on the original's side. It did not recognize the app.
- **Isolation.** 11/11 and 9/9 probes; egress MCP, gate, API and model only.

## Result

| | Kilnroll (v1) | Kilnshare (v2) | **Lockline (v3)** |
|---|---|---|---|
| Conformance | 224/224 | 197/197 | 116/116 (+1 inconclusive) |
| **Hidden suite** | 64/120 (53%) | 73/131 (56%) | **106/130 (81.5%)** |

This was the thinnest spec of the three, yet it gave the best result. Recording the structure the hidden suites
check (titles, focus, status messages, tables, description lists) mattered more than spec volume.

## The 24 remaining failures

| cause | tests | kind |
|---|---|---|
| not-found pages, empty search results, permission and empty-state messages | 7 | **observer coverage**: never visited (38/153 covered) |
| text runs: the clone split inline text into separate elements to match the snapshot's line breaks, so whole-text reads ("Signed in as Otto Brandt") lost their spaces | 7 | **abstraction artifact** |
| named regions (`<section aria-label>`): lists reached through `region "Fits these locks"` | 6 | **abstraction**: region landmarks not recorded |
| search filtering (on Enter vs as you type) | 3 | **observed but not reproduced** |
| focus order (the skip link as the first Tab stop) | 1 | **not observed** |

## Fixes after scoring

- **`f8b8f89`:**
  - links that are table-cell values are records: one representative per table in discovery and coverage;
  - API paths fold id-bearing segments when no templates are declared;
  - `within`/`nth` for same-named controls;
  - `expect: null` matches an absent value;
  - a purpose error that lists the valid values.
- **Not yet done:**
  - region landmarks in the abstraction;
  - a text representation that tells the implementer where inline text joins (whitespace) rather than only
    line breaks;
  - nudging observers to close coverage before releasing (the playbook says so, and this observer stopped
    early).

## Reading

- **Three held-out web rounds: 53%, 56%, 81.5%.** Each round exposed the next layer of user-visible
  structure the abstraction lacked, and fixing it moved the next held-out score.
- **The remaining misses are about evenly split** between what the observer did not visit and what the
  abstraction still represents lossily (regions, inline text).
- **The barrier and the rooms held in all three rounds.**
