# Experiment: uncontaminated benchmark, a novel CLI (`quill`)

*2026-10-20. Kits are local in `.teardown/cleanroom/{cobalt-tundra,docs-arm}`; the tool and its hidden suite are in `.teardown/novel/inventor/`.*

## Why this experiment

The jq experiment could not measure what the spec contributes: the implementer model already knows jq, and memory alone scored 92.5% on jq's own tests (`research/09`).

This experiment removes that confound:
- A separate inventor agent wrote a new tool that no model has seen.
- It wrote the tool's manual.
- It wrote a 398-case hidden suite, in the style of a real project's test suite.

The tool, `quill`, is a pipe-ledger record processor:
- 1,625 lines of Python;
- its own 11-level expression language with 24 functions;
- 8 stages, 4 output formats, and exit codes 0–6.

## Arms

All three agents ran on the same model under the same rules: Python 3.12 standard library only, a bounded effort, no network, and instruction-based isolation.

| Arm | Input | Oracle during development |
|---|---|---|
| **Spec** (Teardown) | The released spec: 470 probes, 94 mined claims, interface structure, 4 unknowns. Codenamed. | `verify.sh` (abstract verdicts) |
| **Docs** | The 713-line author-written manual | none |

**How the Teardown spec was made.** The observer wrote probe hints from `--help` and the manual. It never saw the source or the tests. The pipeline then ran discovery, the sweep, pairwise, designed probes, noise checks and mining in 32 s.

## Results (hidden suite, 398 cases; the original scores 398/398 under the harness)

| Arm | Passed | Rate | Failure kinds |
|---|---|---|---|
| Spec arm (1,500 lines, 1 verify call, 470/470 conformance) | 337 | **84.7%** | exit 29, stdout 48, diagnostic 28, file 12 |
| Docs arm (2,000 lines) | 386 | **97.0%** | exit 2, stdout 1, file 9 |
| Union (passes in at least one) | 389 | 97.7% | — |

The two arms fail on nearly disjoint cases: 9 fail in both, 52 only in the spec arm, 3 only in the docs arm.

**Spec-arm failures** are spread across rules that the probes never exercised:
- input-format edges: escape sequences, header de-duplication, headerless positional fields, multi-file headers;
- void semantics in comparisons and functions;
- output formats with unusual content (grid/kv escaping and quoting);
- the ordering of error classes.

The implementer said so itself. It named "comment/blank lines alone, short rows, kv/card values with spaces, empty input × stages, error-class ordering" as unprobed.

**Docs-arm failures** are concentrated in the `--reject` file (8 of 12) and two derive-spec error classes. These are places where the manual is vague, and where Teardown's observed behavior was exact: the spec arm passed those cases.

## What this means (decision-relevant)

1. **A probe table is a weaker spec than a good manual.** The spec arm had to *induce* rules from 470 examples. The docs arm was *told* the rules.
   - The jq run hid this, because memory supplied the rules.
   - **Behavior-first alone, at this probe budget and with mined decision-table claims only, is not enough** for a tool with a rich language.
2. **Probes are authoritative where documentation is vague.** Teardown was right exactly where the manual was ambiguous (`--reject`, derive-spec errors). Together the two reach 97.7%.
3. **Most of the gap is fixable on the observer side, and that is where the product work goes:**
   - **Observer-authored rule claims.** The observer understood the tool well enough to write good hints. It should also state *rules* in its own words ("lines starting with `#` are comments", "void compares equal to void", "`%` is floored"), each backed by targeted probes and falsified automatically.
     - The mined claims ("class X of option Y is refused") are too shallow to carry a language.
     - This is also the classic clean-room spec form: rules written by the observer, never copied from the original's prose.
   - **Coverage measurement before release.** Build a feature inventory from `--help` (options, formats, modes) plus any public documentation (sections, functions, documented edge cases). Every item needs probes, and a gap blocks the release or becomes an explicit unknown.
     - This would have flagged escapes, header de-duplication, kv quoting and error ordering.
   - **Input-space coverage.** Expressions were probed on only two inputs. Crossing value classes with more fixtures, plus generating input-format probes (escapes, headers, field counts), is cheap: 24 ms per probe.
   - **Docs as a first-class dirty-side source.** When public documentation exists, the observer should (a) turn its rules into claims, rewritten in the observer's own words and verified by probes, and (b) report where the documentation disagrees with observed behavior.
     - Reading a manual to learn the functionality is lawful (*SAS v WPL*).
     - Copying its prose is not, and the docs arm reproduced the help text verbatim from the manual.
4. **Clean-room hygiene differs between the arms.**
   - The spec arm's output contains no target prose (the gate showed 20 warnings, all on our own echoed data).
   - The docs arm copied the manual's help text verbatim, which is expression.
   - So the docs arm's 97% is not a clean-room result. It is an upper-bound baseline.

## Threats to validity

- One tool, one run per arm, and the same model for inventor, observer and implementers.
- The inventor wrote both the manual and the tests, so they share an author's view of what matters. That favors the docs arm.
- The spec arm stopped after 1 verify call because it passed everything. **The conformance suite was saturated by the clone, so it gave no signal about what was missing.** The verifier can only test what was probed, which is the same coverage problem again.

## Next (ROADMAP)

- [ ] Rule claims authored by the observer, with automatic probe generation and falsification.
- [ ] A feature inventory and coverage gate (help plus documentation), so unprobed features become unknowns.
- [ ] Wider input fixtures, and generated input-format probes.
- [ ] A docs-to-claims path: rewrite documentation rules as claims, verify them by probes, report documentation/behavior conflicts.
- [ ] Re-run this benchmark with a fresh inventor tool. Target: spec arm ≥ docs arm, with no target prose in the clone.
