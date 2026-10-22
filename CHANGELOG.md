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

- `web.aria/v3`, the default for new web projects: `tables` (name, columns, rows) and `definitions`
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
- Discovery no longer fails on off-screen controls or selects; `back`/`forward`/`reload` actions; rule checks
  reject undefined actions.

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
