# Changelog

## Unreleased

- `web.aria/v9`, the default for new web projects: `focus` names what has focus by role and name, headings
  and landmarks included (`heading:Programme`); `v8` recorded a focused heading as `h2:`. The surface audit
  adds that case (40 pairs).
- Coverage combines routes with what changes them. For apps with a sign-in, every route is visited signed
  out and signed in, judged by whether the page offers to sign out. When a table has a status column, every
  record route of that kind is visited for at least as many records as there are statuses. `suggest_probes`
  gives the sign-in steps and a `goto` for each. On the eighth held-out round's project it flags exactly what
  the observer missed: the sign-in page while signed in, and locked records' edit pages.

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
  gate) (`research/15`–`22`).

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
