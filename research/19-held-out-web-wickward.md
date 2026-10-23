# Experiment: the fifth held-out web result (Wickward), measuring web.aria/v5 and data-state coverage

*2026-10-22. App and hidden suite: `.teardown/novel-web5/inventor/`. Project `.teardown/obs-w5`, kit
`.teardown/cleanroom/w5-r1` (codename delta-summit). Tooling frozen at `c7a039b` plus an uncommitted diff
(sha256 `311ff77b81a5b80f…`):
- `web.aria/v5` generated content;
- data-state and session-expiry coverage items with suggestions;
- the playbook's data-state, session and role prompts.*

## Setup

- **Target.** Wickward, a street-lantern registry: 460-line API and 1,066-line frontend.
  - Lighting burns oil by wick type; refills only when dark, up to capacity.
  - Condemn/restore with a reason (warden only); removal only when condemned or without history.
  - A logbook and a districts summary.
  - Roles: warden, lamplighter (own district only), observer (read only).
- **Neutral brief**, as in rounds 3 and 4, excluding all earlier domains.
- **Hidden oracle.** 127 Playwright tests. The original scores 127/127 (two inventor runs and one independent
  run).
- **Observer.** Opus 5.5, observer room. Released after 32 minutes:
  - 56 rules (all corroborated), 82 probe rows, 29 claims;
  - **108/111 coverage items**; the 3 gaps were explained (an unclickable skip link, a table with no one-row
    state, a fixed set of four districts);
  - rules for each endpoint × {5xx, network, malformed} plus a 401 rule.
- **Implementer.** Opus 5.5, clean room, spec only. 3 verify calls (206/107 → 309/4 → 313/0, with 2 tests
  inconclusive on the original's side). It did not recognize the app.
- **Isolation.** 11/11 and 9/9 probes; egress MCP, gate, API and model only.

## Result

| held-out round | abstraction | hidden suite |
|---|---|---|
| Kilnroll | v1 | 64/120 (53%) |
| Kilnshare | v2 | 73/131 (56%) |
| Lockline | v3 | 106/130 (81.5%) |
| Scionry | v4 | 121/130 (93.1%) |
| **Wickward** | **v5** | **114/127 (89.8%)** |

**What round 5 targeted held.** Nothing failed for CSS-generated text, list data states (none, one,
several, singular wording) or session expiry. The observer covered them deliberately.

## The 13 remaining failures

| cause | tests | kind |
|---|---|---|
| the remove confirmation is an `alertdialog`; the clone used `dialog` | 7 | **abstraction**: `dialogs` records names, not the role |
| accessible descriptions (`aria-describedby` hints on a button and a field) | 2 | **abstraction**: descriptions are not recorded |
| query encoding (`district=Old%20Town` vs `Old+Town`) | 1 | **reproduction**: to check how the spec showed it |
| empty sign-in message; back keeps filters; status cleared on navigation | 3 | **not reproduced** |

## Fixes made after scoring (uncommitted, in the working tree)

- Nested subset expectations need their keys: a made-up control key no longer passes.
- `fault {mode: clear}` removes injected faults mid-episode.
- The guide documents expecting `NA`/`DISABLED`.

## Reading

- **Round 5 removed the failure classes it targeted** (generated content, data states, sessions).
- **The next layer is again accessibility semantics:**
  - the role that distinguishes an alert dialog from a dialog;
  - descriptions attached with `aria-describedby`.
- Both can be recorded (`dialogs` with roles, a `descriptions` key) in a `v6`, then measured on a sixth
  held-out app.
- **Across five held-out apps the clones always matched their specs.** Every remaining gap was something the
  spec did not record or the observer did not exercise.
