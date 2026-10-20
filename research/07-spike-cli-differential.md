# Spike: CLI differential loop (GNU coreutils vs uutils vs BusyBox)

*Code: `spikes/cli-differential/`. Rerun with `.venv/bin/python run_spike.py all`. A clean rerun from scratch gives identical numbers. Run 2026-10-19.*

## Setup

| Role | Implementation | Image |
|---|---|---|
| **Reference** | GNU coreutils 9.7 | `debian:stable-slim` |
| Candidate | uutils 0.12.0, official aarch64 binary | `teardown/uutils:0.12.0` |
| Candidate | BusyBox 1.38.0 | — |
| Baseline (drift) | uutils 0.2.2, Ubuntu 25.10's default coreutils | — |
| Baseline (drift) | GNU 9.10 | `fedora:latest` |

The commands under test were `cut`, `seq`, `sort` and `head`.

The whole loop — discover → probe → run (fresh containers, two passes) → noise calibration → differential → claim mining — took **47 s end to end** from one command.

## Numbers

**Probes**
- **1,775 probes**: cut 591, seq 493, sort 434, head 257. 1,772 were comparable and 3 were nondeterministic.
- By strategy:
  - value sweep × 3 inputs: 976
  - two pairwise covering arrays: 270
  - seq operand sweep: 378
  - input/delivery: 80
  - argv syntax edges: 47
  - locale: 24

**Execution**
- **17,750 executions** (5 implementations × 2 passes) took **21.2 s wall** with 4 containers in parallel.
- Batching is **20–45× cheaper** than one container per probe:

  | Mode | Cost per probe |
  |---|---|
  | Batched (300 probes per container) | 3.4–8 ms |
  | One container per probe | 139–202 ms |
  | Empty container alone (startup overhead) | 137–186 ms |

- Discovery took 11.6–14.6 s for 4 commands × 5 implementations, about 130 probes per command per implementation.

**Reset fidelity**
- Pass A ran in generation order, pass B shuffled with different batch boundaries. They differed only on `sort -R`, so state does not leak within a batch.
- In 40 sampled probes, per-probe containers and batched runs gave identical results (40/40).

**Noise:** 3 probes, all `sort -R`, all stdout. These were auto-excluded.

**Agreement with GNU 9.7**

| Candidate | raw | text-normalized | **behavior (primary)** | coarse |
|---|---|---|---|---|
| uutils 0.12 | 69.9% | 71.4% | **89.7%** | 92.4% |
| uutils 0.2.2 | 59.8% | 60.8% | **92.6%** | 95.3% |
| BusyBox | 41.1% | 41.1% | **75.8%** | 77.4% |
| GNU 9.10 | 99.1% | 99.1% | **99.8%** | 99.8% |

- **Behavior level** compares exit code, stdout bytes, whether a diagnostic appears, errno class and filesystem diff.
- **Coarse level** compares success vs failure only.

**Divergences and claims**
- Divergent probes: uutils 183, BusyBox 428, uutils 0.2.2 132, GNU 9.10 3.
- 153 raw difference conditions became **111 claims** after value-class folding: uutils 25, BusyBox 81 (52 with more than one probe), uutils 0.2.2 26, GNU 9.10 2.

**Gaps in the GNU test suite**
- uutils main currently passes 662/719 GNU tests. For these four utilities, only `cut/bounded-memory` fails.
- Yet **81 of uutils 0.12's 183 divergent probes are not deliberate extensions.** These are edges the GNU suite doesn't cover.
- Caveat: this compares the 0.12.0 release with main's test status.

## Top 10 behavioral differences (hand-verified)

1. **`seq 1 0 3` (increment 0):** GNU and uutils refuse with exit 1. BusyBox prints `1` forever until the output cap kills it with signal 153. This held on 41/72 three-operand probes where GNU refuses.
2. **`sort -o FILE` with empty input:** GNU and BusyBox truncate FILE. Both uutils versions leave it untouched (3/3). **Only the filesystem diff shows this.**
3. **`head -c N -n 3`:** GNU applies the last option given; BusyBox always lets `-c` win (33/33).
4. **`head -c '' -n 3`:** GNU validates every occurrence and refuses. uutils validates only the option that takes effect, and accepts (15/18).
5. **`sort -S` validation:**
   - GNU refuses `0x10`, `-1` and `abc` with exit 2.
   - BusyBox accepts and ignores anything (42/45).
   - uutils accepts `0x10` but refuses `+2`, which GNU accepts.
6. **`sort` usage-error exit codes:**
   - GNU exits 2; uutils often exits 1 (27/30 `--sort` combinations, plus a missing argument to `-k`, `-t`, `-S` or `--batch-size`).
   - For an unknown `--sort` value, BusyBox exits 2 where GNU exits 1.
7. **Extensions:**
   - uutils and BusyBox accept `cut -F` and `-O` (33/33, 21/24).
   - uutils also accepts `cut -w` and `seq -t` (30/55).
   - GNU 9.7 and 9.10 refuse all of them.
   - These are 102 of uutils' 183 divergences.
