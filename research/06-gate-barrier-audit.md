# Teardown gate, barrier and audit: research track report

*Not legal advice. Primary sources: the clean-room-skill@0.8.0 tarball (all files read), REA `evidence.ts` / `evidenceBundle.ts`, and the Claude Code sandbox, permissions and Agent SDK docs. **[unverified]** marks secondary or remembered claims. Collected 2026-10-19.*

## 1. Prior art

### clean-room-skill (whit3rabbit, v0.8.0)

This is the closest existing tool. It works from source code; screenshots are only a fallback.

- **Roles**
  - **Agent 0** is the contaminated manager and verifier. It talks to the clean side only through schema-valid files: no chat, no hints, only "abstract delta tickets".
  - **Agent 1** is the source analyst and writes draft specs.
  - **Agent 1.5** is a handoff sanitizer. It runs in a fresh context and cannot see the source, Agent 1's chat or the denylist.
  - **Agent 2** is the clean architect.
  - **Agent 3** is the clean implementer and QC.
  - **Agent 4** is the polish reviewer.
- **Barrier**
  - Five env-defined roots: `SOURCE`, `CONTAMINATED_ARTIFACT`, `CLEAN`, `IMPLEMENTATION`, `ALLOWED_READ`.
  - Random neutral IDs. An environment hook fails closed if a root path contains tokens from the source folder name.
  - Docker is used only for Agent 3's tests: no network, no source mounts, capabilities dropped.
  - The project admits this is "context-level separation, not the OS-enforced wall".
- **Hooks** (`docs/HOOKS.md`)
  - `deny-clean-room-shell` allows only the test runner.
  - `deny-clean-source-read` covers Read, Glob, Grep, LSP, MCP resources and view_image.
  - `deny-contaminated-clean-write`.
  - PostToolUse runs `validate-json-schema`, `check-artifact-leakage` and `validate-handoff-package` (sha256 checks, no contaminated paths).
  - **Gap: nothing hooks WebFetch or WebSearch.** Web access is limited only by the agent's `tools:` frontmatter.
- **Spec schema** (`behavior-spec.schema.json`, 28 required fields)
  - `observable_behaviors`, `inputs`, `outputs`, `state_transitions`, `edge_cases`, `error_conditions`, `negative_behaviors`, `timing_or_ordering`, `invariants`, `test_scenarios`.
  - `public_surface[]{name, kind, visibility ∈ public|destination|protocol|user-required, compatibility_reason}`.
  - `compatibility_level ∈ exact-public-contract|behavior-compatible|best-effort`.
  - `evidence_status ∈ observed|derived|inferred|unknown|error`.
  - `leakage_review`, `review_history`.
- **Leakage checks**
  - Regex and denylist only: code fences, diffs, stack lines, the words "decompiled|jadx|apktool", identifier heuristics, and a hidden denylist (up to 20k terms).
  - **No n-gram or fuzzy matching, no post-hoc similarity check, no memorisation probes.**
- **Evidence ledger**
  - Fields: `{evidence_id, source_unit_ref, evidence_type, description, location_ref, source_hash, sensitivity, retained_in_contaminated_domain}`.
  - No content addressing, hash chain or signatures.
- **Worth reusing**
  - The role split, especially a sanitizer that never sees evidence.
  - Coordination only through artifacts, with delta tickets.
  - Neutral naming plus the root-name check.
  - Write-time hooks.
  - `public_surface` with a `compatibility_reason`.
  - Deny-by-default completion.
  - Contamination-incident records.
- **Missing for a behavior-first tool**
  - An oracle channel back to the original.
  - Falsifiable claims.
  - Similarity scoring.
  - Control of web tools and network egress.
  - Memorisation probes.
  - A signed audit trail.
  - Policy profiles.
- Unpacked copy: `scratchpad/crs/package/` (session scratchpad).

### Other prior art

- **Malus** (malus.sh) is satire, but it describes the pattern. "Agent A" reads only docs and writes a spec; "Agent B" implements it behind an "isolation firewall". There is no audit trail, which is the joke and the lesson.
- **irl231/clean-roomer**
  - A guard hook blocks forbidden paths and URLs.
  - A term denylist and a vendor-material scanner.
  - A parity report generated from a feature catalogue.
  - A "target bridge" that returns *facts rather than vendor output*. This is the same idea as our verdict channel.
- **bigsnarfdude/agent-clean-room** found six ways information leaks into the clean agent. **Teardown must close all six.**
  1. Git branch name.
  2. Commit messages.
  3. Auto-loaded memory index.
  4. Auto-loaded CLAUDE.md.
  5. Working-directory path.
  6. Model or tool descriptions.
