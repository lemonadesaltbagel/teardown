<div align="center">

# Teardown

### Clean-room reimplementation by black-box observation.

**See a feature you like. Rebuild it from how it behaves, never from its code.**

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776ab?style=flat-square&logo=python&logoColor=white)](pyproject.toml)
[![MCP servers](https://img.shields.io/badge/MCP-observe_%C2%B7_clean-5c4ee5?style=flat-square)](#how-teardown-works)
[![Targets](https://img.shields.io/badge/targets-CLI_%C2%B7_web_%C2%B7_Android-0f766e?style=flat-square)](#what-you-can-analyze)
[![Status: pre-release](https://img.shields.io/badge/status-pre--release-f59e0b?style=flat-square)](ROADMAP.md)
[![Apache-2.0 license](https://img.shields.io/badge/license-Apache--2.0-d22128?style=flat-square)](LICENSE)

[Quick start](#quick-start) · [How Teardown works](#how-teardown-works) · [What you can analyze](#what-you-can-analyze) · [Results](#results) · [FAQ](#faq) · [Documentation](#documentation)

<code>uv run teardown demo</code>

</div>

> [!IMPORTANT]
> Teardown is pre-release. You declare the purpose of every analysis at intake and own its legal assessment.
> Read [Responsible use](#responsible-use) first.

<div align="center">

<br />

<img src="docs/assets/teardown-flow.svg" alt="A confined observer studies the target's behavior through Teardown's drivers; the gate releases a sanitized spec; a confined clean agent rebuilds the feature and gets abstract verdicts back" width="1200" />

<br /><br />

</div>

---

See a feature in an app that you want in your own product? Teardown lets you rebuild it **without ever looking at
its implementation**. One agent, the *observer*, studies the app as a black box. It records what the app accepts,
refuses and defaults to, what it does at the edges, and how its screens are sequenced. Teardown turns that into
falsifiable rules and claims and releases them as a sanitized spec. A second agent, the *clean implementer*, sees
only that spec and writes its own implementation. It can check its work against the original, but it only ever
gets back abstract pass/fail verdicts.

The valuable knowledge about a feature is behavioral. Tracing the implementation through binaries, minified
bundles or obfuscated code is slow, brittle, and copies expression you don't want. Teardown never captures code,
decompilation or stack traces. What it cannot observe becomes an explicit *unknown*, not a silent gap.

Both sides can run **enforced, not just instructed**. The observer works in a container whose only way to the
target is Teardown's drivers. The implementer works in a container that sees only the spec. Every crossing goes
through the gate and is recorded in a signed, hash-chained audit log.

## Quick start

### Install

```bash
git clone https://github.com/lemonadesaltbagel/teardown.git && cd teardown
uv sync                                    # Python 3.12+
uv run playwright install chromium         # web targets
uv run teardown demo                       # observe -> gate -> clean -> verdict on a built-in example
```

Docker is needed for CLI targets (each run is isolated in a container) and for the enforced rooms. Android needs
the SDK and an emulator or device reachable through `adb`.

The commands below are written as `teardown ...`. Run them with `uv run teardown ...`, or activate the
environment first (`source .venv/bin/activate`).

### Set up your agent

Register the observe server with your agent (Claude Code shown; any MCP client works):

```bash
claude mcp add teardown-observe -- uv run --directory /path/to/teardown teardown observe --project /path/to/project
```

Then ask:

```text
Open web:http://localhost:3000/ as a research target and observe how the signup form behaves:
what it accepts and refuses, its error messages, and what happens when the API fails.
Write rules, measure coverage and release the spec.
```

The observer guide ([docs/observer-guide.md](docs/observer-guide.md)) is what the agent should read first.

### Review and release

```bash
teardown review  --project P --feature F           # gate findings by class, coverage gaps
teardown approve --project P --feature F --by you@example.com --class expected-output --reason test-oracle
teardown release --project P --feature F
teardown export-clean --project P --out KIT        # the kit: released spec + build/verify scaffolding
```

In strict mode every release needs your approval at a terminal. The observer's tools cannot approve anything
([docs/strict-gate.md](docs/strict-gate.md)).

### Rebuild in the clean room

```bash
teardown cleanroom up    --project P --kit KIT --claude-token-file ~/.config/teardown-claude-token
teardown cleanroom check --project P               # isolation probes, run from inside the container
teardown cleanroom shell --project P -- claude     # the implementer sees only /kit; `verify` asks the gate
teardown cleanroom down  --project P
```

`teardown observerroom` confines the observer the same way
([docs/clean-runtime.md](docs/clean-runtime.md)).

## How Teardown works

1. **Observe.** Drivers run the target and capture behavior only: outputs and file effects for CLIs,
   accessibility trees and API exchanges for web apps, accessibility trees for Android. A *mapper* turns each
   observation into a compact, wording-agnostic symbol.
2. **Generalize.** The observer probes fields and inputs by equivalence class and boundary. It injects faults
   (server errors, network failures, malformed bodies, unreadable files, airplane mode) and states rules in its
   own words. Teardown checks every rule against the original and records it as corroborated or falsified.
   Coverage turns anything not exercised into an unknown.
3. **Gate.** The release is checked for copied expression (verbatim and near-verbatim matches against everything
   observed and every ingested document) and for real names, which become a codename. In strict mode, findings
   need your recorded approval.
4. **Rebuild.** The clean agent builds from the spec and asks the gate to verify its build. The gate runs the
   original and the clone through the same tests and returns pass/fail with abstract symbols, never the
   original's text or evidence.

## What you can analyze

| Target | What Teardown observes | Faults it can inject | Requirements | Status |
|---|---|---|---|---|
| Command-line tools | Exit code, stdout, diagnostic presence and errno class, file effects | Closed/full stdio, unreadable files, read-only directories | Docker (isolated runner) or local | **Stable** |
| Web apps | Everything a user-facing Playwright locator or assertion can tell apart (the accessibility tree with roles, names, levels, states and nesting; field values and properties; titles, focus, status messages, landmarks text), plus API method/path/status and public-contract selectors | 5xx, network failure, timeout, malformed body, pending requests | Playwright Chromium; optional backend reset command | **Working**: 53% → 56% → 81.5% → 93.1% → 89.8% → 87.5% → 99.2% → 96.9% on eight held-out apps (see Results) |
| Android apps | Controls by role and name with state flags, visible text, system dialogs | Network off (airplane mode) | Android SDK, emulator or device via `adb` | **Working** |
| Linux desktop apps | AT-SPI tree: windows, controls, text, list items | — | Docker (Xvfb + AT-SPI container) | Experimental |
| macOS, Windows, iOS | — | — | — | Not started |

Teardown refuses to bypass protections and never captures implementation-tier data (see
[Responsible use](#responsible-use)).

## Results

Each result was scored on a hidden test suite that the observer never saw, against a pinned denominator. Each
comes with its caveat. The method is in [docs/evaluation.md](docs/evaluation.md).

### A command-line tool no model has seen: 397/397

A separate agent invented a tile-layout language (`tessel`) and its 397 hidden tests. Teardown's spec alone
gave a clone that passes all of them. A clone built from the manual alone passed 395. Rebuilt again with the
implementer locked in the clean room: 397/397 again.
[Round 1](research/10-novel-benchmark.md) · [Round 2](research/11-novel-benchmark-round2.md) ·
[Clean room](research/13-enforced-clean-room-rounds.md)

### An Android app no model has seen: 113/118

Wickwright, a three-screen candle-batch planner with validation, a capped queue and settings, was written for the
benchmark with 118 hidden scenarios. A confined observer worked through MCP alone, and a confined implementer saw
only the spec. The clone passes 113. The five misses are input-check orders and messages that were never probed.
[Report](research/14-android-novel-confined.md)

### Web apps no model has seen, held out: 53% → 56% → 81.5% → 93.1% → 89.8% → 87.5% → 99.2% → 96.9%

Kilnroll, a pottery-studio kiln logbook, was written for the benchmark with 120 hidden Playwright tests. Nothing
was tuned on it, and the tooling was frozen before the run. The clone matched every observed behavior (224/224
conformance), but half the hidden tests checked things the web abstraction did not record yet: page titles,
focus after validation errors, flash messages, table cells. `web.aria/v2` records them; the next held-out app
will show what that is worth. [Report](research/15-held-out-web-kilnroll.md)

A second held-out app (Kilnshare, 131 hidden tests) scored 73 with `v2`: nothing in what v2 added failed, but
the suite reaches rows through *tables*, and v2 recorded cells without their table. `web.aria/v3` records
tables and description lists. [Report](research/16-held-out-web-kilnshare.md)

A third held-out app (Lockline, 130 hidden tests, a neutral brief) scored **106 with `v3`**, from the thinnest
spec of the three. The remaining misses are pages the observer never visited, plus named regions and inline text
runs the abstraction still represents lossily. [Report](research/17-held-out-web-lockline.md)

A fourth held-out app (Scionry, 130 hidden tests) scored **121 with `v4`**. Releases now need coverage gaps
exercised or explained, so the observer covered 77 of 79 items. The rest are CSS-generated icon text and data
states the observer did not create. [Report](research/18-held-out-web-scionry.md)

A fifth held-out app (Wickward, 127 hidden tests) scored **114 with `v5`**. Nothing failed for CSS-generated
text, list data states or session expiry, which round 5 targeted. The new misses are an `alertdialog` role and
accessible descriptions. [Report](research/19-held-out-web-wickward.md)

A sixth held-out app (Fogline, 128 hidden tests) scored **112 with `v6`**, and its clone passed verification on
the first call. Nothing failed for dialog roles, descriptions, empty submits, query encoding or history. The new
misses are row headers, `aria-invalid` and named groups, which `web.aria/v7` now records. Three more were
observer gaps, two of them hidden by a fault-coverage bug that the observer itself reported (now fixed).
[Report](research/20-held-out-web-fogline.md)

A seventh held-out app (Strewnfield, 130 hidden tests) scored **129 with `v8`, under the strict gate**. `v8`
was built from an audit of what a user-facing Playwright suite can tell apart, rather than from the previous
round's misses. The observer could not approve. A person approved the release at their own terminal with
three class-level decisions, and the audit log records each one. The only miss was an empty list's message
the observer never produced. [Report](research/21-held-out-web-strewnfield-strict.md)

An eighth held-out app (Belfry, 130 hidden tests) repeated those conditions and scored **126**. The four
misses were again states the observer never exercised: a locked record's edit page, the sign-in page while
signed in, and focus after a move in the middle of a list. None was structure the spec failed to record.
[Report](research/22-held-out-web-belfry-strict.md)

### RealWorld "Conduit" web frontend: 99/101

RealWorld's own Playwright end-to-end suite was used. Over four rounds, each tooling gap the suite exposed was
closed: query strings, fault handling, empty structure, CDN assets, clock-dependent text. The score went
80 → 93 → 95 → 99. This is a **development-set** result (the tooling was tuned against this suite), and the
implementer recognized the app. [Report](research/12-web-conduit.md)

### `jq`: a lesson in contamination

The spec gave 394/429 on jq's own tests. The same model *with no spec at all* scored 397: famous tools measure
the model's memory, not the spec. This is why the benchmarks above use apps no model can know.
[Report](research/09-jq-cleanroom-experiment.md)

## FAQ

<details>
<summary><strong>Which agents can use Teardown?</strong></summary>

Any agent that supports MCP. The observe server runs over stdio or HTTP (`teardown observe --port`). The
enforced rooms ship a container with Claude Code and register only the room's Teardown server. Any other agent
that can run in the container and use a proxy works too.

</details>

<details>
<summary><strong>Does Teardown read the target's code?</strong></summary>

No. Drivers capture behavior-tier data only. Stack traces are redacted at capture, Android resource ids and
activity names never enter observations, and web API bodies are reduced to value-free shapes. In the observer
room, the observer agent cannot reach the target's files, bundles or the internet at all: only Teardown's tools.

</details>

<details>
<summary><strong>How is the clean side kept clean?</strong></summary>

The implementer's container mounts only the kit. Its only network peer is an egress proxy that allows the gate
and the model API. The gate accepts only clones built from the kit and returns abstract verdicts. Unexpected
errors come back generic, so dirty-side detail cannot leak through them. `cleanroom check` proves the isolation
from inside the container.

</details>

<details>
<summary><strong>What about the model's own memory?</strong></summary>

No container can close that gap. If the implementer's model already knows the target, part of the result is
memory. Teardown asks implementers whether they recognized the target and reports it. The uncontaminated
benchmarks use apps written for the purpose.

</details>

<details>
<summary><strong>Does Teardown upload my app?</strong></summary>

Teardown runs locally. Your agents send their tool results to their model provider, which has its own data
policy.

</details>

<details>
<summary><strong>Is reimplementing a product this way legal?</strong></summary>

That depends on your jurisdiction, the target's terms and what you build. Teardown records your declared
purpose and shows applicable warnings, but it does not give legal advice. A clean room addresses copying of
expression. It does not address patents, trademarks or trade dress.

</details>

## Documentation

- [Observer guide](docs/observer-guide.md): driving the dirty side for CLI, web and Android targets.
- [Strict gate](docs/strict-gate.md): reviewing findings and approving releases.
- [Clean runtime](docs/clean-runtime.md): the enforced clean room and observer room.
- [Evaluation](docs/evaluation.md): the benchmark method and every result with its caveats.
- [Design](DESIGN.md) and [Roadmap](ROADMAP.md): decisions, architecture and status.
- [Research](research/): experiment reports, from feasibility spikes to the confined rounds.

## Responsible use

Teardown never:

- bypasses CAPTCHAs, bot protection, certificate pinning, root or attestation checks, or FLAG_SECURE;
- flips Electron fuses or re-signs binaries;
- uses fake accounts or exceeds configured rate limits;
- captures implementation-tier data (code bodies, decompilation, stack traces).

These refusals are not configurable. Observe only software you are allowed to observe, within its terms. You
declare your purpose at intake and own the legal assessment.

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the ground rules, and report
anything that could let information cross the clean-room barrier privately through [SECURITY.md](SECURITY.md).
Changes are listed in [CHANGELOG.md](CHANGELOG.md).

```bash
uv sync
uv run ruff check src tests
uv run pytest -q    # Android and desktop tests run when an emulator / the desktop image is available
```

## License

[Apache License 2.0](LICENSE). See [NOTICE](NOTICE).

The license covers Teardown's own code and documents. Teardown grants no rights in the software you analyze:
observing a target, and building and distributing anything from what you observed, remain subject to that
target's terms and the law that applies to you.
