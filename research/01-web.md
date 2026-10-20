# Teardown-web: research report

*Checked against Playwright main docs (v1.64.1, 2026-10-14), the Playwright MCP README (v0.0.83), the Chrome DevTools MCP reference (v1.11.0), WebArena docs, and blobless clones of the candidate evaluation repos (file counts are my own). **[unverified]** marks the rest. Collected 2026-10-19.*

## 1. Actuation stack

**Recommendation:** embed **Playwright for Python** (v1.64+) as a library inside `teardown-observe`.
- Add a raw CDP session only where Playwright has gaps: the full AX tree via `Accessibility.getFullAXTree`, and JS coverage used purely to steer exploration.
- **Do not wrap Playwright MCP or Chrome DevTools MCP.**
- Treat WebDriver BiDi on Firefox as experimental; it reached Mozilla milestones M19/M20 in 2026.

**Why not wrap the existing MCPs**
- **Playwright MCP** returns a full accessibility snapshot after every action. It is aimed at an LLM, is Node-only, and its own README steers coding agents toward `playwright-cli` because of token cost.
- **Chrome DevTools MCP**
  - Console messages come with source-mapped stack traces, and it exposes heap snapshots. Both leak implementation.
  - **Usage statistics are on by default** (`--no-usage-statistics`), and performance tooling can send trace URLs to CrUX (`--no-performance-crux`). Both leak the target's identity.
- Keep `Browser.bind()` (v1.59) so a human can attach to the observer's browser for debugging.

**Python vs Node.** Python has `aria_snapshot(mode="ai", depth, boxes)`, `to_match_aria_snapshot`, `clock`, `route_web_socket`, `route_from_har`, `storage_state(indexed_db=True)`, `console_messages()`, `requests()` and `get_by_ref`.
- JS-only: `ariaSnapshotJSON` (v1.63), so Python must parse YAML; file-based aria snapshots; the test runner and MCP.
- None of these blocks Teardown.

| Surface | Playwright | Gap or fallback |
|---|---|---|
| Accessibility tree | `ariaSnapshot` YAML: role, name, `[checked, disabled, expanded, invalid, level, pressed, selected]`, placeholder. `ai` mode adds refs and iframes. | No `required`, `readonly`, `valuemin`/`valuemax` or `autocomplete`. Use CDP `getFullAXTree` or DOM attributes. |
| DOM | `content(includeShadow=True)` (v1.64); locators pierce open shadow DOM. | **Closed shadow roots are unsupported.** |
| Network | `recordHar` (`content: omit/embed/attach`), `tracing.startHar`, WebSockets in HAR (v1.61), `route`, `routeFromHAR(notFound, update)`, `page.requests()`. | **HAR replay doesn't cover requests made by service workers.** Use `serviceWorkers:'block'`. |
| WebSockets | Frames via the `websocket` event; `routeWebSocket` | |
| Console / errors | `consoleMessages`, `pageErrors`, service-worker console | |
| Storage | Cookies, `localStorage` / `sessionStorage` (v1.61), `storageState` with IndexedDB, passkeys (v1.62) and OPFS (v1.63), `setStorageState` | |
| Service workers | Network and routing (Chromium) | |
| Downloads, dialogs | `download`, `dialog` / `dialogClosed` (v1.63) | |
| Clipboard, permissions | `grantPermissions`; headless clipboard isolated (v1.62) | |
| Tabs, popups | `context.on('page')`, `popup` | |
| iframes | `frameLocator()` with no argument searches all frames (v1.63) | |
| Canvas / WebGL | Accessibility tree empty | See §8 |
| WebMCP | `page.webmcp.tools()` (v1.64) | A published interface; treat it like an API |

## 2. State abstraction

**Prior art.**
- Crawljax: DOM edit distance plus noise-stripping comparators that need tuning per app.
- Yandrapally & Mesbah: 97.5k labelled pairs showing that threshold comparators generalise badly (FragGen arXiv 2110.14043, WebEmbed arXiv 2306.07400).
- APE: refinement from counterexamples.
- WebTestPilot: symbols plus pre/postconditions. Useful for *claims*, not for deciding state identity.

