# Observer playbook

A loop for the dirty side's agent: discover what the app has, exercise all of it, and close every coverage gap,
either with a probe or rule or with a recorded reason. The tool names are the observe MCP server's.
`observer-guide.md` has the details of each tool.

## 0. Open the target (2 minutes)

- `open_target` with:
  - the purpose;
  - the app's real names in `real_names`;
  - for a self-hosted backend: `target_options.reset_command` and `reset_check_url`.
- Web:
  - run `blocked_hosts()`; add stylesheet, font and image hosts the layout depends on to
    `target_options.profile.asset_hosts`, then reopen;
  - if the app shows dates from a server clock, run `set_mapper(params={"mask_dates": true})`.

## 1. Discover (5 minutes)

- `discover_ui(feature)`. For screens behind a sign-in, define the sign-in actions and run it again with
  `start=[...]`.
- Read the screens: route, headings, clickable controls, fields, and the controls that only enable once a form is
  filled.
- `coverage(feature, inventory)` adds your own items:
  - documented features;
  - list behaviors;
  - settings;
  - for web, the API endpoints (added automatically, together with every endpoint × fault class).

## 2. Probe every field (25% of the time)

- `probe_web_field` for each field, using the `prefix` and `submit` that `suggest_probes` proposes.
- Use classes that match the field: ranges as `min`, `max`, `over`, `under`; formats; empty; whitespace.
- When accepted values change the result, pass `accepted_if` (`text_contains` or a `subset`).
- Note each refusal message and its order. When several inputs are invalid, which message wins?
- **Live outputs** (previews, totals, counters that change while you type): discovery marks their fields, and
  coverage lists each as `live output`. Probe them **without** `submit`, so the screen is read right after
  typing an empty, out-of-range or malformed value.

## 3. Faults (15% of the time)

- **Web:** for every endpoint and fault class (5xx, network, malformed), state what the UI shows. Include the
  calls made at start-up: put the fault action first, then navigate. Use `hang` and `release` for loading and
  disabled states.
- **Android:** `network` off when the app uses the network.

## 4. Rules (40% of the time)

State them in your own words, with checks:

- **Navigation and guards:** where each control leads; what happens without a session.
- **State:** what persists across screens and reloads; what resets, and which action resets it.
- **Enablement:** which controls are disabled until which input.
- **Lists:** adding, removing, caps, ordering, duplicates, totals.
- **Derived values:** formulas checked at several points, including boundaries and rounding, and with inputs
  out of range or unfinished: what replaces the value then?
- **Defaults:** what an empty input means.
- **Keyboard:** the order Tab moves focus through a page (`press` Tab, then check `focus`); what Enter does
  in a field; whether filters and searches react while you type or only when you submit.
- **Every route, including the unhappy ones:** a missing record's page, empty results, and pages that a role
  may not see. Use `goto` with a made-up id.
- **Data states:** every list with no rows, exactly one row (singular wording such as "1 item"), and several.
  Coverage lists these per table.
- **Sessions:** what a signed-in user sees when a request comes back 401 (an expired session): the message,
  and where they are sent.
- **Roles:** sign in as each role on the same pages and compare which controls exist (`same`/`differs` on
  `controls`).
- **Every form submitted empty**, sign-in included: which messages appear, where, and where focus goes.
- **Values with spaces and special characters** in searches and filters: what the URL shows (`%20` or `+`).
- **History:** after leaving a filtered list and coming back (a link back, and `back`), are the filters and
  page kept? Do status messages clear on navigation?

Prefer `same`/`differs` checks for relations and `outcome` checks with small subsets for facts.

## 5. Close the loop (repeat until done)

- `coverage(feature)`, then `suggest_probes(feature)`. Act on each suggestion, or record why not:
  `update_unknown(id, "out-of-scope", reason)` or `record_unknown`.
- Retract superseded rules (`list_rules`, `retract_rule`).
- Stop when every uncovered item is either exercised or explained. `release_spec` refuses while measured items
  are neither. Use `accept_gaps` only with a real reason; it is recorded.

## 6. Release

- `compile_spec` and `review_spec`. Rewrite any prose finding, and never paste the app's text into statements.
- `release_spec`. In strict mode, ask the person running the gate to approve.
