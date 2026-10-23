# The strict gate (one developer)

Open a project with `strict=True` (`open_target(..., strict=True)`). From then on nothing reaches the clean side
until a person has decided on every gate finding and every coverage gap. The observer agent can prepare a release;
it cannot approve one.

## The loop

```bash
teardown review  --project P --feature F            # findings by class, approvals, coverage gaps
teardown approve --project P --feature F --by you@example.com --class interface       --reason accessibility-name
teardown approve --project P --feature F --by you@example.com --class expected-output --reason test-oracle
teardown approve --project P --feature F --by you@example.com --finding fnd_... --reason user-required
teardown approve --project P --feature F --by you@example.com --coverage --note "why these gaps are acceptable"
teardown release --project P --feature F
teardown audit-verify --project P
```

Each `approve` shows what it covers and asks you to type the project's codename. It refuses to run without an
interactive terminal.

## In practice

In the seventh held-out round (`research/21`) one person ran the gate on a real web spec of 64 rules and 94
probe rows:

- The observer was told it could not approve. It rewrote every statement the gate flagged as prose, so no
  prose finding reached the person.
- The person made three decisions: the expected-output class (180 findings) as `test-oracle`, the interface
  class (11 action names) as `accessibility-name`, and the three coverage gaps with a note. Then one
  `teardown release`.
- Approvals are content-addressed. Running the same `approve` again records nothing new and says who already
  approved.

Ask the observer to finish with `compile_spec`, `review_spec` and prose rewrites before it stops: that is what
keeps the review to a few class-level decisions. `tests/test_strict_web.py` runs this whole loop automatically,
with approvals typed into a pseudo-terminal.

## Finding classes

| class | where | typical content | approval |
|---|---|---|---|
| `expected-output` | probe rows, rule-check expectations/observations, model outputs | UI labels, messages, output the clone must reproduce | the whole class at once |
| `interface` | action names and values, API paths, contract selectors | accessible names, argv values, routes | the whole class at once |
| `prose` | rule statements, claims, unknowns, anything unclassified | the observer's own sentences | one finding at a time, or rewrite |

Expected outputs and interface names are functional: a conforming clone has to reproduce them. Prose is where
expression leaks without functional need, so a class approval never covers it.

- Approvals are content-addressed records in the project's gate config.
- A finding keeps its id across re-reviews (kind, class and matched text), so approving it once survives
  recompiles. Text that changes is a new finding.
- Coverage acknowledgements name the exact gaps. A new gap blocks again.
- Every approval, acknowledgement and release is an audit statement, signed with the project's key when one exists.

## What the gate does and does not protect against

- **It stops** an agent from approving its own leaks through the tools it is given. The observe MCP server has no
  approval tool in strict mode. `release_spec` accepts no approver. `teardown approve` needs a terminal and a typed
  confirmation.
- **It records** every decision, with who made it and why, in a hash chain that `audit-verify` checks.
- **It is not a sandbox.** An agent with unrestricted shell access to the dirty project, running as you, could
  edit files or fake a terminal. Give the observer agent the MCP server, not a shell on the project. If it needs a
  shell, run it under a different user or in a container that mounts the project read-only except through the
  MCP server.