8. **BusyBox `cut` lists and delimiters:**
   - It refuses lists GNU accepts: `"1 2"` and `4294967296` (18/18).
   - It accepts delimiters GNU refuses in the C locale: `-d` or `-O` with `ab` or `é` (18/18).
9. **BusyBox `head` and `sort`:**
   - `head` refuses the size suffixes `K`, `kB`, `KiB`, `M`, `Q`, plus `+2`, `' 2'` and huge values (54/54). It knows only `b`, `k` and `m`.
   - `sort -m` sorts unsorted input where GNU does a pure merge.
   - `sort` refuses `--debug`.
10. **Version drift:**
    - GNU 9.10 made `cut -c` multibyte-aware under `C.UTF-8`. uutils 0.12 already matches 9.10; uutils 0.2.2 and BusyBox match 9.7.
    - uutils fixed `cut -c +1` between 0.2.2 and 0.12: it used to accept it and now refuses like GNU (9/12).
    - BusyBox `seq` exits 0 with no output for `nan` and for an empty operand (4/4).

## Normalization lessons

- **Exact message matching is hopeless.** Text normalization gained only 1.5 percentage points for uutils and nothing for BusyBox. Messages differ in:
  - wording;
  - quoting style (`'\331\241'` vs raw bytes);
  - clap's `tip:` lines;
  - BusyBox printing a usage dump.
- Normalizations that were still needed:
  - strip program-name prefixes (`cut:`, `uu_cut:`, `busybox:`) and clap's `error:`;
  - drop "Try '--help'" lines;
  - collapse the BusyBox usage dump by matching it against its own help text.
- **What counts as a difference:** exit code, stdout bytes, diagnostic present or absent, errno class (from libc strerror), or a filesystem change. **Message wording is expression.**
- An "error locus" level (which of our argv tokens the message quotes) was too sensitive to quoting style to use as the primary comparison.

## Lessons for the driver

- **One container per batch.**
  - Each probe gets its own directory, built on the host and streamed in and out as tar.
  - Containers run with a read-only root, tmpfs, `--network none`, a non-root user, and `ulimit -t` / `-f`.
- **Never measure with the tools under test.** Use only tar and shell builtins inside the container, and diff on the host.
- **Cap output.** Infinite output then shows up as signal 153, which is its own behavior class.
- **Confirm discovery by behavior; never trust help parsing alone.** Three techniques:
  - an unknown-option reference (`-@`, with the letter substituted in);
  - a sentinel file, to tell whether an option takes an argument;
  - first finding a minimal valid invocation (e.g. `cut` needs a list).
- **Behavior caught help-parsing errors:**
  - A phantom `-M` came from the LIST syntax prose. It was dropped automatically.
  - Some accepted options are undocumented: GNU `sort -y`; BusyBox `sort -S`, `-T` and `-m`; BusyBox `cut -O`.
  - `-0`…`-9` turned out to be numbers in `seq` and obsolete syntax in `head`.
- **Hard parts:**
  - mapping placeholder names to types (clap's `<key>`, BusyBox's `N[bkm]`, BusyBox `sort`'s unbalanced synopsis);
  - enum domains that appear only in prose.
- **Deterministic content-hash probe IDs** let results join across implementations and runs.
- **Not covered:** TTY vs pipe. It needs a pty inside the container.

## Lessons for the spec format

- **Conditions need more than input factors.** They need:
  - value-class sets (decision tables);
  - argv shape;
  - environment;
  - outcome predicates (e.g. "whenever the reference refuses, it exits 2");
  - option precedence.
- **Tag every argv element as a factor.** Finding #3 was mislabeled as a claim about `-c` values because the base `-n 3` wasn't tagged.
- **Never combine invalid values in pairwise rows.** Multiple faults in one probe make blame ambiguous (finding #6). Use pairwise for valid classes and single-fault probes for invalid ones.
- **Claims need a strictness field** (must refuse vs may extend), or extensions flood the results (102 of 183 for uutils).
- **Outputs on precondition violation are implementation-defined.** Example: `sort -m` on unsorted input.
- **Claims carry the reference build fingerprint.** GNU 9.7 vs 9.10 changed `cut -c`.
- **Sample claim** from `out/claims.json`:
  - Statement: "When option -c is given and a size value of class {b,…,zero}, `head` shall succeed (exit 0) and write exactly the reference output."
  - `confidence {probes:33, confirming:33, contradicting:0}`, `status: corroborated`.
  - Falsified by BusyBox 33/33.
  - Carries evidence probe IDs and example argv.

## Files

- `run_spike.py`: steps are `discover`, `probe`, `run`, `bench`, `analyze` or `all`.
- `teardown_cli/` package:
  - `impls.py`
  - `runner.py`
  - `discover.py`
  - `probes.py`
  - `analyze.py`
- `images/uutils/Dockerfile`
- `out/` (about 59 MB of results): `models/`, `probes/`, `results/`, `evidence/help/`, `analysis.json`, `claims.json`, `bench.json`, `run_stats.json`.

## Notes

- The spike agent started Docker Desktop because it wasn't running.
- These images were left in place: `debian:stable-slim`, `busybox:latest`, `ubuntu:25.10`, `fedora:latest`, `teardown/uutils:0.12.0`.
