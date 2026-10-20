# Teardown

Clean-room, behavior-first analysis of applications. Teardown observes a target black-box, learns how it behaves
(what it accepts, refuses, defaults to, and how its UI is sequenced), states that as falsifiable claims, releases a
sanitized spec through a gate, and lets a separate clean-side implementer verify a reimplementation against the
original — getting back abstract verdicts only.

Status: **Phase 0** (core skeleton, fake driver). See `DESIGN.md` for decisions and `ROADMAP.md` for the plan;
research is in `RESEARCH.md`, `DECISION-REPORT.md` and `research/`.

## Try it

```bash
uv sync
uv run teardown demo            # observe -> claims -> gate -> clean -> verdict on a fake signup wizard
uv run pytest -q
```

The demo shows the gate catching a leaked UI label in the first spec draft, a refined mapper, a 24-state learned
model, two corroborated claims, a release under a codename, and two clean-side implementations verified against
the original: the faithful one passes every test, the buggy one fails with a minimal abstract counterexample.

## MCP servers

```bash
uv run teardown observe --project PATH   # dirty side: open_target, set_mapper, run_sequence, learn_flow,
                                         # propose/falsify claims, compile/review/release spec, tickets, audit
uv run teardown clean --project PATH     # clean side: get_spec, list_unknowns, ask_question, get_ticket,
                                         # verify_against_original
```

Give the clean server only to the implementer agent, and run it in a separate environment. In Phase 0 the verifier
runs in-process, so `teardown clean` still needs the project path; Phase 3 moves the verifier behind a network
boundary and ships the isolated clean runtime.

## What Teardown never does

Bypass CAPTCHAs or bot protection, certificate pinning, root/attestation checks or FLAG_SECURE; flip Electron fuses
or re-sign binaries; use fake accounts; exceed configured rate limits; or capture implementation-tier data (code
bodies, decompilation). What cannot be observed is recorded as an *unknown*.

You declare the purpose of an analysis at intake and are responsible for its legal assessment; Teardown records
your declarations and shows applicable warnings. A clean room does not address patents, trademarks or trade dress.

## Layout

```
src/teardown/
  core/      content-addressed records, workspace (packs + ledgers + corpus), observation tree, confidence
  drivers/   driver contract, hard-refusal policy, observation session, fake driver
  engine/    mapper (observation -> abstract symbol), learner (AALpy KV / L#), claim ledger
  spec/      EFSM IR + interpreter, EARS / XState exports, spec drafts and release projection
  gate/      verbatim matcher (suffix automaton), gate review/release, verifier (abstract verdicts)
  audit/     hash-chained in-toto statement log
  mcp/       observe and clean MCP servers
  examples/  fake signup target and example clean-side clones
spikes/      feasibility spikes (reference only)
```

License: to be decided.
