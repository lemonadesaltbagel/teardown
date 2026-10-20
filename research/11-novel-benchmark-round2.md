# Experiment: uncontaminated benchmark, round 2 (`tessel`), after Phase 1.5

*2026-10-20. Round 1 is in `research/10-novel-benchmark.md`.*

## What changed since round 1

**Phase 1.5 features:**
- observer-authored **rules** with `outcome` / `same` / `differs` checks;
- relational verification on the clone;
- generic input mutations;
- a coverage inventory, where uncovered items become unknowns;
- docs ingestion, so copied wording is flagged.

**Process:**
- **The observer was an independent agent.** It worked from `docs/observer-guide.md`, the tool's `--help`, its manual and black-box runs. It never saw the source or the tests, and I did not hand-tune its hints.
- **A new tool, `tessel`**, written by a separate inventor agent: a tile-layout language.
  - 1,160 lines; 397 hidden tests.
  - Sheet format with sections and escapes, derived tiles, 6 operators with precedence, 3 transforms, 7 functions, and exit-code classes with a fixed precedence.

## The observer's release

| | |
|---|---|
| Probes | 620 (0 nondeterministic) |
| Rules | 96 (about 600 checks): 94 corroborated, 2 falsified (= documentation/behavior conflicts) |
| Claims | 69 mined |
| Unknowns | 2 (the conflicts) |
| Coverage | 95/95 inventory items |
| Gate | 35 rule statements initially shared word runs with the manual and were reworded. One finding remained: the exact `--help` output, observed as stdout 12 times. |

**Conflicts found in the inventor's own manual:**
1. Whitespace is allowed before a call's `(`; the manual says it is not.
2. `-D` text splits into rows at line feeds; the manual says a `-D` tile is always one row.

**Undocumented behaviors captured as rules:**
- `--help`/`--version` take precedence over late checks;
- tab expansion inside literals;
- a lone CR is kept;
- raw control characters are accepted;
- `crop` clips each axis independently;
- `-o -` writes a file literally named `-`;
- oversized numbers map to exit 7.

## Results (hidden suite, 397 cases; the original scores 397/397)

| Arm | Sources | Hidden suite | Conformance (verify) |
|---|---|---|---|
| **Spec** (Teardown) | spec.json only | **397 (100%)** | 1144/0, 1 inconclusive, **1 verify call** |
| **Hybrid** | spec.json + manual | **397 (100%)** | 1144/0, 1 inconclusive, 1 call |
| Docs | manual only | 395 (99.5%) | — |

- **The docs arm's 2 failures:**
  - `func_space_before_paren` is exactly documentation conflict #1, where it followed the manual and the tool does otherwise.
  - `cli_output_empty_name` is an underspecified edge case.
- **The spec arm reports** that the rules were "precise and complete enough to write the whole thing in one pass". Its only guesses were in areas no probe or rule covered: closed or full stdout, and the order in which `--list` evaluates.
- **Neither clean implementer recognized the tool.**
- **The inconclusive test** (stdout `/dev/full`) is held back because the original's behavior there diverged from the spec. That is an interpreter-level crash path.

## Round 1 → round 2

| | Round 1 (`quill`) | Round 2 (`tessel`) |
|---|---|---|
| Observer | hand-written hints, no rules | independent agent, 96 rules, coverage gate |
| Spec arm | 84.7% | **100%** |
| Docs arm | 97.0% | 99.5% |

The tools differ, so this is not a controlled A/B of the features. The docs-arm scores (97.0% vs 99.5%) suggest the two tools are of similar difficulty for an implementer. The spec arm's jump is consistent with round 1's diagnosis: rules and coverage, not more examples, were what was missing.

## Clean-room hygiene notes

- **The `--help` text was released as observed stdout** (the gate flagged it in standard mode). Both spec-based arms reproduced it exactly, because the hidden tests compare `--help` output.
  - This is the one place where the released spec carries the original's prose.
  - In strict mode it needs a human decision. Either approve it as a functional quote (`compat_reason: user-required` when byte-exact help output is required), or drop those probes and accept failures on `--help` tests.
  - **The product must surface this decision explicitly** rather than leave it as a warning.
- **The observer saw Python tracebacks** when the target crashed on a closed stdout (an implementation-tier leak).
  - Fixed in `da5205b`: stack traces are now redacted at capture.
- **The docs arm copied help text from the manual verbatim.** This is expected for that arm, and it is why the docs arm is a baseline, not a clean-room process.

## Threats to validity

- One tool per round and one run per arm, all on the same model family.
- **A ceiling effect:** 2 of 397 cases separate spec from docs. The headline is "the spec matches a complete manual", not "the spec beats documentation by a margin".
- The observer was an agent of the same model family as the implementers. It spent about 25 minutes and was generous with probes. Observer effort and quality are now the main variable.
- The inventor wrote both manual and tests (shared perspective); its manual was unusually complete.

## Implications for the product

1. **Rules plus coverage is the spec format.** Probe tables are evidence and worked examples; mined claims are secondary. Promote rules to first class across platforms; web is already supported.
2. **The observer agent and its guide are a product component.** Their quality bounds spec quality. Ship the guide, a coverage gate that blocks release on gaps, and a rule-authoring loop that rewrites falsified rules.
3. **When documentation exists, the hybrid is the realistic deployment.** It reaches the ceiling and resolves documentation/behavior conflicts correctly. Teardown's distinct value is the conflicts and undocumented behaviors (#1 and #2 above, plus the seven captured as rules).
4. **Prose that tests require byte-exact** (help and usage text) needs an explicit policy decision in the gate UI.
