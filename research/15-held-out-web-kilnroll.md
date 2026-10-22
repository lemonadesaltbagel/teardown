# Experiment: the first held-out web result (Kilnroll)

*2026-10-22. App and hidden suite: `.teardown/novel-web/inventor/`. Project `.teardown/obs-kiln1`, kit
`.teardown/cleanroom/kiln-r1` (codename ember-tundra). Tooling frozen at `50665bf` (discover_ui,
suggest_probes, playbook), plus a packaging-only fix to the room images (`6d2cddc`).*

## Why

Every web number so far (Conduit 80 → 99) was measured on the same suite the tooling was tuned against. This
round uses a web app nobody had tuned anything on, with the tooling frozen before the run.

## Setup

- **Target.** Kilnroll, a shared-kiln logbook for a pottery studio, written for the benchmark by a separate
  inventor agent.
  - 393-line stdlib JSON API with a reset endpoint; 794-line static single-page frontend.
  - Sign-in, a filtered and paginated list, a detail view, a create/edit form with client- and server-side
    validation, a destructive action with confirmation, firings with stage, cone and capacity rules, and guards.
- **Hidden oracle.** 120 Playwright tests using only roles, labels, text and URLs, with API faults injected via
  `page.route`. The original scores 120/120 (three inventor runs and one independent run).
- **Observer.** A fresh agent (Opus 5.5) in the observer room. It had the playbook, the guide, the app's public
  manual and two seed accounts. It released after 19 minutes:
  - about 190 actions, 58 of them fault/hang actions on 14 endpoints;
  - 48 rules, all corroborated;
  - 32 probe rows, 11 claims, 4 open unknowns.

  `discover_ui` found the screens; `suggest_probes`' endpoint × fault list drove the whole fault phase.
- **Implementer.** A fresh agent (Opus 5.5) in the clean room with the spec only. It used 3 verify calls; the
  last passed 224/224 conformance tests. It did not recognize the app.
- **Isolation.** 11/11 and 9/9 probes. Egress: MCP, the gate, the API and the model only.

## Result

| | |
|---|---|
| Conformance | 224 / 224 |
| **Hidden suite (pinned 120)** | **64 / 120 (53%)** |

Scoring note: as in the other rounds, the clone's codename is mapped back to the real name before scoring
(here by replacing it in a copy of the clone's files).

## Why half the hidden tests failed

The clone matched everything the spec recorded. The failures are behaviors the web abstraction (`web.aria/v1`)
did not record at all:

| missing from the abstraction | failed tests |
|---|---|
| table rows and cells (cells were not part of `text`) | 15 |
| status / flash messages (`role=status` was dropped as noise) | 14 |
| focus (which field is focused after a validation error) | 10 |
| page title (`document.title`) | 9 |
| select options, dialogs, `aria-current`, empty states | 8 |

Separately, the observer found that names containing `#` or `:` were lost to the `text` key, because
Playwright's YAML quoting was not undone.

## Fixes (after scoring)

- **`web.aria/v2`**, the default for new web projects (`4cd2b2a` and the next commit):
  - YAML quoting undone;
  - table cells in `text`;
  - `status`, `dialogs`, `options`, `title`, `focus`, and a `current` flag on controls.

  `web.aria/v1` is unchanged, so specs released under it keep verifying.
- **Process fixes:**
  - UI coverage counts only actions a probe or rule runs;
  - coverage resolves its own gap unknowns;
  - observer-side errors carry their message.

## Reading

- **The barrier, the rooms and the productivity tools did their job.** The observer covered its inventory in
  19 minutes, and the implementer reproduced the spec exactly (224/224).
- **The weak link was observation itself.** A third of the app's user-visible behavior (titles, focus, flash
  messages, tables) never entered the spec. Conformance cannot reveal this, because it only checks what was
  recorded. A held-out hidden suite can.
- **53% is the honest web number for the frozen tooling.** A re-run on Kilnroll with `v2` would be a
  development-set number again. The next honest measurement needs another new app.

## Still open from the observer's report

- Field claims that say "is accepted" for refused values.
- The length search missing limits of 41/31/201 characters.
- `retract_rule`'s reported counts.
- Session expiry (a 401 mid-session) was not observed.
