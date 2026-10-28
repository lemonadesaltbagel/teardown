# Changelog

## Unreleased

## 0.3.0 (2026-10-28)

Highlights:

- **Real applications.** Observation holds up on an app many times larger than the benchmark ones (Flipt):
  long calls have time budgets and progress, faults can change a response (`patch`, for server modes), a
  `request` action seeds records so deep screens are reachable, hash routes and clocks are handled
  (`web.aria/v10`), and settling no longer misses short-lived notifications. Results: 9 → 19 of 55 on Flipt's own
  suite over four rounds (development set).
- **Faster, sturdier verification.** The original's runs are cached per release, `verify --only-failed` re-runs
  only what failed, one verification runs at a time, and a call the gate fails does not spend budget. A crashed
  Android emulator is restarted.
- **A clearer strict gate.** Coverage lists server modes and faults that met no call, the reviewer sees the
  observer's explanation next to each gap, and the clean side sees the gate's own error messages.
- **Installable on its own** as `teardown-cleanroom` (the name "teardown" is not available on PyPI; the command
  and the import package stay `teardown`), with `install-browser`, `install-android-agent`, room images built from the files
  the wheel carries, `teardown api-proxy` for backends that share the UI's port, and a release workflow for
  PyPI.

Details:

- `teardown api-proxy` puts an API-only front before a target that serves its UI and API on one port, so the
  clean side can call the backend without being able to fetch the original's frontend. `cleanroom check` says
  so when the kit's API points at the original's port.

- A web name pattern drops Python-only leading flags such as `(?i)` (patterns run as JavaScript and already
  ignore case), and other Python-only syntax is refused when the action is defined instead of crashing an
  episode. `compile_spec` judges the coverage gaps as they are now.

- Web settling no longer trusts a running count of requests: a request whose finishing event never arrived
  (cancelled by a navigation) kept every later observation waiting for the whole settle timeout, so a
  notification shown for three seconds was gone by the time the page was read. On Flipt this hid every
  "Successfully created" message from the third round's spec; observations after an action now take about 0.1
  seconds there instead of 3.

- Actions that discovery generates for names with masked parts ("Created <ago>") match the element's real name
  (a pattern with those parts open); they used to match nothing. A `hang` fault counts as met when the call it
  holds was made (held calls are recorded apart from `network`, so no symbol changes).

- A `request` web action makes one API call as setup (with the browser's cookies, not counted as UI traffic), so
  a sequence can create the records a deep screen needs in one step instead of minutes of UI. Verification runs
  it against the same backend for the clone. On Flipt the observer did not reach the rule and rollout editors,
  which need a flag with variants and a segment built first, and those were most of the remaining misses.

- Results: Flipt (development set) on its own UI suite over four rounds: 9, 17, 11 (observations missed
  short-lived notifications: the settling bug above), then 19/55, with the clone passing 163 of 164 conformance
  tests.

- The gate runs one verification at a time (a second call waits its turn), and a call the gate itself could
  not finish (the original went away mid-episode) does not count against the budget. On Flipt, the
  implementer's client gave up on a long first call and started a second one; both ran on the one original,
  whose resets broke the other's episodes.

- A `clear_storage` web action makes the visit a first one (cookies and web storage cleared, faults kept):
  an app that remembers a session in web storage makes some calls only on a first visit, and `[fault,
  clear_storage, reload]` now reaches them. `v10` with `mask_dates` masks dates and times in control names,
  `properties` (keys and values), focus and flagged names too, so a switch labelled with the live clock or a
  "Created 3 seconds ago" title stays stable. Coverage resolves gap unknowns for items that no longer exist (a
  literal path before `api_templates` named it). The observer docs' examples no longer name a benchmark target's
  own mode.

- Server modes in coverage: each boolean field (outside lists) of a resource without path parameters, such as the
  app's configuration, is a `mode GET <path> <field>` item, covered by a `patch` fault that sets it, and
  `suggest_probes` gives that fault. `check_rules` lists `faults_not_met`, faults no call of the sequence matched
  (they test nothing). `teardown review` and `teardown approve --coverage` show the observer's explanation next to
  each gap, unexplained gaps first. `v10` with `mask_dates` also masks numeric dates (`10/26/2026`, not versions
  like `1.6.10`) and times in table cells. Fixed: the calls a rule check made (kept for coverage) were released in
  the spec and came back from the gate as prose findings.

- Fault coverage credits every API call a rule's sequence made, at every step: an observation's `network` holds
  only the calls since the previous step, so a fault met while a page loaded used to go uncredited. `v10` takes
  `mask_patterns` (the observer's own regular expressions, masked everywhere text appears). Over MCP,
  `check_rules` and `discover_ui` cap the budget an observer asks for below a 300-second client timeout.

- A crashed Android emulator is restarted: the driver remembers its AVD (or takes
  `target_options["emulator"]`), checks the device before every episode and brings it back on the same port. An
  episode the device died in raises `DeviceLost` instead of reporting an empty screen, and verification re-runs
  that episode once. In the second held-out Android round the emulator crashed during the implementer's first
  verify, and every later call failed.

- Faster verification on large targets: the original's runs are cached per release (each call re-checks a rotating
  sample, and any difference drops the cache), so later calls run the clone alone; `verify --only-failed` re-runs
  just the tests the build did not pass last time. On Flipt one full call took 45 minutes, two thirds of it
  re-observing the unchanged original.

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
