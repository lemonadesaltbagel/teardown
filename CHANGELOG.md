# Changelog

## Unreleased

- Results: a real open-source app, Flipt v1.61.0, scored 9/55 on its own UI suite; a second
  held-out Android app, Saltrake, 100/119 under the strict gate, built without verify feedback after the emulator
  crashed.

- `android.a11y/v3`, the default for new Android projects: a control named by its content description but showing
  other text ("Open" described as "Open North") records that text in `properties`, and `keyboard: shown` records
  that the soft keyboard is up (it takes the next Back press). The Android audit adds both cases (23 pairs) and
  observes each screen after it settles; v3 records all 23.
- The Android driver waits for the screen to change after an action (up to 0.6 s) before taking it as settled:
  right after a tap, two quick dumps could both show the old screen. Android fills refuse non-ASCII text, which
  adb cannot type and used to leave the field empty, and field probes record an unknown for those classes.

- The clean side's `verify` prints the gate's own message (its refusal, the clone's build error, or "could not
  run on the gate, try again later") instead of a bare `HTTP Error 400: Bad Request`. When the emulator died
  during the second Android round, the implementer saw only bare errors and could not tell an outage from a
  broken build.

- A `patch` fault passes the real JSON response with fields changed (`set: {"storage.readOnly": true}`), so
  server modes the UI reads (read-only, maintenance) become observable. On Flipt, 21 of its 55 UI tests mock
  read-only mode this way, and without it the observer could not see that mode.

- Coverage keeps the observer's own inventory items across calls (a later call without them used to drop them),
  and `teardown review` and a strict release judge the gaps as they are now. `check_rules` checks its budget
  after every rule, and a contested result says which checks differed between runs. API version segments
  (`/auth/v1`) are no longer folded as record ids.

- `web.aria/v10`, the default for new web projects: hash-routed apps record their route in `path`
  (`/#/namespaces/default/flags`), and route templates and coverage use it; with `mask_dates`, times of day and
  relative times ("3 seconds ago") are masked too. `check_rules` runs in batches within `max_seconds` (200 over
  MCP) and returns the rest as `not_checked`; `discover_ui` checks its budget between screens as well. A control
  that mounts just after a step (a sliding panel) is waited for briefly before the step is `NA`, and a click that
  fails while it animates is retried. All found on Flipt, a real application.

- Long observe calls report MCP progress every 15 seconds (`TEARDOWN_HEARTBEAT_S`), so clients with an idle
  timeout no longer abandon a crawl the server is still running. `discover_ui` takes a time budget
  (`max_seconds`, default 240) and returns what it found. A browser whose connection died is replaced instead of
  failing every later call. With `mask_dates`, `v9` also masks times of day in control names, options and the
  outline. Found on a real application (Flipt), where a crawl outlasted the client's timeout and every later call
  failed.

- `android.a11y/v2`, the default for new Android projects: `outline` (meaningful nodes in screen order, with
  heading, selected and dialog flags), `properties` (field value except passwords, hint, error text, masked,
  progress range, state description) and `dialogs`. An Android surface audit
  (`teardown.drivers.android.surface`, with its own app) lists 21 screen pairs an Espresso or UiAutomator test can
  tell apart and 4 implementation-only ones: v2 records all 21 and none of the 4; v1 records 9 to 12, depending
  on whether error popups and dialogs have appeared when it observes. The on-device
  agent reports error text, headings, state descriptions, ranges and windows (version 2; the driver replaces an
  older agent). `teardown install-android-agent` builds the agent for an installed copy (the wheel ships its
  sources) and keeps one signing key per machine.

- Installable on its own: `uv tool install "teardown[web] @ git+https://github.com/lemonadesaltbagel/teardown"`,
  then `teardown install-browser` and `teardown demo`. The wheel carries the room files, and an installed copy
  assembles the room images' build context under `~/.teardown` (`TEARDOWN_HOME`); kits call the installed
  interpreter. `aalpy` is a default dependency, so the demo runs on a plain install. A `release` workflow
  publishes to PyPI by trusted publishing when a version tag is pushed.

- Ninth held-out web result, Jessline: 125/127 with `v9` and combination coverage under the strict gate;
  verification had no inconclusive checks.

- `web.aria/v9`, the default for new web projects: `focus` names what has focus by role and name, headings
  and landmarks included (`heading:Programme`); `v8` recorded a focused heading as `h2:`. The surface audit
  adds that case (40 pairs).
- Fixed before publication: v9 recorded a focused `<button>` as `generic:` (a role equal to its tag name was
  taken for an unknown element). The surface audit adds focus on a button (41 pairs).
- Discovery explores one row per status value; `retract_rule` reports rules left by status.
- Coverage combines routes with what changes them. For apps with a sign-in, every route is visited signed
  out and signed in, judged by whether the page offers to sign out. When a table has a status column, every
  record route of that kind is visited for at least as many records as there are statuses. `suggest_probes`
  gives the sign-in steps and a `goto` for each. On the eighth held-out round's project it flags exactly what
  the observer missed: the sign-in page while signed in, and locked records' edit pages.

- Fixed: field-probe rows stored a derived `flagged` key that live symbols do not have, so verification
  reported those rows inconclusive instead of testing the clone (16 of the eighth round's 18 inconclusive
  checks). Outcomes now hold only real symbol keys.
- Fixed: released actions whose names carry the codename (`click[link:Old Granary <codename>]`) found nothing
  when replayed on the original; the original now runs each real action under its released name too.

## 0.2.0 (2026-10-23)

Web reimplementation reaches 99.2% and 96.9% of hidden tests on two held-out apps, under the strict gate.

### Highlights

- **`web.aria/v8`**, the default for new web projects. It records everything a user-facing Playwright locator
  or assertion can tell apart:
  - `outline`: the accessibility tree, with roles, names, levels, states, nesting and counts;
  - `properties`: field values (never a password's), required, readonly, masked, error message, sort state,
    progress values and `title` attributes.

  A surface audit (`teardown.drivers.web.surface`) of 39 page pairs, plus 7 implementation-only pairs, keeps
  it that way. `v8` records all 39 and none of the 7; `v7` recorded 17.
- **Observer tooling.**
  - `discover_ui` crawls every screen. Its runs accumulate, one per role or start point.
  - Coverage lists every control, field, endpoint × fault class, data state (tables and named lists), session
    expiry and live output.
  - `suggest_probes` turns each gap into a ready-made next step, and a release is refused until every gap is
    exercised or explained.
  - The observer playbook is served as the `observe_target` MCP prompt.
- **The strict gate, tested end to end.** `tests/test_strict_web.py` covers it automatically: the observer
  works over MCP/HTTP and approvals are typed into a pseudo-terminal. Two live held-out rounds also used it,
  each approved by a person at their own terminal.

### Web observation

- Versioned abstractions. Each project keeps the version it was created with, so released specs keep
  verifying:
  - `v2`: page title, focus, status messages, dialogs, select options and `aria-current`;
  - `v3`: tables and description lists;
  - `v4`: landmark text as text assertions read it;
  - `v5`: CSS-generated text;
  - `v6`: dialog roles and accessible descriptions;
  - `v7`: `aria-invalid`, row headers and named groups;
  - `v8`: the outline and properties described above.
- Fault actions: `{mode: clear}`; `hang`/`release` for pending states. Actions: `back`/`forward`/`reload`,
  plus `within`/`nth` for controls with the same name.
- API paths fold id segments. Discovery and coverage count table-row links once per table.

### Observer

- Field probes:
  - find a minimum length as well as a maximum;
  - read the screen without `submit` (live outputs);
  - count an API 4xx, a dialog left open or an `aria-invalid` field as a refusal;
  - mask echoes;
  - take `accepted_if`.
- Rule checks:
  - reject undefined, empty or inline actions with a clear message, while `click[role:name]` names define
    themselves;
  - nested `null` asserts absence, and `{}` or `[]` mean none.
- Coverage credits a fault only when a recorded call with that method and path was made while it was active.
  A control whose clicks only came back `NA` is not covered.
- `run_sequence` takes `keys`. `propose_claim` lists the valid kinds. `ingest_docs` reports paragraphs the
  corpus already held. Fault suggestions show the observed path next to the contract path.

### Gate

- Strict mode refuses a release until coverage gaps are measured and acknowledged. `teardown review` shows the
  gaps for rules-only drafts too.
- A repeated `teardown approve` says who already approved. Generated unknowns are interface findings.

### Fixes

- Observer-side errors carry their message. Unexpected gate errors come back generic.
- The room images copy the license files and the packaged playbook.

### Results

- Eight held-out web apps, with the tooling frozen per round and both sides confined:
  53% → 56% → 81.5% → 93.1% → 89.8% → 87.5% (`v1`–`v6`, standard gate), then 99.2% and 96.9% (`v8`, strict
  gate).

## 0.1.0 (2026-10-22)

First public release.

### The loop

- **Observe.** The observe MCP server (stdio or HTTP) and the Python API: targets, actions, mappers,
  sequences, field probes, observer-authored rules checked against the original, coverage with unknowns, and
  automata learning (KV / L#).
- **Gate.**
  - Verbatim (suffix automaton) and near-verbatim (winnowing) checks against everything observed and ingested.
  - Real names replaced by a codename; a functional-quote ledger.
  - Strict mode with classified findings and terminal-only approvals (`teardown review`, `approve`, `release`).
- **Rebuild.**
  - Clean-room kits (`teardown export-clean`) for CLI, web and Android targets.
  - A verifier that runs the original and the clone through the same tests and returns abstract verdicts.
- **Audit.** A hash-chained, DSSE-signed in-toto statement log (`teardown audit-verify`).

### Targets

- **CLI (stable).**
  - A locked-down container runner: no network, read-only, unprivileged.
  - Help discovery, probe planning, decision-table claim mining, noise calibration.
  - Stdio and permission faults.
- **Web (stable).**
  - Playwright with a determinism profile; accessibility-tree symbols.
  - Fault injection (5xx, network, timeout, malformed body, held requests).
  - Query-string routes, public-contract selectors, replayed CDN assets, date masking.
  - A value-free API contract and endpoint × fault coverage.
- **Android (working).**
  - adb with an on-device UiAutomation agent; network-off fault.
  - Gradle-free clone builds (`android:kit`).
- **Linux desktop (experimental).** Xvfb + AT-SPI in a container.

### Enforced rooms

- `teardown cleanroom`: the implementer sees only the kit; egress goes only to the gate and the model API.
- `teardown observerroom`: the observer reaches the target only through the observe MCP server.
- An allowlisting egress proxy with a per-attempt log, and isolation probes (`check`).

### Results

All results were scored on hidden suites with pinned denominators (see `docs/evaluation.md`):

- novel CLI tool: 397/397;
- novel Android app, both sides confined: 113/118;
- RealWorld Conduit: 99/101 (development set);
- `jq`: 394/429, with the contamination lesson.
