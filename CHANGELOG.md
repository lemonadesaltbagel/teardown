# Changelog

## Unreleased

### Observer productivity

- `discover_ui`: a bounded crawl that clicks every enabled control and fills forms. Screens are identified by
  route, headings, controls and enablement, and pages that differ only in data are explored once.
- UI coverage from discovery (every control and field), plus endpoint × fault coverage.
- `suggest_probes`: gaps become ready-made fault actions with a path that triggers them, field-probe
  arguments, and click paths.
- The observer playbook (`docs/observer-playbook.md`), served as the `observe_target` MCP prompt.

### Web observation

- `web.aria/v3`: `tables` (name, columns, rows) and `definitions`
  (description lists).
- `web.aria/v2`. It adds page title, focus, status messages, dialogs, select
  options, `aria-current`, and table cells, and undoes Playwright's YAML quoting for names with `#` or `:`.
  `web.aria/v1` is unchanged, so existing specs keep verifying.

### Fixes

- UI coverage counts only actions a probe or rule runs.
- Coverage resolves its own gap unknowns once covered.
- Observer-side errors carry their message.
- The room images copy the license files and the packaged playbook.

### Results

- First held-out web result, Kilnroll: 64/120 with the frozen tooling. The misses are what `v2` now records
  (`research/15`).
- Second held-out web result, Kilnshare: 73/131 with `v2`. No misses in what `v2` added; 54 were table
  structure, which `v3` records (`research/16`).
- Third held-out web result, Lockline: 106/130 with `v3` (`research/17`).
- `web.aria/v4`: landmark text as text assertions read it.
- Releases need coverage gaps exercised, explained or accepted with a reason; strict mode gates every draft on
  measured coverage.
- Fourth held-out web result, Scionry: 121/130 with `v4` (`research/18`).
- `web.aria/v5`: CSS-generated text (`generated`).
- Coverage lists data states per table (none, one, several) and session expiry for apps with a sign-in.
- Fifth held-out web result, Wickward: 114/127 with `v5` (`research/19`).
- Nested subset expectations need their keys; `fault {mode: clear}` removes injected faults.
- Field probes read status messages and mask echoes in the length search; generated unknowns are interface
  findings.
- Table-row links count as one representative per table in discovery and coverage. API paths fold id
  segments. `within`/`nth` handle same-named controls.
- Discovery no longer fails on off-screen controls or selects; `back`/`forward`/`reload` actions; rule checks
  reject undefined actions.
- `web.aria/v6`: dialog roles and accessible descriptions.
- Sixth held-out web result, Fogline: 112/128 with `v6` (`research/20`).
- Seventh held-out web result, Strewnfield: 129/130 with `v8` under the strict gate, a person approving at a
  terminal (`research/21`).
- Eighth held-out web result, Belfry: 126/130 with `v8` under the strict gate (`research/22`).
- `discover_ui` runs accumulate instead of replacing the inventory. Fault suggestions show the observed path
  next to the contract path. `propose_claim` lists the valid kinds; `run_sequence` takes `keys`.
- Field probes find a minimum length before the maximum, and count an API 4xx, a dialog left open or an
  `aria-invalid` field as a refusal. Named lists get data-state coverage. An expected `{}` means none. Controls
  whose clicks only came back `NA` are not covered. `click[role:name]` names define themselves. A repeated
  `approve` says who already approved.
- `web.aria/v8`, the default for new web projects: `outline` (the accessibility tree: roles, names, levels,
  states, nesting, counts) and `properties` (field values except passwords, required, readonly, masked, error
  message, sort state, progress values, title attributes). A surface audit
  (`teardown.drivers.web.surface`) lists every difference a user-facing Playwright locator or assertion can
  see. v8 records all 39 and none of 7 implementation-only differences; v7 recorded 17.
- `teardown review` lists coverage gaps for rules-only drafts too; before, it showed none while release
  refused them. Found by a new end-to-end strict test (`tests/test_strict_web.py`): the observer works through
  MCP over HTTP only, and the person approves in a real pseudo-terminal.
- Live outputs: discovery marks fields whose typing changes the screen without a click (previews, totals,
  counters); coverage lists each as `live output` until the screen is recorded right after typing three
  different values; `probe_web_field` reads the screen without `submit`, and `suggest_probes` proposes it.
- `web.aria/v7`: an `invalid` control flag for `aria-invalid`, `row_headers`
  per table, and `groups` (named groups, radiogroups and toolbars with their controls).
- Fault coverage counts an item only when a recorded observation shows that method and path called while a
  matching fault was active. Before, a fault on a GET also covered a POST to the same path.
- Rule checks reject inline action objects with a clear message; nested `null` in an expectation asserts
  absence; `ingest_docs` reports paragraphs already in the corpus.

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
