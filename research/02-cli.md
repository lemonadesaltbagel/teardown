# Teardown-cli: research track report

*CLI and TUI programs, plus libraries that sit behind a CLI and local daemons. Claims marked **[unverified]** could not be confirmed against a primary source. Collected 2026-10-19.*

## 0. REA prior art and gaps

### Reusable from REA

- **Process-capture scenario schema**
  - Fields: executable, args, cwd, explicit env, cols×rows×scrollback, timed `input`/`resize`/`signal` events, timeouts, and `finalization_ms` (SIGTERM, then SIGKILL).
- **Raw evidence**
  - Raw PTY chunks plus rendered `@xterm/headless` frames.
  - Before/after filesystem snapshots, with an `unknown` result when the snapshot is incomplete.
- **Normalization and comparison contracts**
  - Normalization is versioned.
  - Comparison contracts are committed; captures whose contracts differ are refused rather than diffed.
- **Trace specification** (`refs/rea/src/domain/process/processTraceSpecification.ts`)
  - Supports `partial_order` (happens_before / unordered_groups / prefix / suffix) and `finite_traces`.
  - This maps directly onto ordering claims that carry `nondeterminism: partial-order`.

### Gaps to close

1. **PTY only.** stdout and stderr are merged, so the original can't be probed for TTY-vs-pipe behavior or for which stream a message goes to.
2. **No expect-style waits.** Events are scheduled by clock (`at_ms`) only.
3. **Weak capture boundaries.** Snapshots are bounded and taken only before and after. There is no isolation, and the inherited environment is not recorded.
4. **No reset primitive.** Without one, automata learning isn't possible.

## 1. Driving

- **Two channels are mandatory.**
  - Pipe mode (`subprocess`): separate stdout and stderr, exact exit code and signal, and stdin closed, at EOF, `/dev/null` or `/dev/full`.
  - PTY mode (`ptyprocess` + `pexpect`, or `node-pty`): for interactive behavior.
- **TUI rendering**
  - `@xterm/headless` for fidelity (alt-screen, bracketed paste, mouse, truecolor).
  - `pyte` for cheap abstraction.
  - **Frames are evidence. Claims are made about the abstracted screen**, the TUI equivalent of the web side's accessibility-tree hash.
- **tmux control mode** (`tmux -C`) is a secondary renderer for cross-checking. It is not the primary driver.
- **Raw evidence format: asciinema asciicast v3**
  - NDJSON events with codes `o`, `i`, `r`, `m`, `x`. Spec: https://docs.asciinema.org/manual/asciicast/v3/
  - It has no stderr channel, so stderr goes in a sidecar file.
- **Signal and edge probes**
  - Signals: SIGINT, SIGTERM, SIGHUP, SIGPIPE/EPIPE, SIGWINCH.
  - Stream edges: closed stdout, `/dev/full`, stdin EOF in the middle of a prompt.
  - uutils had to fix aborts on `2>/dev/full` to pass the GNU tests.
  - Exit codes to classify: 0, 1, 2, 126, 127, 128+n.
- **Daemons**
  - Run each daemon in its own network namespace, detect its listeners, and probe until it is ready.
  - Hand the endpoint to the web/API observer.
  - The CLI side keeps only lifecycle claims: bind flags, signal → shutdown, pidfile, port conflict.

## 2. Interface discovery

### Sources, in order of preference

1. **Shell completion scripts.**
   - zsh `_arguments` encodes mutual exclusion, arity and value completers.
   - fish `complete -s/-l -r -x -a` gives similar structure.
   - bash completions can be *executed* by setting `COMP_WORDS`/`COMP_CWORD`.
   - Frameworks can emit completions on demand: clap, cobra, click.
2. **`--help` and usage errors** such as `--bogus`, which reveal the error grammar and usually exit with code 2.
3. **Man pages**: the OPTIONS, ENVIRONMENT, FILES and EXIT STATUS sections.
4. **withfig/autocomplete** specs (MIT), plus carapace and jdx/usage **[unverified coverage]**.

### Rules for discovered interface data

- **Parse into a neutral argument model; drop the prose.**
  - Option and value names are kept with `compat_reason: cli-interface`.
  - **The model is a hypothesis.** Every edge in it is falsified by probes.
- **Option grammar to probe**
  - Forms: `-x`, `-xVAL`, `-x VAL`, `--x=VAL`, `--x VAL`.
  - Abbreviations, clustering (`-abc`) and `--`.
  - Repetition semantics, and permutation vs POSIX stop (`POSIXLY_CORRECT`).
  - PICT pairwise across options to find conflict and override matrices.
  - Defaults are found by equivalence: output(no flag) ≡ output(flag=v).