**Proposed state key: `S = (route_tmpl, overlay_stack, auth_role, H_aria, form_vec)`**
1. **`route_tmpl`** — the URL path as a template. ID-like segments (UUIDs, numbers, slugs that take several values) become parameters, as mitmproxy2swagger does. Query string keeps only its keys, sorted.
2. **`overlay_stack`** — the open `dialog`, `alertdialog`, `menu` and `listbox` elements, as roles with masked names.
3. **`H_aria`** — a sha256 of the canonicalised aria snapshot (`ai` mode, refs dropped):
   - Keep the role, the state attributes, and the names of interactive elements and of h1/h2 headings.
   - Replace other text with a type token: NUM, DATE, MONEY, EMAIL, UUID, URL, SHORT or LONG.
   - Collapse repeated sibling subtrees to `role×{0|1|many}`.
   - Apply the calibrated noise masks.
4. **`form_vec`** — per control: its validity flag, whether it is empty, and whether it is disabled.

**Refinement**
- **Split.** If the same `(S, action)` leads to two different successors in at least 2 of N runs, and noise doesn't explain it, add back the cheapest field that tells them apart. Try, in order: list count, a heading's text, whether a storage key exists, a field of the last API response.
- **Merge.** Merge two keys that produce identical outputs for k steps.
- **pHash** of the screenshot is used only for canvas or when the accessibility tree is degenerate.
- The LLM *names* states. It never decides whether two states are equal.

## 3. Determinism and reset

**Client side**
- Pinned Playwright Docker image (fonts).
- Fixed `timezoneId`, `locale`, `viewport`, `deviceScaleFactor`, `colorScheme` and `reducedMotion`.
- `page.clock.install` / `setFixedTime` fakes `Date`, `Temporal.Now`, timers, `requestAnimationFrame` and `performance`.
- An `addInitScript` seeds a PRNG for `Math.random`, `getRandomValues` and `randomUUID`. Use this on the dirty side only.
- A fresh context per episode.

**Freezing the backend**
- Record a HAR, then replay it with `routeFromHAR(notFound='abort')`.
- HAR matching reportedly also checks the POST body **[unverified]**, so bodies containing nonces break replay. Fix this with a custom `route` handler that matches on the path template plus a masked body. Meticulous stubs network, time and performance the same way.

**Server time.** On self-hosted targets, run the backend under libfaketime `LD_PRELOAD`. This does not work for static Go or vDSO time reads. On SaaS, treat time-dependent behavior as an explicit unknown.

**Reset options**

| Target | Mechanism | Fidelity |
|---|---|---|
| Self-hosted, compose | Volume/fs snapshot (ZFS/btrfs, `docker commit`) or Postgres `CREATE DATABASE … TEMPLATE`, plus restarting caches and queues | **High**, seconds to a minute |
| WebArena-style | `docker rm` and re-run the populated images | High, but minutes, so too slow for L\*. Put DB snapshots underneath |
| Remote SaaS | A fresh tenant per run, unique prefixes, cleanup, a pool of accounts | **Low–medium.** Rate counters, onboarding flags, sent emails, A/B buckets, recommendation history and audit logs can't be reset |

**Detecting a failed reset**
1. **Reset fingerprint:** the states of K canonical pages plus normalised GET responses must match a golden copy.
2. **Sequence witness:** a newly created entity's ID must equal the value seen after the first reset.
3. **Cross-episode canary:** a marker written in episode i must be gone in episode i+1.

Any failure is reported to the learner as nondeterminism.

## 4. Frontend vs backend behavior

**Each claim is tagged `layer: client | server | both`, decided by a three-way comparison:**
1. UI against the live backend.
2. UI against a HAR-frozen backend. Behavior that survives is client-side.
3. Direct API replay with mutated inputs:
   - rejected before any request is sent → client;
   - request sent, response 4xx → server;
   - both → two separate claims. **If the two disagree, that is a finding in itself.**

**Recovering the API contract**
- mitmproxy2swagger (HAR → OpenAPI 3, two passes) as the baseline.
- Optic (Atlassian since 2024; CLI is open source) to diff spec versions and verify the clone.
- Postman Insights (Akita, eBPF on the server host) is self-hosted only, and redundant there.
- Feed the result to Schemathesis.

