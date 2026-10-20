# Experiment: web clean room on a real app (RealWorld "Conduit"), Phase 2 exit

*2026-10-20. Kit: `.teardown/cleanroom/juniper-falcon/` (local only).*

## Setup

- **Original.**
  - Frontend: the RealWorld Angular reference frontend.
  - Backend: a spec-compliant Django Ninja API, self-hosted.
  - Database: SQLite, restored in-container before every episode, seeded with two demo users plus their articles and comments.
- **Hidden oracle.**
  - RealWorld's shared Playwright E2E suite (123 tests in `spa` mode).
  - The original passes 101. The other 22 tests intercept requests to the public demo API host, so they cannot apply to a local backend.
  - Pinned denominator: **101**.
- **Observer.** An independent agent using Teardown's web API and the observer guide. It never read the app's source or bundles. It released:
  - 223 actions;
  - 13 probed fields (134 rows, 48 mined claims);
  - **43 rules** (all corroborated);
  - a learned 10-state sign-in/sign-up model;
  - 17 API endpoints with value-free shapes;
  - 62/65 inventory items covered.
- **Clean implementer.** A separate agent restricted to the kit, with:
  - the Teardown spec;
  - the **public `SELECTORS.md` contract** that RealWorld publishes for frontend implementers (CSS classes, field names, routes);
  - the backend API.

  It wrote about 1,300 lines of plain HTML/JS/CSS, including its own markdown renderer.

## Results

| | |
|---|---|
| Teardown conformance (verify-web) | **342 / 342** (after two Teardown fixes, below) |
| Hidden RealWorld E2E (pinned 101) | **80 / 101 (79.2%)** |

### The 21 hidden failures map to two observer gaps

**1. Query strings were invisible (8 tests).**
- Symbols carry route *paths* and API *path templates*. They drop query strings, so `?feed=following` and `?page=N` routing was never observed. The observer flagged this in its report.
- The clone routed feeds and pages with history state instead of URLs.
- **Fix:** include query keys (and observed values for routing parameters) in route and network symbols.

**2. Error handling under faults was unobservable (11 tests, plus 2 on 404 pages and 2 on null-bio rendering).**
- The suite checks how the frontend behaves when the API returns 5xx, times out, fails at the network level or sends malformed JSON. A passive observer of a healthy backend never sees any of that.
- **Fix — fault-injection probes:** route specific API calls of the *original* to a 500, a network failure, a timeout or a malformed body, and observe the frontend's handling.
  - This observes the original's own error handling in our own deployment. It is not circumvention.
  - Fault classes and the endpoints they target become part of the probe plan and the coverage inventory.

### Two Teardown bugs found by this run (fixed in `06daf31`)

1. **Codename renaming reordered keys** inside canonical symbols, which caused 47 false failures. Comparison is now structural.
2. **Non-dict symbols** (`DISABLED`, `NA`) never matched the outcome-shaped expectations, which caused 134 false inconclusives.

## Contamination

- The implementer recognized the app as RealWorld Conduit: `SELECTORS.md` names it, and the app is famous.
- It reports building from the spec, the contract and live API responses, with recognition shaping only the general layout.
- This experiment demonstrates the web loop on a real app with a real backend. **It is not an uncontaminated measurement of spec value**; `research/11` is that measurement.

## Round 2: query strings + fault injection (re-run)

*Kit: `.teardown/cleanroom/web-r2/` (codename again juniper-falcon), project `.teardown/obs-web2`.*

- **Observer.** Fresh agent with a *neutral* prompt that pointed only at the guide's Web section; no behaviors were taken
  from the hidden suite. (A first attempt whose prompt carried hidden-suite-derived hints was stopped before it
  recorded anything, and its artifacts were deleted.) It released:
  - 358 actions, including fault-injection actions on 18 endpoints (5xx, abort, malformed body, timeout, 404, 401) and
    query-string deep links;
  - 13 probed fields (144 rows, 58 claims), **60 rules** (all corroborated), the same 10-state auth model;
  - 84/88 inventory items covered, 10 unknowns.
- **Clean implementer.** Fresh agent, the round-1 instructions word for word, plus the same public `SELECTORS.md`.
  About 1,400 lines of plain HTML/JS/CSS; 2 of 6 verify calls used.

| | Round 1 | Round 2 |
|---|---|---|
| Teardown conformance (verify-web) | 342 / 342 | **438 / 438** |
| Hidden RealWorld E2E (pinned 101) | 80 / 101 (79.2%) | **93 / 101 (92.1%)** |

Per-test comparison (both clones re-scored on the same day; the round-1 clone again scored 80):

| Round-1 failure group | Tests | Round 2 |
|---|---|---|
| Query-string routing and pagination (`?page=N`, `?feed=following`, tab hrefs) | 8 | all pass |
| Server unavailable at start-up (5xx, malformed JSON, network failure or timeout on the current-user fetch) | 5 | all pass |
| Page wrapper missing after a failed article/profile load (500, network error, 404) | 6 | still fail |
| Empty bio element | 2 | still fail |

(Round 1's write-up above split the 21 as 8 + 11 + 2 + 2; the per-test re-run gives 8 + 5 + 6 + 2.) The clone
passes none of the original's 22 inapplicable tests, as expected.

### The 8 remaining failures: empty structure is invisible to the accessibility view

- **Wrapper on failed loads (6 tests).** When the article or profile request fails (500, network error, 404), the
  original still renders the page wrapper (`.article-page`, `.profile-page`/`.user-info`) with no accessible content.
  The observer correctly recorded "only header and footer" in the ARIA view, so the clone rendered nothing.
- **Empty bio element (2 tests).** With a null or cleared bio, the original renders an empty `<p>` in `.user-info`;
  the clone omits it.

Fault injection made the failed loads observable, and the observer recorded them correctly; what the ARIA view
lacks is the empty wrapper. In both cases the abstraction cannot tell "an empty element is there" from "nothing is
there". The public contract
names exactly these selectors, so the fix is generic and stays at the behavior tier:

- **Contract-selector observations.** When the observer supplies a public contract (selectors from `SELECTORS.md`
  or similar), `web.aria` records, per listed selector, whether it is present, visible and empty. Rules and
  conformance can then compare it like any other key. Only selectors from a public document are observed; the
  rest of the DOM stays out of the record.

### Notes

- Contamination is as in round 1: the implementer recognized RealWorld Conduit and says it followed the spec where
  spec and memory disagreed (empty-feed text, blank `/login` page when already signed in).
- Process slips reported by the implementer: it listed a browser cache folder outside the kit (nothing used), and it
  created a probe user and two articles through the API (the database is reset before every run).

## Next

- [x] Query strings in route and network symbols.
- [x] Fault-injection probes for web (5xx, abort, timeout, malformed body). CLI (I/O faults) and Android (network
  off) remain.
- [x] Re-run Conduit with both fixes: 93/101 (target was ≥ 95).
- [ ] Contract-selector observations (presence/visibility/emptiness of public-contract selectors), then re-run.
- [ ] Injected timeouts that actually hang, so pending-state UI is observable.