- **Environment variables**
  - getenv is a libc call, not a syscall, so strace cannot see it.
  - Build a candidate set from man/help/completions, conventions (`NO_COLOR`, `CLICOLOR`, `TERM`, `COLUMNS`, `PAGER`, `EDITOR`, `HOME`, `XDG_*`, `TMPDIR`, `LANG`/`LC_*`, `TZ`, `<TOOL>_*`), and the binary's strings (dirty side only).
  - Confirm each candidate with a differential sentinel probe.
- **Config files**
  - Use a fresh HOME/XDG directory, plant canary files at candidate paths, and look for a behavior change.
  - A filesystem diff shows what gets created.
  - An access log from a FUSE or overlay layer is acceptable.
  - **strace/dtruss path sets count as steering only.** They must be deduplicated and unordered, then re-confirmed by canary probes. Raw syscall traces never become claim content.
  - dtruss needs SIP disabled.

## 3. Side effects and isolation

- **Linux default: rootless container or bubblewrap, with an overlayfs root whose upperdir is the side-effect record**
  - In the upperdir: regular files mean created or modified, char 0/0 whiteouts mean deleted, and the opaque xattr means a replaced directory. `docker diff` reports exactly this.
  - Complete per mount. It misses ordering and transient files; add inotify/fanotify if those matter.
- **Hardening**
  - nsjail (seccomp + namespaces) or Landlock (kernel ≥5.13).
  - Private netns with no route. Allow-listed egress goes through a recording proxy, with pcap on the veth.
- **Spawned processes**
  - Track them via PID namespace and cgroup.procs.
  - execve tracing through bpftrace or audit is steering only, unless the claim is user-visible (e.g. "invokes `$PAGER`").
- **macOS**
  - sandbox-exec is deprecated and there is no overlay. Use APFS clonefile and tree-hash diffs.
  - Run portable targets in a Linux VM or container.
- **Reset cost** **[unverified; benchmark this]**

  | Mechanism | Cost per reset |
  |---|---|
  | Discard overlay upper + new mount namespace | ~1–10 ms |
  | bwrap | ~10–50 ms |
  | Container | ~100–500 ms |
  | VM restore | seconds |

  - At about 10 ms per reset, budgets of 10^4–10^5 queries are practical. **CLI is the cheapest platform.**

## 4. Determinism and noise

- **Canonical environment**, recorded in the comparison contract (a gap in REA):

  | Setting | Value |
  |---|---|
  | Environment | `env -i` |
  | `HOME`, `XDG_*` | fresh directories |
  | `PATH` | minimal |
  | `LC_ALL` | `C.UTF-8` |
  | `TZ` | `UTC` |
  | `TERM` | fixed |
  | `COLUMNS`/`LINES` | fixed |
  | umask | 022 |
  | uid/gid | fixed, via userns |
  | hostname | fixed, via UTS namespace |
  | Other | `SOURCE_DATE_EPOCH`, `PYTHONHASHSEED`, fixed CPU count |

- **Time**
  - libfaketime only works for programs that read the clock through dynamic libc. It does not work for static binaries or Go, which use vDSO or raw syscalls.
  - Linux time namespaces virtualize only MONOTONIC and BOOTTIME.
  - For those targets, use a VM clock or a mask.
- **`calibrate_noise`**
  - Run N baseline repeats, then a one-at-a-time sweep in the style of reprotest. Variations: environment, build_path, kernel, aslr, num_cpus, time, user_group, fileordering, domain_host, home, locales, exec_path, timezone, umask.
  - Each variation either becomes an **environment-dependence claim** or a mask.
  - Thread and readdir order (rg, fd) become `partial_order` claims.
- **Probe axes to cover**
  - stdout: TTY vs pipe.
  - stdin: TTY vs pipe vs closed.
  - Terminal width.
  - `NO_COLOR`.
  - root vs non-root.

## 5. Inferring input domains for file inputs