**GraphQL**
- Use introspection when it is enabled. It is often off in production; Apollo's default with `NODE_ENV=production` is off **[unverified]**.
- Otherwise, build the schema from observed operations.
- Automatic persisted queries reveal only operation shapes.
- Recovering schema from "did you mean" suggestions (Clairvoyance) is a grey area. Allow it on self-hosted targets only.

**Legal posture (not legal advice)**
- Van Buren: the CFAA question is a "gates-up-or-down" test.
- Meta v. Bright Data (2024): logged-out scraping wasn't bound by the ToS, which implies logged-in use is.
- Teardown always runs logged in, so the ToS applies as a contract.
- **Policy:**
  - Direct API probing only on self-hosted or OSS targets, or where the ToS allows API use.
  - Otherwise: UI-only probing, no bulk mutation, honour rate limits, and keep a ToS snapshot from intake.

## 5. Where the clean-room line falls on the web

The rule: **what the shipped artifact presents at its interfaces is behavior; how it computes that is implementation.**

**Tier A — behavior; allowed in claims**
- The accessibility tree and visible text, tagged for expression risk.
- Form-control attributes: `type`, `required`, `pattern`, `min`, `max`, `step`, `minlength`, `maxlength`, `accept`, `multiple`, `autocomplete`, `inputmode`, `novalidate`.
- `element.validity`. The `validationMessage` text comes from the browser, not the target.
- URLs and routes.
- Request/response *shapes*, status codes and ordering.
- Cookie and storage keys and lifetimes.
- Download file formats, timing, and WebMCP tool schemas.

**`pattern` is the hard case, because the attribute is a literal regex.**
- The claim records the *accepted language*, corroborated by boundary and Arvada probes.
- The attribute itself is kept as evidence. Copy the regex into the JSON Schema only when functionally necessary (merger doctrine).
- **A missing attribute never means "no validation".** JavaScript-only validation is found by probing.

**Tier B — steering only, quarantined**
- DOM structure, class names and `data-testid`s.
- CSS and visual layout.
- JS coverage via CDP.
- Stack traces and framework devtools hooks.

**Tier C — excluded at capture time**
- JS, CSS, WASM and source-map bodies. Record HAR with `content:'omit'` for those types.
- `<script>` and `<style>` elements, stripped from DOM evidence.
- Heap snapshots, `evaluate` against app globals, and deobfuscation.
- `evaluate` is allowed only for allow-listed probe functions such as reading validity, computed role, or the bounding rect.

## 6. Conformance testing, original vs clone

**Locators**
- Abstract steps name semantic IDs. Each side keeps an adapter map from semantic ID to locator: the dirty side builds the original's, the clean implementer writes the clone's.
- Locators default to `getByRole(role, name)` scoped by landmark, with `Locator.within` (v1.64).

**Oracles**
- The §2 abstract key.
- Claim predicates over symbols.
- The API trace, normalised against the inferred OpenAPI.
- `toMatchAriaSnapshot` with `/children: contain` and regexes.
- Pixel diffs are advisory only.

**"Frontend under a frozen backend."** If the clone implements the same OpenAPI, one HAR can drive both frontends. Penpot's own suite works this way, with 67 UI specs against 285 mocked RPC fixtures.

**Noise.** Three-way Diffy (opendiffy): a difference counts only if the clone differs from original-A on a field that is stable between original-A and original-B.

