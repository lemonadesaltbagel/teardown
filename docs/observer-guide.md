# Observer guide (CLI targets)

You are the **observer** (dirty side). Your job is to produce a behavioral specification good enough for a separate
implementer to rebuild the tool **without seeing it**. You may run the tool black-box through Teardown, read its
`--help`, and read public documentation. You must never read its source code, decompile it, or look at any hidden test
suite.

The implementer gets only what you release: probes with observed outcomes, claims, **rules**, interface structure and
unknowns. In the uncontaminated benchmark, an implementer with the author's manual beat one with a probe table alone
(97% vs 85%): **examples alone are not a spec.** Rules carry the generalizations; probes and checks back them.

## Python API (same operations as the `teardown-observe` MCP server)

```python
from teardown.project import Project
p = Project("/path/to/project")                      # a codenamed directory, never the product's real name
p.open_target("cli:docker:<image>", purpose="research", real_names=["<product name>"])
p.ingest_docs("manual", open("MANUAL.md").read())   # docs join the gate corpus: copied wording gets flagged
d = p.discover_cli("<cmd>")                          # interface structure from --help, confirmed by behavior
p.probe_cli("<feature>", hints, discovery=d)         # sweep + pairwise + mutations + designed probes + noise + mining
p.check_rules("<feature>", rules)                    # your rules, checked against the original
p.coverage("<feature>", inventory)                   # what is still unexercised -> unknowns
draft = p.compile_spec("<feature>"); p.review_spec(draft.id); p.release_spec(draft.id)
```

### `hints` for `probe_cli` (all optional except `cmd`)

| key | meaning |
|---|---|
| `base` | argv that makes the tool do its main job (probes vary one factor around it) |
| `default_input`, `sweep_inputs`, `inputs`, `pair_inputs` | names of input fixtures (`extra_inputs`) used by the sweeps |
| `extra_inputs` | `{name: text}` fixtures; use **many** small ones covering the input format's features |
| `option_values` | `{"-x": {class: value}}` value classes per option; the most important hint |
| `mutation_lines` | `{name: line}` lines inserted at start/middle/end of the default input (comment-like, header-like, escapes, odd field counts) |
| `mutation_argv` | argv variants the input mutations run with |
| `extra_argv` | `{case: argv}` designed probes (orderings, combinations, edge cases) |
| `operand_type`, `operand_forms`, `operand_options` | positional-operand sweeps |
| `skip_options` | options not to probe (interactive, network, …) |
| `stdio_modes`, `file_faults` | on by default: closed/full stdout, closed stdin; an unreadable input file, alone and before a readable one |

Any invocation (rule sides, designed probes) can seed permission faults with `file_modes`:
`{"argv": [...], "files": {"in.txt": "...", "out/keep": ""}, "file_modes": {"in.txt": "000", "out": "555"}}`
(unreadable file, read-only directory). The program runs unprivileged, so the modes bite; they are the starting
state, so only the program's own changes show up as file effects.

### Rules for `check_rules`

```python
{"statement": "Lines whose first character is '#' are ignored.",   # your own words, never copied
 "origin": "documented",          # documented | inferred-intent | observed
 "kind": "invariant",             # invariant | refusal | default | ordering | ...
 "checks": [
   {"kind": "same", "a": {"argv": ["tool"], "stdin": "x\n"}, "b": {"argv": ["tool"], "stdin": "# c\nx\n"}},
   {"kind": "outcome", "a": {"argv": ["tool", "-n", "abc"]}, "expect": {"exit": 2, "diagnostic": True}},
   {"kind": "differs", "a": {...}, "b": {...}, "keys": ["stdout"]}]}
```

- An invocation is `{argv, stdin, files: {name: text}, env, stdin_mode, stdout_mode}`; `argv[0]` is the command.
- `outcome` expects a **subset** of the behavior symbol: `exit`, `stdout` (exact), `diagnostic` (stderr non-empty),
  `errno`, `fs` (file effects). Diagnostic wording is never part of a symbol.
- `same`/`differs` compare two invocations (optionally only `keys`): metamorphic checks are the strongest way to
  state a rule ("the order of X does not matter", "adding a comment line changes nothing").
- Give each rule **several** checks over different inputs; a rule with one check is an example, not a rule.
- A documented rule that the tool contradicts is reported as a documentation/behavior conflict; that is valuable.

## What a good spec covers (use `coverage` with an inventory built from the help and docs)

1. **Input format**: every syntactic feature (comments, headers, separators, escapes, quoting, blank lines, encodings,
   field-count mismatches), each with rules and mutation probes.
2. **Every option**: value classes (valid, boundary, invalid), interactions and ordering.
3. **Any embedded language**: every operator (precedence, associativity, types, errors), every function (arguments,
   edge values, void/null handling), literals and syntax errors.
