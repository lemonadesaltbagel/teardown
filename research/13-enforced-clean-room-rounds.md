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
