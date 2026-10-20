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

## Next

- [ ] Query strings in route and network symbols.
- [ ] Fault-injection probes for web: an API route returns 5xx, is aborted, times out or sends a malformed body. Same for CLI (I/O faults), and Android (network off).
- [ ] Re-run Conduit with both fixes. Target: ≥ 95/101.