**Hidden ground-truth tests are written against the original's DOM.**
- RealWorld's `specs/e2e/SELECTORS.md` is an explicit contract of CSS classes, `name`s, placeholders and labels.
- Report both a **raw** score (tests unmodified) and an **adapted** score (a third-zone harness rewrites selectors to the clone's map).
- Alternatively, admit published test IDs as compatibility claims with a `compat_reason`.

## 7. Evaluation targets

| Target | Hidden suite | Running it locally |
|---|---|---|
| **RealWorld / Conduit** | `specs/e2e`: 12 Playwright files, **128 tests** (31 on errors, 5 XSS); also 172 Bruno + 15 Hurl API files and `openapi.yml` | Easy, with many front/back pairs. **Best first full target**, and it comes with an API oracle |
| **TodoMVC** (cypress-example-todomvc) | 1 file, **32 tests** | Trivial, client-only. Milestone 1 |
| **Actual Budget** | 24 Playwright files | Easy; local-first, one container |
| **Ghost** | 79 admin E2E + 139 e2e-api files | Medium |
| **Mattermost** | **391 Playwright + 621 Cypress** spec files | Medium; large realtime surface |
| **Cal.com** | 53 Playwright files | Medium-hard; timezone-heavy |
| **Rocket.Chat** | ~180 E2E files | Hard (Meteor + Mongo) |
| **Element Web** | 158 Playwright files (harness spins up Synapse) | Medium-hard; realtime + E2EE |
| **Penpot** | 67 Playwright files with mocked RPC | Medium; canvas/SVG |
| **tldraw** | 35 example E2E files | Easy; canvas probe |
| **WebArena** | 812 tasks with evaluators | Hard: ~1 TB, AMI recommended, reset takes minutes |

**Weak oracles:** Excalidraw (~143 vitest/jsdom unit tests, no browser E2E), Plane (Python API tests only), Docmost (component tests only).

## 8. Hard limits

- **Auth and MFA:** a human authenticates once and the session is seeded into `storageState`. WebAuthn can be seeded on controlled targets (`context.credentials`, v1.61).
- **CAPTCHA and bot detection (e.g. Turnstile): never bypass.** If a challenge is detected, end the session and mark the target out of scope. Headless fingerprints trigger these more often.
- **Rate limits:** the budget is set at intake, with backoff on 429. A rate limit is itself a `refusal` claim.
- **Legal:** logged-in ToS binds. Art. 5(3) helps for licensed software; how it applies to SaaS is unclear **[unverified]**.
- **Canvas, WebGL and WASM apps**
  - Fallbacks: the app's own serialisations (export, clipboard, IndexedDB scene), sync and WebSocket payload shapes, masked visual hashes, coordinate actions.
  - Expect low spec recall. Penpot and tldraw sit in between.
- **Realtime collaboration:** two or more contexts in lockstep, `partial-order` claims, WebSocket replay, and stochastic learners.
- **Server-side ML features:** only invariants can be claimed (shape, latency class, refusals); the rest are unknowns.
- **A/B flags:** pin the account and cookie bucket, detect drift with the reset fingerprint, and record flag state as part of the target's identity.

## Decisions

- **Driver and capture**
  - Embed Playwright for Python on Chrome for Testing, with CDP only for the full AX tree and JS coverage (steering).
  - If Chrome DevTools MCP is ever used, always pass `--no-usage-statistics --no-performance-crux`.
  - Filter at capture time: HAR omits code bodies, DOM evidence has no `<script>`/`<style>`, and `evaluate` is allow-listed. Tiers A/B/C are encoded in the evidence schema.
- **State and claims**
  - State key `(route_tmpl, overlay_stack, auth_role, H_aria, form_vec)`, with Diffy masks and APE-style split/merge.
  - Every claim carries `layer: client|server|both`, decided by the three-way probe.
- **Determinism and reset**
  - Default profile: clock install, seeded PRNG, fixed timezone/locale/viewport, `serviceWorkers:'block'` during replay, pinned image.
  - Self-hosted reset uses DB/fs snapshots checked by fingerprint, witness and canary.
  - SaaS runs in **limited-reset mode**: no L\* on mutating flows, and low-confidence claims.
- **Conformance:** semantic-ID adapters, abstract-observation diffs, three-way Diffy, and "frontend under frozen backend" whenever the clone shares the OpenAPI.
- **Evaluation ladder:** TodoMVC → RealWorld → Actual or Ghost → Mattermost or Cal.com, with tldraw or Penpot as the canvas stress test. Report raw and adapted pass rates.
- **Intake:** ToS snapshot, self-hosted vs SaaS mode, a challenge detector that aborts, and a rate budget.

## Risk

| Scope | Feasibility | Why |
|---|---|---|
| **Overall** | **Medium** | — |
| Self-hosted CRUD and forms (RealWorld, TodoMVC, Actual, Ghost) | **High** | Playwright covers every surface, reset can be exact, hidden suites exist |
| Large realtime apps (Mattermost, Element, Cal.com) | **Medium** | — |
| Remote SaaS, canvas, ML-heavy | **Low** | Low reset fidelity, bot protection and ToS, uncontrollable server time, empty accessibility tree. **The main risk is legal and contractual, not technical** |