4. **Output**: every format, with edge content (empty, unicode, separators inside values, very long values).
5. **Errors**: each exit-code class, and **which error wins** when several apply.
6. **Files**: every output/side-effect file, its content and when it is (not) written.

Release only when `coverage` reports no uncovered inventory items, or record why as unknowns.

## UI targets: start with discovery

For web, Android and desktop targets, follow [observer-playbook.md](observer-playbook.md) (also served as the
`observe_target` MCP prompt).

- `discover_ui(feature, start=[...])` crawls the app and defines `click[role:name]` and `fill[name]=sample`
  actions. It records every screen and the path that reaches it.
- `coverage` then lists every discovered control and field.
- `suggest_probes(feature)` turns the gaps into ready-made next steps.

## Web targets

```python
from teardown.drivers.web.driver import LocalSite          # or any URL you are allowed to observe
p.open_target("web:http://127.0.0.1:4200/", purpose="research", real_names=["<product>"],
              target_options={"reset_command": ["<restore backend state>"], "reset_check_url": "<GET that must not change>"})
p.define_actions({"open_signup": {"op": "click", "role": "link", "name": "Sign up"},
                  "fill_email": {"op": "fill", "role": "textbox", "name": "Email", "value": "a@b.co"}, ...})
s = p.session(); outputs, evidence, _ = s.run(["open_signup", "fill_email", ...])   # symbols per step
p.probe_web_field("signup", prefix=[...], role="textbox", name="Email", submit="submit", kind="email")
p.check_rules("signup", [{"statement": "...", "checks": [{"kind": "same", "a": {"actions": [...]},
                                                          "b": {"actions": [...]}, "keys": ["controls"]}]}])
p.learn("signup", alphabet=[...], walks_per_state=100, walk_len=20)   # state machine of a flow (KV/L#)
p.api_contract()                                                       # value-free backend contract (in the spec)
```

