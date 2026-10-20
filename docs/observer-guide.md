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

- Actions address elements by **ARIA role and accessible name** only; values are what you type. A missing element
  makes the step `NA`; a disabled one `DISABLED`.
- A symbol is the structured accessibility view: `path`, `headings`, `alerts`, `text`, `controls` (role:name →
  state flags; textbox values reduced to filled/empty), `invalid`, `network` (API method, path template, status).
- Rules on UIs compare **sequences**: `{"actions": [...]}` on each side; restrict `keys` to what the rule is about
  (`controls`, `path`, `alerts`, `network`) so incidental text does not break the relation.
- Field probes find length limits and classify refusals as client-side (submit disabled / no request) or
  server-side (API 4xx).
- A shared self-hosted backend means episodes run one at a time; give each run a fresh reset.
- `api_contract()` is released with the spec: endpoints, statuses and body *shapes* (no values).
- Inventory for `coverage`: pages/routes, every form and field, every button/link action, every API endpoint.
- **Fault injection** (error handling is invisible on a healthy backend): an action
  `{"op": "fault", "fault": {"path": "/api/articles*", "mode": "status|abort|timeout|malformed", "status": 500}}`
  makes matching API calls *as received by the observing browser* fail for the rest of the episode; put it before
  the steps that trigger the call and state rules about what the UI then shows. Cover every important endpoint with
  5xx, network failure and malformed-body probes. The server is never touched.
- **Pending states**: `"mode": "hang"` holds matching calls unanswered, so the next observation shows the loading
  UI (placeholders, disabled buttons). A later `{"op": "fault", "fault": {"mode": "release", "then":
  "continue|abort|timeout|status", "status": 500}}` answers them and removes the hang.
- **Public markup contracts**: when the product publishes one (a selectors document for compatible frontends),
  pass `target_options={"contract_selectors": {"source": "<the public document>", "selectors": [...]}}`. Each
  observation then carries `contract`: per selector `absent | hidden | empty | content`. This sees structure the
  accessibility view omits (elements with no accessible content). Use only selectors the public document names;
  state rules on the `contract` key.
- Route and network symbols include query strings (`/?feed=following`, `GET /api/articles?limit=10&offset=0`):
  state rules about pagination and filters through them.