- **Grammar inference**
  - **TreeVada** (ICSE'24) is deterministic and beats Arvada by +19.5% F1 and 2.4× in speed, so prefer it. It also has an incremental variant (arXiv 2408.16706).
  - **Arvada** (ASE'21) needs only seeds plus an accept/reject oracle.
  - **GLADE**'s results reportedly failed to replicate (PLDI'22) **[unverified detail]**.
- **What "accept" means**: exit 0 and no parse-error class on stderr.
- **Format inference**
  - Magic-byte and extension probes.
  - Mutation minimality: which bytes can change without the input being rejected.
  - Round-trip and idempotence probes, which yield metamorphic claims.
- **Fuzzing**
  - Radamsa, Hypothesis and grammar-based fuzzers are black-box.
  - AFL++ in QEMU/Frida mode is coverage-steered, so it is grey-box and may be used for steering only.

## 6. Case studies: reimplementations judged by the original's tests

### uutils/coreutils vs the GNU test suite

- **Pass history** (release notes):

  | Version | Date | GNU tests passed |
  |---|---|---|
  | 0.0.15 | 2022-08 | 242 → 293 |
  | 0.0.24 | 2024-01 | 422 (69.9%) |
  | 0.1.0 | 2025-05 | 522 (84.5%) |
  | 0.2.0 | | 538 (87.1%) |
  | 0.6.0 | 2026-02 | 622 (96.3%) |
  | 0.7.0 | | 629 (94.6%; GNU added 19 tests) |
  | 0.9.0 | | 625 (90.6%; GNU added 25 tests) |
  | 0.12.0 | 2026-09-17 | 653 pass / 21 fail / 18 skip (94.4%) |

- **Ubuntu 26.04** ships uutils 0.8.0 as its default coreutils (secondary source).
- **Policy**
  - No changes based on GNU source, and no links to it.
  - Contributors may read the GNU manual and BSD/MIT implementations.
  - AI output must not be derived from GPL code.
  - The GNU tests are fetched at test time and never vendored (`util/build-gnu.sh`).
- **Lessons**
  1. The denominator moves, so pin the oracle version.
  2. **Tests encode prose.** build-gnu.sh has about 68 `sed` lines rewriting expected error messages. Use error-class matching instead of byte equality.
  3. uutils upstreamed new tests to GNU, because differential testing finds behaviors GNU's suite doesn't cover.
  4. Reaching ~95% took about 4 years. The last 5% is SELinux, `/proc` and locale corners.

### Other reimplementations

- **Deno and Bun on Node's test suite**
  - Deno 2.8 (2026-05) passed 76.4% (3,405/4,457).
  - Bun 1.3.14 passed 40.6% on the same subset, per Deno.
  - Bun reports per-module rates instead (e.g. 98% of node:fs).
  - **Lesson:** headline numbers depend on which denominator is chosen. Publish and pin it.
- **ruff**
  - Implements every Flake8 rule plus 50+ plugins, and ~209 of pylint's ~409 rules.
  - Its formatter leaves >99.9% of lines identical on Black-formatted Django and Zulip.
  - **Lesson:** parity is measured over a **corpus**, so corpus-differential testing is a second oracle.
- **gojq and jaq**
  - Both publish ledgers of intentional divergences.
  - jaq has its own 500+ tests and a denotational semantics of jq (arXiv 2403.20132: jq "is currently only specified by its implementation").
  - **Lesson:** ship a divergence ledger, using `observed` vs `inferred-intent`.
- **Turso/Limbo (SQLite)**
  - Runs SQLite's TCL compatibility tests.
  - Intentional divergences live in a separate suite.
  - A deterministic simulator offers `--differential` against sqlite3.
- **Wine**
  - Every conformance test is **validated on real Windows first** (daily WineTest); clone gaps are marked `todo_wine`.
  - Disassembly is forbidden.
  - **This is the closest precedent for Teardown's loop:** a probe-written test is admitted only once the original passes it.
- **PyPy**
  - Lists its divergences, such as GC timing and refcount.
  - **Lesson:** classify resource-lifetime timing as `timing` or `out-of-scope` up front.
- **ripgrep, busybox and toybox**
  - ripgrep diverges deliberately. busybox and toybox are subsets, and toybox's `TEST_HOST` runs the same tests against GNU.
  - **Lesson:** the spec must declare its compatibility scope.

### Synthesis

- **The original's test suite is an excellent hidden evaluation oracle but a poor spec.** It over-specifies message text and leaves untested areas unspecified.
- **Mature projects converge on three artifacts:**
  - a conformance suite run against both implementations;
  - a divergence ledger;
  - a corpus or differential fuzzer.

## 7. CLI-Tool-Bench (arXiv 2604.06742, Hu, Wang, Peng, Gao, Lo, 2026)

- **Benchmark**
  - 94 repos: Python 34, JS 15, Go 45.
  - An LLM extracts a command schema from the README and `--help`. LLM-directed fuzzing then generates 50 cases per command pattern, kept only if the oracle accepts them.
  - Twin Docker containers, snapshotted, with no network. Filesystem deltas are captured.
- **Metric tiers**
  - Build → Exec, where exit codes must match strictly.
  - → SP: side effects must match first.
  - → EM: whitespace-normalized exact match.
  - → FM: Levenshtein similarity ≥ 0.8.
  - → SM: an LLM judge.
- **Results**
  - The best model was Kimi-k2.5, with SM 43.8% and EM 36.3%.
  - Claude-Sonnet-4.6 scored SM 10.6% with Build 44.7%, which looks like a harness failure **[interpretation]**.
  - Repo: https://github.com/kinesiatricssxilm14/CLI-Tool-Bench
- **Use for Teardown**
  - **A ready-made baseline:** replace the README-derived prompt with a Teardown sanitized spec and measure the uplift on the same hidden suites.
  - Adopt the order of the gates. Reject an LLM judge as the verdict; verdicts that cross the gate must be deterministic.
- **Normalization stack** (each rule versioned)
  1. ANSI escape codes.
  2. Line endings and trailing whitespace.
  3. Paths → `<ROOT>`.
  4. pids, ports and temp files.
  5. Calibrated time masks.
  6. Unordered line sets for partial-order claims.
  7. Structured equality for JSON/CSV/YAML.
  8. **Error class**: stderr non-empty + exit code + refusal class, not message bytes.

## 8. Evaluation targets

| Target | Hidden oracle | Feasibility |
|---|---|---|
| **jq** (MIT) | `tests/jq.test` (~500–800 cases) plus the gojq/jaq divergence ledgers | **High: first target** |
| **GNU coreutils subset** (sort, cut, tr, wc, seq, uniq, head/tail) | GNU `tests/`, run the way uutils does. uutils' history serves as a published human baseline | **High** |
| **git porcelain subset** | `t/t*.sh` with `GIT_TEST_INSTALLED` | Medium |
| **Miller / csvkit** | regression cases | High |
| **fd / ripgrep** | integration tests (needs an adapter) | Medium-high / Medium |
| **sqlite3 shell** | sqllogictest; Turso cli_tests | Medium-hard. A good L\* target for its REPL modes |
| **TUI** (htop, lazygit, tig, nnn) | none; we would write our own hidden frame-claim suite | Low-medium, a stretch goal |
| **CLI-Tool-Bench** (94 repos) | the benchmark's own suites | A broad, comparable benchmark |

## Decisions

1. **Driver**
   - Python `ptyprocess`/`pexpect` plus a pipe-mode runner.
   - REA's scenario schema, extended with:
     - `stdio_mode` per stream: tty / pipe / null / closed / full;
     - `wait_for`: regex / screen predicate / quiescence;
     - an explicit `env -i` environment.
   - Renderer: xterm-headless sidecar or pyte.
   - Raw evidence: asciicast v3 plus a stderr sidecar.
2. **Isolation:** overlayfs + bubblewrap/nsjail. The upperdir is the canonical side-effect record. Benchmark reset latency in week 1.
3. **Interface discovery:** discovered interface data → a neutral argument model, with every edge falsified by probes. Option names cross the gate with `compat_reason`; prose never does.
4. **Grey-box policy:** strace path sets, getenv interposition and AFL++ coverage are for **steering only**. Every claim must be re-established black-box, and the grey-box input is tagged `steering_evidence`.
5. **Noise:** repeats plus a reprotest-style sweep. Each finding becomes an environment-dependence claim, a mask, or a partial-order claim.
6. **New claim kinds:** `stdio-mode-dependence`, `env-binding`, `config-precedence`, `exit-code`, `signal-contract`, `stream-attribution`.
7. **Verdicts:** deterministic tiers in the order side effects → exit/error class → normalized stdout. No LLM judge.
8. **Daemons:** CLI lifecycle claims, then hand off to the web/API observer.
9. **Benchmark**
   - Phase 1: jq + 5–7 coreutils.
   - Phase 2: Teardown specs vs README specs on CLI-Tool-Bench.
   - Phase 3: git + sqlite3.
   - Always pin the oracle and publish the denominator, the divergence ledger and the expected failures.

## Risk

| Area | Rating |
|---|---|
| Driving | Low |
| Linux isolation | Low |
| macOS-native isolation | Medium |
| Determinism | Medium (static/Go time, thread order) |
| Interface discovery | Low-medium |
| File grammar inference | Medium-high |
| TUI specs | High |
| Leakage through messages | Medium |
| **Overall** | **Low-medium: the best platform for the rigorous MVP** |