- **blasterpal/cleanroom:** a Docker workspace with only selected inputs mounted.
- **chardet 7.0** (Willison)
  - The rewrite started from an empty repo with an instruction "not to use LGPL code", yet Claude read `metadata/charsets.py` anyway.
  - JPlag gave a maximum similarity of 1.29%, versus 80–93% between real versions.
  - Pilgrim's objection was about the maintainer's exposure to the original, not the similarity number. Fontana later found no LGPL obligation established.
  - **Lesson: evidence that access was controlled is what persuades. Prompts and low similarity scores do not.**

## 2. Enforcing the barrier around agents

### Limits of Claude Code (primary docs)

- **The sandbox covers Bash only.** File tools, MCP servers and hooks run outside it, and "`allowedDomains` doesn't limit WebFetch".
- **Sandbox keys:** `sandbox.enabled`, `failIfUnavailable`, `allowUnsandboxedCommands:false`, `network.allowedDomains`/`deniedDomains`/`strictAllowlist`, `allowManagedDomainsOnly`, `filesystem.denyRead`/`allowRead`.
  - The proxy filters by hostname and does not inspect TLS.
- **Permissions**
  - A bare deny of `WebSearch`, `WebFetch` or `mcp__*` removes the tool from the model's context entirely.
  - `WebFetch(domain:…)`, `Read(//abs/**)`, `disableBypassPermissionsMode:"disable"`.
  - `/etc/claude-code/managed-settings.json` has the highest precedence.
- **Agent SDK**
  - `disallowedTools`, an explicit `allowedTools`, and `permissionMode:"dontAsk"`.
  - A hook deny wins even in bypass mode.
  - `settingSources` controls whether CLAUDE.md and settings are loaded **[unverified]**.

### Clean-zone layers, strongest first

1. **Separate VM or rootless container under its own OS user.**
   - No `$HOME` mounts, no host pasteboard, its own browser profile.
   - A fresh `CLAUDE_CONFIG_DIR` for each session, which closes leak channels 3 and 4.
