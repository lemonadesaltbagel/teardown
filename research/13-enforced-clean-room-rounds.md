# Experiment: implementers inside the enforced clean room

*2026-10-21. Clean-room runtime: `teardown cleanroom` (`docs/clean-runtime.md`), commits `2ab321a` to `ab5b799`.*

## Question

Earlier rounds kept the implementer in its kit by instructions only, and implementers slipped: they listed folders
outside the kit and wrote scratch files outside it. Does the loop still work when the barrier is enforced by the
environment rather than the prompt?

## Setup

- **Clean zone.** An isolated container, read-only, unprivileged, with no capabilities and only the kit mounted.
  - The implementer is Claude Code (`claude-opus-5-5`, the same model as the earlier implementers), running
    headless inside the container.
  - Managed settings deny web tools.
  - The only network peer is the egress proxy.
- **Egress allowlist.**
  - The gate (kit-only clone targets).
  - The model API.
  - For the web round only: the Conduit backend API, which the kit says the implementer may call.
- **Isolation probes** (`cleanroom check`, before each round): 8/8 passed both times.
  - No direct route out.
  - The proxy refuses the internet and the original's port.
  - The project directory is invisible.
  - The kit is the only mount.
- **Kits.** Freshly exported, empty `impl/`, from existing releases:
  - web: the round-4 Conduit release (`research/12`);
  - CLI: the round-2 `tessel` release (`research/11`).
- **Prompts.** The earlier prompts, changed only to name `verify` and `$TEARDOWN_API_URL` instead of host paths.

## Results

| round | verify calls | conformance (through the gate) | hidden suite | earlier result with the same release |
|---|---|---|---|---|
| web (Conduit, round 4 release) | 1 of 6 | 570 / 0 / 6 inconclusive | **99/101** | 99/101 (round 4, prompt-only barrier) |
| CLI (`tessel`, round 2 release) | 1 of 20 | 1144 / 0 / 1 inconclusive | **397/397** | 397/397 (round 2, prompt-only barrier) |

- **Egress.** In both rounds every attempt the implementer made was allowed, and every allowed attempt went to an
  allowlisted destination:
  - the model API;
  - the gate;
  - for web, the backend API (GET/POST/PUT/DELETE while it explored response shapes).

  The only refused attempts in the logs are the isolation probes run before each round.
- **Blocked, as designed.** The web implementer found no browser in the container, and Node's `fetch` ignored the
  proxy settings (now fixed with `NODE_USE_ENV_PROXY`). It tested with its own fake DOM instead. The CLI
  implementer reported nothing blocked.
- **Inconclusives** are the original diverging from its own recording (password-change sequences, the full-stdout
  probe), not clone failures.
- **Contamination.** As before, the web implementer recognized RealWorld Conduit. The CLI implementer did not
  recognize the tool (it is a private tool written for the benchmark).
- **Scoring note.** The hidden CLI suite compares `--help`/`--version` stdout, which contains the tool's real name.
  The clone prints its codename, so scoring maps it back (`bench-jsonl --rename ember-raven tessel`), as in round 2.
  Without the mapping it scores 393/397.

## Conclusion

Enforcing the barrier cost nothing in outcome: both rounds matched their prompt-only results. The two implementers
needed one verify call each, and neither could have reached the original, the project or the internet. This
closes the M2 exit criterion (an implementer running inside the clean room, isolation shown, rounds scoring).

## Round 6: both sides confined

*Project `.teardown/obs-web6`, kit `.teardown/cleanroom/web-r6` (codename indigo-meadow). Observer room:
`teardown observerroom` (`e45355f`).*

- **Observer.**
  - A fresh agent in the observer room (Opus 5.5). Its only tools were the observe MCP server over HTTP and a
    scratch workspace holding the guide and the public `SELECTORS.md`. It had no earlier scripts.
  - Isolation probes: 11/11 before the run. During the run, egress contained only MCP calls (89) and the model
    API.
  - It worked for 29 minutes entirely through MCP and released 42 rules (40 corroborated, 2 contested),
    64 probe rows, 37 claims and 10 unknowns, with 65/65 of *its own* inventory covered.
- **Implementer.** A fresh agent in the clean room with the round-5 prompt. It used 1 verify call and passed
  198/198 conformance tests.

| | hidden suite (pinned 101) |
|---|---|
| Round 4 (observer and implementer confined by prompt) | 99 |
| Round 5 (round-4 spec, implementer confined) | 99 |
| **Round 6 (both confined)** | **93** |

The 8 extra failures trace to the observer's choices, not to the barrier:

- **Comment deletion (3).**
  - `blocked_hosts` reported the icon CDN, but the observer left it out of `asset_hosts`: it took the icon
    glyphs in accessible names for a defect.
  - Icons were zero-size during observation, so the clone's delete icon is too.
  - The guide now says the glyphs are real behavior.
- **The app starting while the server is down (5).**
  - The observer injected only a 401 on the current-user endpoint, never a 5xx, a network failure or a
    malformed body.
  - The guide asked for these on every important endpoint, but nothing measured it.
  - `coverage` now lists every observed endpoint × fault class (`556a0ff`). On this project it reports 30
    uncovered items, including exactly these three.

**Bugs the MCP-only observer surfaced, all fixed** (`6e14f76`, `d6012c0`):
- tool errors arrived without their message;
- dotted keys made `same` checks pass vacuously;
- reopening a target dropped all actions, and could relax strict mode;
- rules could not be retracted;
- `valid=` rejected literal values;
- accepted titles were mined as "refused" because their slugs differed.

**Reading.**
- The barrier costs nothing by itself: round 5 matched round 4.
- Confining the observer to MCP did cost spec volume in this run: 42 rules against 85, in 29 minutes. Round 6's
  observer started from nothing, where rounds 2–4 started from earlier observers' scripts. The spec's gaps were
  in coverage, which tooling can now make visible.
- The two fixes above were informed by the hidden suite's failures, so a re-run would be another
  development-set number.