- Actions address elements by **ARIA role and accessible name** only.
  - **Fields:** `op` is one of click, fill, check, uncheck, select, press, goto, back, forward, reload, fault.
    `value` holds the typed text, the selected option, the key, or (for `goto`) the root-relative URL.
  - **Same-named controls** (a page button and a dialog's confirm button): `within: {"role": "dialog",
    "name": ...}` scopes the lookup, and `nth` picks one among several matches.
  - **Outcomes:** a missing element, or one a user could not act on, makes the step `NA`; a disabled one makes
    it `DISABLED`. An outcome check expects these as `{"value": "NA"}` / `{"value": "DISABLED"}`.
- **A symbol is the structured accessibility view** (`web.aria/v6`, the default for new projects):
  - `path`, `title`, `headings`, `alerts`;
  - `status` (live-region messages such as "Saved.");
  - `text`;
  - `tables` (each table's name, columns and rows of cells);
  - `definitions` (description-list term/definition pairs);
  - `controls` (role:name → state flags, including `current` for `aria-current`; textbox values reduced to
    filled/empty);
  - `options` (each combobox's options, the selected one marked);
  - `dialogs`, `focus` (role:name of the focused element), `invalid`;
  - `network` (API method, path template, status);
  - `landmarks`: the banner, footer, navigation, complementary, search, and named regions/forms, each with its
    text as a text assertion reads it (inline text joins with spaces, blocks do not), so layout that splits or
    joins text is visible;
  - `generated`: text CSS inserts with `::before`/`::after` (icons, separators), one `before|text|after` entry
    per element. Accessible names include it; element text does not;
  - `descriptions`: each control's accessible description (`aria-describedby` / `aria-description`); `dialogs`
    entries carry the role (`alertdialog:Remove …` vs `dialog:…`).

  Projects keep the version they were created with (`v1`: no title, focus, status or tables; `v2`: table cells
  flattened into `text`; `v3`: no landmarks; `v4`: no `generated`; `v5`: dialogs without roles, no
  `descriptions`).
- Rules on UIs compare **sequences**: `{"actions": [...]}` on each side; restrict `keys` to what the rule is about
  (`controls`, `path`, `alerts`, `network`) so incidental text does not break the relation.
- Field probes find length limits and classify refusals as client-side (submit disabled / no request) or
  server-side (API 4xx).
- A shared self-hosted backend means episodes run one at a time; give each run a fresh reset.
- `api_contract()` is released with the spec: endpoints, statuses and body *shapes* (no values). Query values are
  dropped; fold data-bearing path segments with `target_options={"api_templates": ["/api/articles/feed",
  "/api/articles/{slug}", ...]}` (first match wins, so list literal paths first).
- An unknown you have since answered: `p.update_unknown(id, "resolved" | "out-of-scope" | "investigating", note)`.
  Resolved ones leave the release; the audit log keeps the history.
- Inventory for `coverage`: pages/routes, every form and field, every button/link action, every API endpoint.
- **Fault injection** (error handling is invisible on a healthy backend): an action
  `{"op": "fault", "fault": {"path": "/api/articles/*", "mode": "status|abort|timeout|malformed", "status": 500}}`
  (`{"mode": "clear"}` removes the faults installed so far, e.g. to sign in again after an injected 401)
  (`*` stays within one path segment: that pattern hits an article but not its comments; `**` crosses segments)
  makes matching API calls *as received by the observing browser* fail for the rest of the episode; put it before
  the steps that trigger the call and state rules about what the UI then shows. Cover every important endpoint with
  5xx, network failure and malformed-body probes. The server is never touched. `coverage` lists every observed
  endpoint × fault class (5xx, network, malformed) automatically, plus each table's data states (none, one,
  several) and, for apps with a sign-in, session expiry (a 401 fault). An item counts as covered only when a recorded
  probe or rule observation shows that call (same method and path) made while a matching fault was active, so a
  fault on a GET does not cover a POST to the same path. Uncovered items become unknowns.
- **Absence**: inside a nested expectation `null` means "must not be there":
  `{"controls": {"button:Delete": null}}` holds only when no Delete button exists.
- **Pending states**: `"mode": "hang"` holds matching calls unanswered, so the next observation shows the loading
  UI (placeholders, disabled buttons). A later `{"op": "fault", "fault": {"mode": "release", "then":
  "continue|abort|timeout|status", "status": 500}}` answers them and removes the hang.
- **Public markup contracts**: when the product publishes one (a selectors document for compatible frontends),
  pass `target_options={"contract_selectors": {"source": "<the public document>", "selectors": [...]}}`. Each
  observation then carries `contract`: per selector `absent | hidden | empty | content`. This sees structure the
  accessibility view omits (elements with no accessible content). Use only selectors the public document names;
  state rules on the `contract` key.
- **Third-party assets**: hosts other than the target's are blocked (determinism, and no outside service learns what
  is observed). If the app's layout depends on a CDN stylesheet or icon font, observations differ from a real
  deployment (icons with zero size, for instance). Name those hosts in
  `target_options={"profile": {"asset_hosts": ["<cdn host>"]}}`: their stylesheets, fonts and images are fetched
  once per process and replayed; scripts and API calls to them stay blocked. Icon fonts put their private-use
  glyphs into accessible names (a button named "\uf141 Favorite"). That is what users' assistive technology
  gets from the real app, so observe it that way rather than leaving the font out. `p.blocked_hosts([actions])` lists
  what an episode tried to load from blocked hosts (host + resource type).
- **Clock-dependent text**: dates rendered from server timestamps (creation times) change between observation and
  verification days. Use `p.set_mapper(params={"mask_dates": True})` before probing when the app shows them;
  `compile_spec` records an unknown if expected text contains dates while they are not masked.
- Route and network symbols include query strings (`/?feed=following`, `GET /api/articles?limit=10&offset=0`):
  state rules about pagination and filters through them.

## Android targets

```python
p.open_target("android:emulator-5554:com.example.app", purpose="research", real_names=["<app name>"])
p.define_actions({"amount": {"action": "fill", "role": "textbox", "name": "Amount", "value": "80"},
                  "go": {"action": "click", "role": "button", "name": "Calculate"},
                  "offline": {"action": "network", "value": "off"},     # airplane mode, restored at reset
                  "back": {"action": "back"}})
p.probe_web_field("calc", prefix=[...], role="textbox", name="Amount", submit="go", kind="number")  # any UI target
```

- **Episodes.** Every episode starts from cleared app data and a cold launch. Steps address elements by
  accessibility role and name: the text, or the content description for fields and icon buttons.
- **Actions.** `click`, `fill`, `longclick`, `key` (a keycode), `back`, `network` (`off` | `on`).
- **Symbols** (`android.a11y/v1`):
  - `controls`: role:name → flags, i.e. `disabled`, `checked`, `selected`, `focused`, and `filled` | `empty` for
    text fields;
  - `text`: visible text;
  - `system`: system dialogs.
- **Not observed.** Resource ids and activity names are never part of observations.
- **Fields whose accepted values change the result** (a calculator's total): pass `accepted_if`, e.g.
  `{"text_contains": "total"}` or `{"subset": {"controls": {"button:Add": []}}}`, so each class is judged by
  what acceptance looks like, not by equality with the known-good value's outcome. Number fields skip the length
  search; probe their ranges with classes (`min`, `max`, `over`, ...).
- **The soft keyboard** can take the first Back. If Back matters in a flow, observe what it does both with and
  without the keyboard open.
- **Coverage inventory:** screens, every field and its validation, every button and toggle, list behavior (caps,
  removal, ordering), what persists across screens and what resets, and the app's behavior with the network off
  if it uses the network.