2. **Default-deny egress at the network layer.**
   - Allow only the model API, a registry mirror and the gate MCP.
   - Use iptables/ipset (as in Anthropic's devcontainer `init-firewall.sh`) or a Squid/Envoy allowlist.
   - The target's domains, its docs, app-store pages and search engines are unreachable.
3. **Bare-deny the web tools.** On the raw API, never pass server-side web_search or web_fetch. Use `dontAsk` with a fixed tool list.
4. **Registry mirror** (Verdaccio or Artifactory) that blocks the target's own packages, SDKs and assets, plus codename typosquats. Re-check the lockfile.
5. **Repo hygiene:** a fresh `git init` with no remotes, neutral branch names, and commit messages linted against the denylist.
6. **Server-side authorisation in the clean MCP.**
   - It returns only gate-released objects and logs every call.
   - Its server name, tool descriptions and errors stay free of the real name (closing channel 6).
   - The dirty MCP is never registered in the clean zone.

- **Codename the target.**
  - Use a random word pair and a neutral vocabulary for product nouns.
  - The mapping stays on the dirty side and feeds the hidden denylist.
- **Two model providers?** This does little against memorisation, since both trained on the web. It does give separate accounts, memory and caches, which reads well in an audit. At minimum, use separate keys and organisations.

## 3. Sanitizer pipeline (run on every spec release and ticket answer)

1. **Reference corpus** (dirty side) of every observed string: DOM and accessibility text, toasts, HTTP bodies, binary strings, help text.
2. **Exact-match check.** Use a suffix automaton or suffix array to find the longest common substring between spec and corpus. Flag 8 or more tokens.
3. **Near-match check.** Winnowing (MOSS; Schleimer–Wilkerson–Aiken 2003) over 5-word k-grams, plus MinHash/LSH via `datasketch`, flagging Jaccard ≥ 0.5.
4. **Distinctiveness score instead of a length cutoff.**
   - Combine Zipf frequency (e.g. `wordfreq` **[unverified API]**) with length.
   - Common strings of three words or fewer pass, as short phrases under the merger and scènes-à-faire doctrines (37 CFR 202.1(a)).
   - Rare strings, or sentences of four or more words, need a quote entry.
5. **Quote ledger entry:** `{literal_id, text, claim_ids[], compat_reason ∈ protocol|file-format|public-api|error-code|accessibility-name|test-oracle|user-required, merger_basis?, approved_by}`.
   - Each profile has a cap on count and on total characters.
   - Literals may appear only in quote-tagged fields.
6. **Identifier denylist**, filled automatically: CSS classes, JS globals, source-map module names, non-public API path segments, internal event names, and the brand-to-codename map. It is enforced through hooks the model never sees.
7. **LLM judge.**
   - Classifies each claim and literal as function vs expression, and flags anything more specific than the behavior requires.
   - Runs in a fresh context with no evidence access, ideally on a different model from the observer.
   - **Advisory only.** It routes items to a human.
8. **Asset similarity.**
   - `imagehash` pHash/dHash and Meta's PDQ (Hamming ≤ 31 **[unverified threshold]**).
   - Chromaprint for audio.
   - An exact-digest check against captured assets.
9. **Post-hoc code similarity of the clone.**
   - Web: beautify the original bundles and the clone's build the same way, then run Dolos (tree-sitter + winnowing) and JPlag. Also compare CSS custom-property and class vocabularies.
   - Native: overlap of string tables and of import vocabularies.
   - SourcererCC and NiCad apply only when source is available.
   - **Record the score; don't rely on it** (chardet).

## 4. Memorisation and contamination risk

### Research

- Extraction: Carlini et al. 2021 (arXiv 2012.07805); Nasr et al. 2023 (2311.17035).
- Memorisation grows with model size, data duplication and prompt length (Carlini et al., ICLR'23, 2202.07646).
- Code models:
  - Al-Kaswan et al. (ICSE'24, 2312.11658) extracted 47% of the samples judged potentially extractable from CodeGen-16B.
  - Yang et al. (ICSE'24, 2308.09932).
  - LiCoEval (ICSE'25, 2408.02487) found 0.88–2.01% of outputs "strikingly similar".
  - "SWE-Bench Illusion" (2506.12286): models identify repository file paths from the issue text alone up to 76% of the time. **This is a template for our identification probe.**
- Min-K% Prob membership inference (2310.16789 **[unverified ID]**).
- **GEMA v OpenAI** (LG München I, 42 O 14139/24, 11 Nov 2025): memorisation counted as reproduction.

### Probes (results are recorded in the attestation)

- **(a) Identification:** given the sanitised spec, does the model name the product, vendor or URL? Run at temperature 0 and with 5 samples.
- **(b) Completion:** truncate 20–50 distinctive strings or identifiers at 50%, then measure exact-continuation rate and edit distance against controls from a never-published synthetic app.
- **(c) Structural:** ask for the "likely file layout or module names" and compare them with bundle and source-map names.
- **(d) Differential:** run the same probes on a second model family.
- **(e) Canaries:** plant invented field names in the spec and confirm they appear in the clone. This shows it was built from the spec.

**If probes fire:** paraphrase more, strip distinctive taxonomy, switch the implementer model, or lower the literal allowance. **Never claim "clean".** Record "probe score X, mitigations Y".

**What persuades an opponent:** contemporaneous proof that the clean agent *could not* reach the target (egress logs, image digests), the exact spec that crossed the barrier, the full verdict and ticket logs, probe results, independent similarity reports, and reviewer sign-offs. Instructions in prompts count for roughly nothing.

## 5. Audit log

- **Adopt REA's model.**
  - `ev_<sha256(canonical semantic projection)>`, tamper-checked when parsed.
  - Canonical bundles.
  - `evidence_links[]` forming a graph.
  - Unknowns with `previous_revision_digest`.
  - Content-address claims, specs and verdicts the same way.
- **Log format:** append-only JSONL of DSSE-signed in-toto Statements, each carrying `prev` (the digest of the previous entry), with periodic Merkle checkpoints (Rekor v2 / rekor-tiles self-hosted, or a simple Merkle tree).
- **Anchor only the checkpoint roots externally**, via an RFC 3161 TSA or public Rekor. Don't publish the entries themselves: they reveal identities and timing.

### Predicates (`https://teardown.dev/attestation/<type>/v0.1`)

| predicateType | subject | key fields |
|---|---|---|
| `observation-session` | evidence bundle digest | `observer{agent, model, provider}`, `tools[]{name, version, digest}`, `target{codename, identity_digest_sealed}`, `legal_basis`, `account_mode`, `env{isolation, image_digest}` |
| `spec-release` | sanitised spec digest | `inputs[]` (digests only, SLSA-style), `profile`, `prev_spec`, `sanitizer{version, checks[]{name, result, max_overlap}}`, `quotes{count, chars, ledger_digest}`, `judge{model, flagged[]}`, `review{reviewer_id, kind, decision, signed_at}` |
| `clean-session` | clone commit digest | `implementer{agent, model, provider, account}`, `image_digest`, `egress_policy_digest`, `deny_rules_digest`, `mounted_inputs[]`, `probes{ident, completion, canary}`, `transcript_digest`, `no_target_access{egress_log_digest, blocked_attempts}` |
| `verdict` (or in-toto test-result) | clone build + suite digest | `claim_ids[]`, `results[]{claim, pass\|fail\|inconclusive, symbols}`, `literal_policy`, `noise_calibration` |
| `similarity-report` | clone digest | `tool`, `max_scores`, `thresholds`, `verdict` |

- **Verification** of the chain is a policy over linked digests, like a SLSA VSA.
- **Signing keys**
  - The dirty-zone key signs `observation-session` and `spec-release`.
  - The human reviewer signs with Sigstore keyless or SSH.
  - The clean-runner key is held by infrastructure, not the agent.

## 6. Gate workflow

- **Stages**
  1. Automated checks.
  2. An LLM sanitizer in a fresh context, with no evidence access, rewrites flagged items.
  3. A human reviews every flagged item.
     - Substitute profile: the human signs every release.
     - Interop profile: sampled review, plus a signature on any new literals.
- **Review UI**
  - Claim-level semantic diff between spec versions.
  - Each literal shown with its origin, overlap and distinctiveness.
  - A quote-budget meter.
  - Per claim: approve, rewrite, drop or escalate, with a reason code.
- **Tickets**
  - The gate classifies each ticket as behavioral or expression-seeking. "What's the exact text?" is rejected unless a compatibility reason applies.
  - The observer answers with new claims, which pass through the gate again.
- **Verdict sanitisation for `verify_against_original`**
  - **Returned:** claim ID, pass/fail/inconclusive, step index in the abstract trace, and expected vs observed *symbols* (e.g. `ERROR_SHOWN(kind=validation, target=@field2)`).
  - **Never returned:** original-side literals (unless already an approved quote), screenshots, DOM, response bodies, timings or byte lengths.
  - Clone-side outputs may be echoed.
  - **Close the equality oracle.** Unquoted text is compared only by abstract class (present/absent, language, length bucket); otherwise text could be recovered by repeated guessing.
  - Per-session call budget, deduplication and rate limiting; every call logged.

## 7. Policy profiles

| Profile | What it allows |
|---|---|
| **interop / bug-compatible** | Public API, protocol and file-format names, error codes and exact bytes where needed, each with a compat_reason. Bug-compatible claims. Bigger quote budget, sampled human review, literal verdicts for protocol claims. Basis: EU Art 5(3)/6, *Google v. Oracle*. |
| **substitute (strict)** | No UI copy beyond common short labels; no layout measurements, palettes or icons. New names for internal concepts. A human signs every release. Symbol-only verdicts. Memorisation probes required. Trademark and trade-dress scrubbing, plus a patent warning. |
| **own-legacy migration** | The gate is relaxed; strings, assets and source may pass. The audit trail is kept as provenance. Third-party components are still checked. **Relicensing code that has outside contributors is NOT own-legacy (chardet).** A signed ownership declaration is required. |

## Recommended components

1. **`teardown-observe`** (dirty zone): REA-style evidence and claims.
2. **`teardown-gate`** (dirty-zone service):
   - corpus builder;
   - suffix-automaton matcher;
   - winnowing + datasketch;
   - distinctiveness scoring;
   - quote ledger;
   - automatic denylist and codename map;
   - LLM judge;
   - human review UI;
   - ticket router;
   - verdict abstractor with budgets;
   - DSSE signer.
3. **`teardown-clean`** (clean-zone MCP with server-side authorisation): `get_spec`, `ask_question`, `verify_against_original`.
4. **Clean runtime:**
   - VM or rootless container under its own OS user;
   - fresh `CLAUDE_CONFIG_DIR`;
   - managed settings that deny the web tools and set `disableBypassPermissionsMode`, the sandbox on, `failIfUnavailable` and `allowUnsandboxedCommands:false`;
   - SDK `dontAsk` with a fixed tool list;
   - iptables allowlist, Verdaccio block list;
   - fresh repo, commit lint.
5. **Audit:** the hash-chained DSSE log with the 5 predicates, checkpoints anchored externally, and probe and similarity reports attached.

**Schemas to write first:** `Claim`, `QuoteEntry`, `SpecRelease`, `Ticket`, `AbstractVerdict`, and the 5 predicates.

## Residual risks

- The implementer's weights may already contain the target.
- A very detailed spec may itself copy the original's structure, sequence and organisation (SSO).
- Similarity scores can be gamed.
- The verdict oracle can leak a little at a time over many queries.
- The barrier can be misconfigured: the sandbox covers Bash only, the proxy doesn't inspect TLS, and MCP servers and hooks run outside the sandbox.
- Human reviewers may rubber-stamp.
- ToS and contract claims, patents, trademarks and trade dress are untouched.
- The clone may not be copyrightable (Thaler).
