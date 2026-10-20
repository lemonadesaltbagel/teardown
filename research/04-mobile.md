# Teardown-mobile: research report (Android + iOS)

*Machine checked read-only: Apple M4, macOS 26.6.2, 151 GB free, OpenJDK 27, Homebrew, Node, Python 3.15. Only the Xcode Command Line Tools are present (no Xcode.app, so no simctl or XCUITest). No adb, no emulator. Nothing was installed. **(unverified)** marks claims I did not check. Collected 2026-10-19.*

## 1. Android: driving and observing apps

### Driver options

- **ADB primitives**
  - Commands: `input tap/swipe/text/keyevent`, `screencap`, `screenrecord` (3-minute limit), `am start`, `dumpsys`.
  - REA already wraps the read side and lifecycle (`refs/rea/docs/adb-device-analysis.md`). It has **no UI-hierarchy dump and no input injection.**
- **`uiautomator dump`**
  - Dumps the AccessibilityNodeInfo tree as XML. It is slow (1–3 s).
  - It fails with "could not get idle state" when the screen keeps animating (unverified).
  - It drops "non-important" nodes.
- **openatx `uiautomator2`** (Python, ~8.4k stars, actively maintained) — **the best primitive for a Python MCP.**
  - `dump_hierarchy(compressed, max_depth)`, toast capture, popup watcher.
  - Android 4.4+.
- **Appium UiAutomator2 driver + appium-mcp**
  - Tools include `get_page_source`, `generate_locators`, `gesture` and `generate_tests`. Needs Node 22+ and a JDK.
  - One protocol for both Android and iOS.
  - **Only one UiAutomation connection at a time** (unverified).
- **Espresso** runs instrumented inside the app's process, which is white-box. **Keep it out of the observer.** Its test suites are useful only as hidden ground truth.
- **Accessibility-service approach**
  - DroidRun, now Mobilerun (MIT), uses a "Portal" a11y app and claims 91.4% on AndroidWorld.
  - AndroidWorld itself uses an a11y forwarder over the emulator's gRPC 8554.
- **mobile-mcp** (v0.0.59): accessibility-first, with screenshot and coordinate fallback, for Android, iOS Simulator and real iOS devices.
- **Recommendation:** use mobile-mcp and appium-mcp only as references or temporary backends, and own the abstraction layer. None of them does state hashing, probing or claims.

### Hierarchy quality by framework

