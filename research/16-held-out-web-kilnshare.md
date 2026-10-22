# Experiment: the second held-out web result (Kilnshare)

*2026-10-22. App and hidden suite: `.teardown/novel-web2/inventor/`. Project `.teardown/obs-w2`, kit
`.teardown/cleanroom/w2-r1` (codename ember-meadow). Tooling frozen at `4ccad3c` (`web.aria/v2`).*

## Why

`web.aria/v2` added what the first held-out round (`research/15`) showed missing: page titles, focus, status
messages, dialogs, select options, `aria-current`, table cells. This round measures v2 on an app nobody had
tuned anything on.

**Caveat.** My prompt to the inventor asked for a broad range of ordinary web UI behavior, explicitly including
page titles, focus, flash messages, tables, dialogs and current-page navigation, which are the categories v2
added. That stops the benchmark from avoiding them, but I chose them knowing v2. The inventor also picked a
domain close to round 1's (a kiln firing queue); the observer and implementer were fresh agents who saw
neither earlier app.

## Setup

- **Target.** Kilnshare, a pottery co-op's kiln firing queue: 416-line API and 894-line frontend.
  - Sign-in with redirect back; a queue with filters, sort and paging in the URL; a detail view; a create/edit
    form whose cone options depend on clay and firing.
  - Client- and server-side validation, focus on the first invalid field, flash messages, withdrawal with a
    confirmation dialog, error handling.
- **Hidden oracle.** 131 Playwright tests (roles, labels, text, URL, title, focus). The original scores 131/131
  (four inventor runs and one independent run).
- **Observer** (Opus 5.5, observer room, playbook, manual, four accounts). Released after 16 minutes: 63 rules
  (all corroborated), 34 probe rows, 12 claims, 6 unknowns, 27/27 endpoint × fault items.
  - **`discover_ui` crashed on every run:** it clicked an off-screen skip link and called `fill` on a
    `<select>`. All discovery was manual, and `suggest_probes` had nothing to work from.
- **Implementer** (Opus 5.5, clean room, spec only). 2 verify calls; the last passed 197/197 conformance tests.
  It did not recognize the app.
- **Isolation.** 11/11 and 9/9 probes; egress MCP, gate, API and model only.

## Result

| | Kilnroll (v1) | Kilnshare (v2) |
|---|---|---|
| Conformance | 224 / 224 | 197 / 197 |
| **Hidden suite** | 64 / 120 (53%) | **73 / 131 (56%)** |

## What failed, and what did not

- **No failure in the categories v2 added.** Titles, focus, status messages, options, dialogs and
  `aria-current` all held.
  - In round 1 these took about 40 tests.
- **54 failures: table structure.** The hidden suite reaches list rows and detail fields through the table
  ("the table named Pieces, its rows, its column headers"). v2 flattened cells into `text`, so the spec never
  said there was a table named Pieces, or which columns it had. The implementer rendered the list its own way.
- **Description lists** were not observed at all. The implementer reported that its `<dt>/<dd>` detail fields
  were invisible to conformance, and converted them to paragraphs.
- **4 failures: URL normalization** (clamping an out-of-range page, dropping an invalid page parameter). The
  observer had recorded junk query parameters as an unknown.

## Fixes (after scoring)

- **`web.aria/v3`**, the default for new projects:
  - `tables`: name, columns, and rows of cells (cells leave `text`);
  - `definitions`: term/definition pairs.

  v2 is unchanged.
- **Discovery robustness** (`c079db6`):
  - an element a user cannot act on is unavailable (NA), not a crash;
  - comboboxes get an observed option;
  - `back`/`forward`/`reload` actions.
- **Rule and field-probe checks** (`c079db6`):
  - rule checks reject undefined or empty action lists;
  - web field probes judge acceptance by outcome shape.

## Reading

- **Two held-out web rounds, 53% and 56%.** The barrier, the rooms and conformance did their job both times:
  each clone matched its spec exactly.
- **What limits the result is how much of a web app's user-visible structure the abstraction records.** Each
  round found the next missing layer:
  - round 1: titles, focus, messages;
  - round 2: tables and description lists.
- **What the hidden suites check is mostly accessibility semantics.** That is the right target for a
  behavior-first tool, and it is still being completed.
- **v3 needs a third held-out app** to be measured. With `discover_ui` fixed, that round will also be the
  first to test discovery on a held-out target.
