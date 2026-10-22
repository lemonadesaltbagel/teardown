# Contributing

Issues and pull requests are welcome: bug reports, new targets, better probes, documentation.

## Development

```bash
uv sync
uv run playwright install chromium
uv run ruff check src tests
uv run pytest -q
```

- CLI tests that need Docker skip themselves when Docker is unavailable.
- Android tests need an emulator with the example apps (`src/teardown/examples/android*/build.sh`).
- Desktop tests need the desktop image (`deploy/desktop-linux/`).
- CI runs lint and the tests that need neither.

## Ground rules

- **Behavior only.** Drivers capture behavior-tier data; nothing may capture code, decompilation or stack traces.
- **Hard refusals stay hard.** CAPTCHAs, bot protection, pinning, attestation, FLAG_SECURE, fake accounts: no
  option, flag or profile may relax them.
- **The barrier is the product.** A change must not let dirty-side information reach the clean side except
  through the gate's release. This covers error messages, verdict details, kit contents and logs.
- **Missing coverage is unknown, not absence.** New probes and abstractions record what they could not observe.
- **Real names never enter kits or kit paths.**

## Pull requests

- Use Conventional Commit subjects (`feat(web): …`, `fix(gate): …`, `docs: …`).
- Describe the behavior change and the checks you ran. Report only checks that actually ran.
- Add a test for each behavior change. Prefer the public workflows (the CLI, the MCP tools, the `Project` API)
  over module internals.
- AI-assisted contributions are welcome. A human reviews and owns the final diff.

## Reporting issues

Use the issue templates. For anything that could let information cross the barrier, follow
[SECURITY.md](SECURITY.md) instead of opening a public issue.