| Framework | What the a11y tree gives |
|---|---|
| Views (XML) | Good: class, text, content-desc, resource-id, bounds, flags |
| **Jetpack Compose** | Semantics only. **resource-id is empty unless `testTagsAsResourceId=true`**, which release builds rarely set. Single-activity, so activity coverage is meaningless. |
| **Flutter** | A semantics tree only when the OS reports a11y is enabled (flutter#21140). Labels are often merged. |
| React Native | Native views, so good. `testID` maps to resource-id. |
| **Unity / games** | **No tree.** Unity 6 needs a hand-built hierarchy. Vision only. |
| WebViews (release builds) | Partial a11y. No CDP, because `setWebContentsDebuggingEnabled` is off. |

### Other surfaces

- **Notifications:** `dumpsys notification --noredact`. Toasts arrive as a11y events.
- **Deep links and intents:** `pm get-app-links` (Android 12+), `dumpsys package`, `cmd package query-activities -a VIEW -d <uri>`.
  - These are the **app's public interface as the OS reports it**, so they are allowed as interface facts.
  - Component class names are implementation detail: they stay on the dirty side and go to the denylist.
- **Logcat** is split:
  - **System events are behavior:** activity starts, process death, FATAL EXCEPTION as a yes/no, ANR, permission dialogs.
  - **App-tagged text is implementation leakage.** It stays in raw evidence, goes to the gate's n-gram and identifier denylist, and never supports a claim.
- **FLAG_SECURE** (black screenshots) is a protection measure. **Respect it**: observe the a11y tree only and record an unknown.

## 2. iOS

### Tools

- **XCUITest through WebDriverAgent** (Appium XCUITest driver) can drive any installed app by bundle ID, App Store apps included.
- **idb:** `ui describe-all`, Simulator-focused. It lags new Xcode releases (unverified).
- **simctl:** `erase`, `openurl`, `push`, `privacy`, `status_bar override`, `location`, `ui appearance`, `keychain add-root-cert`.

### Hard constraint: FairPlay

- App Store IPAs are FairPlay-encrypted device builds, so **the Simulator cannot run them.** On the Simulator, only apps built from source work, which in practice means open-source evaluation targets.
- **Third-party apps need a real device** with WDA signed by an Apple ID.
  - Free accounts: 7-day profiles, 3 devices. Paid: $99/yr.
  - appium-mcp has `appium_prepare_ios_real_device`.
- **Resetting a real device is weak.**
  - Uninstall and reinstall works, but **the Keychain survives app deletion** (unverified).
  - There are no snapshots, and a full erase takes minutes.

### "Designed for iPad" apps on an Apple Silicon Mac

- They run unmodified. UIKit accessibility is bridged to NSAccessibility, so **the desktop AX driver should see their trees** (unverified; test each app).
- **Caveats:**
  - Developers can opt out, and many big ones did: Google, Meta, Netflix, Disney+, banks.
  - The app knows it is on a Mac (`isiOSAppOnMac`), so claims must be tagged `platform: ios-on-mac`.
  - Installs come from the Mac App Store only.
- Reset is easy: uninstall and clear `~/Library/Containers/<bundle>`.
- **This is a cheap opportunistic path that reuses the desktop backend.**

## 3. Network observation and certificate pinning

### Android

- Since Android 7, apps targeting API 24+ **trust only system CAs** (NCC Group), so a user CA shows almost nothing.
- **System-CA route:**
  - Use a rooted `google_apis` emulator image (not `playstore`).
  - On API 34+, the CA store is the immutable `/apex/com.android.conscrypt/cacerts`. Bind-mount a tmpfs into the zygote and app namespaces (HTTP Toolkit).
  - **This changes your own device's trust store, not the app.** Apps that don't pin will then accept the proxy.
- **Without decryption** you still get metadata: `emulator -tcpdump` or proxy CONNECT logs give host, SNI, timing, bytes and cadence.

### iOS

- A user root with "full trust" enabled is accepted by non-pinning apps (unverified per app). No jailbreak is needed, so **iOS is easier than Android here.**

### Pinning bypass is forbidden

- Bypass methods include Frida or objection hooks, repackaging with a modified `network_security_config` (which breaks the signature), and Xposed or Magisk modules.
- **Two reasons to forbid it:**
  - **Legal.** Pinning is arguably a technical protection measure under DMCA §1201, and the security-research exemption (37 CFR 201.40) does not cover building a competitor. The EU has similar rules: InfoSoc Art. 6 and Software Directive Art. 7(1)(c). This is a legal reading, not advice.
  - **Clean room.** Finding the pinning code usually means decompiling, and hooking it alters execution.

### Network policy (set at intake, enforced by the MCP)

| Tier | What is allowed |
|---|---|
| **N0** | UI only |
| **N1** (default) | Network metadata: pcap, SNI, timing |
| **N2** | TLS interception through the device trust store only, on a device you own, without touching the app |
| **Forbidden** | Frida, objection, repackaging, Xposed, and bypassing pinning, root detection, attestation or FLAG_SECURE |

- **If an app fails under the proxy** (detected by comparing against a run without it): turn interception off for that host, record `unknown: network.payload(<host-codename>)`, and fall back to UI, timing and side-effect claims.
- **The proxy perturbs behavior**, so calibrate noise with and without it.

## 4. Reset and isolation

### Emulator on this Mac

- **Native arm64-v8a images under Hypervisor.framework run at near-native speed. Use these.**
- **Docker emulators don't work here:**
  - budtmo/docker-android is "Ubuntu only", needs `/dev/kvm`, and ships amd64 images.
  - Google's android-emulator-container-scripts need Linux x86_64 with KVM; Docker Desktop on Mac is unsupported.
  - Docker Desktop doesn't expose KVM even on an M4 with nested virtualization (unverified).
- **Architecture:**
  - The emulator runs on the host, inside the dirty zone.
  - The containerized observer MCP connects through adb over TCP (`host.docker.internal`).
  - The clean container has no route to adb.
  - On Linux CI, use the KVM containers.

### Reset ladder

| Method | Approx. time | What it resets |
|---|---|---|
| `am force-stop` | ~0 s | Nothing persistent; data is kept |
| `pm clear <pkg>` | ~1 s | App data, and runtime permissions (unverified) |
| Uninstall + install | seconds | The app fully. Note `adb install -r` *keeps* data, so it is not a reset |
| `adb emu avd snapshot load <name>` | ~2–10 s (unverified) | The whole device |
| `-wipe-data` cold boot | 30–60 s | Everything |

**Recommendation:**
- One golden snapshot per intake: logged in, settings pinned, CA installed.
- `pm clear` for app-only probes, snapshot load for L\* resets.
- `-read-only` AVDs for parallel instances.

### Attestation

- **Play Integrity gives emulators no device verdict.** `MEETS_VIRTUAL_INTEGRITY` is limited to Play Games on PC.
- ARAP (arXiv 2408.11080) found **about 25% of popular apps detect virtual environments.** Banking, finance, games and streaming apps are the most likely to.
- **You usually get attestation or traffic, not both:**
  - A `google_apis` image is rootable and allows CA injection, but fails attestation.
  - A `playstore` image is not rootable and still fails attestation.
  - A real unrooted phone passes attestation but gives no TLS visibility.
  - This is acceptable under the N1 default.
- **Real devices:**
  - A used Pixel costs about $100–150 and gives adb with no root.
  - Device farms (Firebase Test Lab, AWS Device Farm, BrowserStack) raise issues of third-party custody and ToS.

## 5. Determinism (Android)

| Control | How |
|---|---|
| Animations | Set `window_animation_scale`, `transition_animation_scale` and `animator_duration_scale` to 0 |
| Time | `settings put global auto_time 0` and `auto_time_zone 0`. Setting the date needs root: `adb root; date …; am broadcast TIME_SET`, so use a `google_apis` image. Timezone via `-timezone` or `persist.sys.timezone`. **Re-set the clock after every snapshot load** (whether it resyncs to the host is unverified). |
| Locale | `-change-locale`, or per app on Android 13+: `cmd locale set-app-locales` (unverified syntax) |
| Display | `font_scale 1.0`, `wm density`, `wm size`, `cmd uimode night no` |
| Environment | `adb emu geo fix`, `network delay/speed`, airplane mode, `power capacity` |
| Noise sources | Disable Play auto-update; pin the keyboard (or use `input text`); disable autofill and spellcheck |
| iOS Simulator | `status_bar override`, `location`, `ui appearance`, locale launch args. Real devices offer far fewer controls. |

## 6. State abstraction and exploration prior art

**Classical tools:**
- **DroidBot:** a UTG keyed by view-tree hash. A good baseline structure.
- **Stoat:** a stochastic model.
- **APE:** dynamic abstraction refinement (keep this).
- **Humanoid.**
- **Fastbot2** (ByteDance, ASE'22): a probabilistic event-to-activity model reused across runs, plus RL. Deployed in CI and credited with 50.8% of developer-fixed crashes. **Model reuse fits repeated runs on the original and the clone.**

**LLM-based tools:**
- GPTDroid, DroidAgent, AutoDroid.
- **LLMDroid** (FSE'25) calls the LLM only when coverage plateaus.
- **LLM-Explorer** (arXiv 2505.10593): the LLM holds knowledge while action choice is LLM-free, which is **148× cheaper.**

**Benchmarks:**
- AndroidWorld: 116 tasks across 20 apps, with state-checked rewards.
- AndroidLab: 138 tasks across 9 apps.
- Mobile-Agent-v3 / GUI-Owl: 73.3 on AndroidWorld. 2026 leaderboards claim 90%+ (unverified).
- **Implication:** goal-directed acting is mostly solved. **Systematic probing and specification are the unsolved part.**

**Coverage:**
- **Activity coverage** (`dumpsys activity` topResumedActivity) needs the manifest's activity list as its denominator, and it is meaningless for Compose apps. Activity names are implementation detail, so this is **a dirty-side steering signal only.**
- **Method coverage** (JaCoCo) is allowed **only in the evaluation harness**, on open-source apps.
- **Primary metric:** abstract-screen and transition coverage of the learned automaton.

## 7. Evaluation targets

| # | App | Ground truth | Feasibility |
|---|---|---|---|
| 1 | **Loop Habit Tracker** (iSoron/uhabits) | BDD-style `androidTest/.../acceptance/` (HabitsTest, BackupTest, WidgetTest, steps/), close in shape to claims | **High. Best first target.** Offline and deterministic |
| 2 | **AntennaPod** (GPL-3.0) | Espresso: Preferences, Queue, FeedSettings, AddFeed, NavigationDrawer, DownloadLog | High. Works offline with local feeds |
| 3 | **Omni-Notes** | 15 Espresso tests (NoteLifecycle, Reminders, RecurrenceRule, Category, …) | High. Offline |
| 4 | Wikipedia Android | robots, onboarding | Medium. Needs network; content drifts |
| 5 | **AndroidWorld's 20 apps** | Programmatic state checks for 116 tasks | High. Reproducible |
| 6 | Wikipedia iOS | `WikipediaUITests/` | Medium. Needs Xcode |
| 7 | **Firefox iOS** | 93+ XCUITests, including **`FxScreenGraph.swift`, a hand-written screen graph that serves as ground truth for the UI state machine** | Medium-low. Huge build |

**Avoid:** Thunderbird (no clear UI tests), NewPipe (androidTest is DB-level), Signal (needs phone registration), Fossify (no androidTest found).

## 8. Setup cost on this M4

**Android: about 30–60 minutes to a first loop.**
- **Downloads:**
  - cmdline-tools (mac_arm64): 155 MB
  - platform-tools: 16 MB
  - emulator (darwin_aarch64): 421 MB
  - `system-images;android-34;google_apis;arm64-v8a`: 1.61 GB (API 35: 1.78 GB; API 36: 1.87 GB)
- **Disk:** roughly 10–20 GB in practice (estimate).
- **Steps:**
  1. `brew install --cask android-commandlinetools`. JDK 27 should satisfy the 17+ requirement (unverified).
  2. Run `sdkmanager` for the packages, then `avdmanager create avd`.
  3. `emulator -avd X -no-boot-anim -grpc 8554`.
  4. `pip install uiautomator2`.

**iOS: hours.**
- Xcode is a 3–4 GB download and 10–15 GB installed, plus a 7–9 GB Simulator runtime. Then build WDA.
- Real devices also need an iPhone, Developer Mode and an Apple ID.
- The iOS-on-Mac route needs nothing beyond the desktop AX backend.

## Decisions

1. **Android first.** Native arm64 emulator, driven by `uiautomator2` from Python. Screenshots are evidence only. appium-mcp and mobile-mcp serve as references. Reuse REA's ADB conventions (fixed argv, effect flags).
2. **The observer container talks to the host emulator over adb TCP.** Ship compose files for the macOS host and for Linux CI (KVM).
3. **State hash:** normalized a11y tree (role, text class, enabled/checked, structure; time and counts masked), plus APE refinement. **Never key on resource-id or activity names.**
4. **Semantic abstract actions** (role + label + ordinal), never coordinates. **The spec carries a testability contract: the clone must expose a11y labels and roles for every element the spec names.**
5. **Network tiers N0/N1/N2. Hard-refuse every bypass.** What can't be observed becomes an unknown. Calibrate with and without the proxy.
6. **Logcat** is reduced to system events. App text goes to the denylist only.
7. **Surface metadata** (deep links, intent filters, permissions, notification channels) is allowed, with class names stripped.
8. **Reset:** golden snapshot, `pm clear` and snapshot loads. Re-apply determinism after every load.
9. **Intake gate:** detect FLAG_SECURE, attestation failure, and Flutter or Unity apps with no tree. Then downgrade the coverage promise or reject the target.
10. **Evaluation:** Loop Habit Tracker, Omni-Notes and AntennaPod against their hidden Espresso suites, plus AndroidWorld apps. JaCoCo only in the harness.
11. **iOS:** phase 2 is a Simulator track for open-source apps (Wikipedia; Firefox's screen graph). For third-party apps, try iOS-on-Mac through desktop AX first. A real device plus WDA comes last.

## Risk

| Scenario | Rating | Notes |
|---|---|---|
| **Android, OSS / sideloadable** | 🟢 High | Weak trees (Compose, Flutter, games); nondeterminism after snapshot load |
| **Android, commercial Play apps** | 🟡 Medium | ~25% detect emulators, attestation fails on AVDs, pinning means N0/N1 only, FLAG_SECURE. Expect UI-heavy claim sets with many unknowns |
| **iOS, OSS on Simulator** | 🟡 Medium | Hours of setup; no realistic third-party coverage |
| **iOS, third-party** | 🔴 Low | FairPlay, real-device WDA (7-day free profiles), weak reset, two devices needed for differential runs. iOS-on-Mac is cheap but often opted out and gives Mac-flavoured behavior |
