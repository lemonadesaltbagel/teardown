# Experiment: clean-room jq reimplementation from a Teardown spec (Phase 1 exit)

*2026-10-20. Code: `bench/jq/`, `src/teardown/bench/jqtest.py`, the `teardown bench-jq` command, and the kit in `.teardown/cleanroom/indigo-summit/` (local only, not committed).*

## Setup

- **Original:** distro jq 1.7.1 (Debian `1.7.1-6+deb13u4`) in `teardown/jq-original`.
- **Observer:** the Teardown CLI pipeline. It ran discovery, then a one-factor sweep, then pairwise combinations over accepted classes, then noise calibration (a rerun plus an environment sweep), then claim mining.
  - The probe corpus was hand-written from general knowledge of jq's interface (`bench/jq/observer_hints.py`), standing in for an LLM observer.
  - **It was written without reading the hidden suite.**
- **Gate:** standard mode, with `jq` and `jqlang` codenamed to `indigo-summit`.
  - It reported 2 findings: a leaked build-configuration string, and the type-name list (functional).
  - The release has 1,725 probes, 61 claims, 3 unknowns, about 1 MB.
  - The string "jq" appears nowhere in the release.
- **Clean implementer:** a separate Claude agent, isolated by instruction only (Phase 3 adds the isolated runtime).
  - It could use only the kit directory, Python 3.12 standard library, no network, and `verify.sh` for abstract verdicts.
- **Hidden oracle:** jq's own `tests/jq.test` at tag `jq-1.7.1`, fetched at run time and never shown to either side.
  - The original passes 429 of its 447 cases under our harness (modules and the `?//` error-output cases account for the 18 failures). **The denominator is pinned at 429.**

## Results

| Arm | Conformance suite (Teardown) | Hidden jq.test (429) |
|---|---|---|
| Control: original under the codename | 1714 pass / 0 fail / 11 inconclusive | **429 (100%)** |
| **Teardown spec → clean agent** | 1714 / 0 / 11 (3 verify calls) | **394 (91.8%)** |
| Memory only (same model, no spec, no oracle) | — | *(running)* |

- **Clone:** 4,478 lines in Python 3.12 standard library: lexer and parser, an interpreter built on generators with a path mode, about 200 builtins, and a value/number module.
  - No jq binary or library is present in the clone image.
  - No probe ids appear in the code.
- **The 11 inconclusive tests are `--build-configuration` probes.** Their expected output contained the product name, so the gate codenamed it and the original's live output no longer matches. The verifier withholds these instead of leaking them.
- **Hidden-suite failures (35):**
  - path-expression errors inside `try`, e.g. `path(.a | map(select(...)) | .[0])`;
  - `delpaths` with large negative indices and `del` with mixed slices;
  - the combined `@format` chain (line 64);
  - `nth` with negative arguments;
  - string multiplication edge cases;
  - `from_entries` key aliases;
  - one top-level `.` case with unusual input (line 46).

  All of these are areas the probe corpus never exercised.

## Threats to validity (read before quoting the number)

1. **Contamination.**
   - The implementer recognized the tool as jq. The filter language is unmistakable, and the project path leaked the name (see 2).
   - It reports using prior knowledge wherever the spec was silent: `-e`, `$ARGS`, `--slurpfile`, the `@uri` character set, the `from_entries` aliases, number-formatting thresholds.
   - Where memory and spec disagreed, it followed the spec (`repeat`, `//` passing errors through, `leaf_paths` undefined, exit code 5 on unparseable input).
   - **91.8% therefore measures spec + memory, not the spec alone.** The memory-only arm measures the memory component.
2. **Barrier leak.** `verify.sh` contained the project path `.teardown/jq`.
   - Fixed in commit `2bfb75f`: kits now go through a codenamed link, and export fails closed if any denylisted name appears in the kit.
3. **Instruction-based isolation.** The implementer could technically read outside the kit. It reports one slip: a temporary file in `/tmp`, since removed.
4. **One run, one model, one target.** No variance estimate yet.
5. **The observer's probe corpus came from the same model family's knowledge of jq.**
   - In production this is legitimate, because the dirty side may know anything.
   - It still means the probe set was well aimed at jq's real feature surface.

## What this shows anyway

- **The loop works end to end on a real, non-trivial tool:** probing (35 s), spec, gate, clean implementation, abstract verification, then a hidden oracle.
- **The conformance suite is a sharp, cheap feedback channel.** The implementer reached 0 failures with only 3 verify calls, because the released probe table doubles as a local test suite.
- **Coverage gaps in the probe corpus map directly onto hidden-suite failures** (path-expression error handling, `del`/`delpaths` edges). This is the "silent incompleteness" risk on the CLI side, and the Phase 1 backlog item for spec-coverage measurement.

## Next

- [ ] Memory-only control (running).
- [ ] An uncontaminated target: a CLI the model cannot recognize (a private or synthetic tool with its own test suite). This is the only way to measure the spec's contribution cleanly.
- [ ] Coverage without an oracle: measure spec coverage from the observer's side (feature inventory, classes per builtin), so gaps are found *before* release. Hidden-suite failures must never feed back into probing for the same benchmark: that would leak the oracle into the spec.
