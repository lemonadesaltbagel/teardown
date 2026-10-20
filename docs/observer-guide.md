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
