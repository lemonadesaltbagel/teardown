# Teardown-desktop: research track report

*Covers macOS, Windows and Linux. Items marked **[unverified]** come from secondary sources or are estimates. Spike code is in `spikes/desktop-ax/`. Collected 2026-10-19.*

## 1. Actuation and observation

### macOS

- **The Accessibility (AX) API is the main interface.**
  - Use `AXUIElement` through pyobjc (atomacos and AXSwift are thin wrappers).
  - It exposes role, subrole, title, value, AXIdentifier, enabled, frame and actions.
  - Semantic actions: `AXPress`, `AXIncrement`, `AXShowMenu`, setting `AXValue`.
  - `AXObserver` delivers change notifications.
  - It needs the Accessibility TCC grant.
- **Prefer semantic AX actions over `CGEventPost`.** Synthetic HID events are racy and depend on focus.
  - REA follows the same rules (`refs/rea/docs/native-investigation.md`): AX child-index paths, no global event injection, a guard against PID reuse, and fail-closed on ambiguity.
- **Screen capture (ScreenCaptureKit) needs the Screen Recording grant.** Since Sequoia, macOS re-prompts every month (9to5mac), which breaks unattended runs on a real Mac.
  - In a VM, grant it once when building the image **[unverified for SCK under MDM]**.
- **Existing MCPs:**
  - mediar-ai/mcp-server-macos-use (Swift).
  - mediar-ai Terminator (Rust, "Playwright-style", Windows-first).

### Windows

- **UI Automation (UIA) is the main interface.**
  - Client libraries: pywinauto `backend="uia"`, the `uiautomation` Python package, or FlaUI (.NET, the most robust).
  - Windows-MCP (CursorTouch, MIT) is built on UIA.
- **WinAppDriver has been abandoned since 2021**, though never formally deprecated.
  - The Appium Windows driver still proxies to it. NovaWindows is a community drop-in replacement.
  - Use UIA directly, and keep WebDriver only as an adapter for running existing WinAppDriver test suites.
- **UFO2 (Microsoft, arXiv 2504.14603) is the reference architecture.**
  - It fuses UIA with OmniParser-v2, discarding vision boxes that overlap a UIA control by more than 10% IoU.
  - **62% of its WindowsAgentArena failures were control-detection failures.** LibreOffice is a poor UIA citizen.
  - The hybrid approach recovered 9.9–12.5% of tasks, and a GUI+API "Puppeteer" cut steps by 58.5%.
  - **It isolates the agent in an RDP loopback session, giving an invisible second desktop.**

### Linux

- **AT-SPI2 over D-Bus** (pyatspi, dogtail).
  - GTK works once accessibility is on.
  - Qt needs `QT_ACCESSIBILITY=1` / `QT_LINUX_ACCESSIBILITY_ALWAYS_ON`, otherwise its tree is empty.
- **Input injection depends on the display server.**
  - X11 + Xvfb with XTest/xdotool: unrestricted.
  - Wayland blocks synthetic input. Options are libei through the RemoteDesktop portal (needs consent), uinput/ydotool, wlroots virtual-input protocols, or gnome-ponytail-daemon.
- **Recommendation:** run under Xvfb/X11 in a container. Use AT-SPI actions first and XTest as the fallback.

### Toolkits and app types

- **Electron/CEF: treat as web.**
  - Drive through Playwright `_electron` or `--remote-debugging-port`.
  - This fails if the `EnableNodeCliInspectArguments` fuse is off. Check fuses statically (REA's `inspect_electron_fuses`).
  - Fallbacks: on macOS, set `AXManualAccessibility` (or `AXEnhancedUserInterface` for Chromium); on Windows/Linux, `--force-renderer-accessibility` or AT detection.
  - **Never flip fuses.**
- **Qt:** decent through QAccessible, but custom-painted QGraphicsView and QML canvases are opaque.
- **Java Swing:**
  - Windows: Java Access Bridge (`jabswitch -enable`).
  - Linux: java-atk-wrapper.
  - macOS: fair.
- **Flutter desktop:** exposes a semantics tree, but quality depends on the developer.
- **Canvas and game-engine apps need vision.**
  - Options: OmniParser v2 (~0.6 s/frame on an A100; 39.6 on ScreenSpot-Pro with GPT-4o), UI-TARS-2, ShowUI, or a frontier computer-use agent (high-80s on ScreenSpot-Pro in 2026 **[unverified]**).
- **Accessibility coverage in practice:**
  - Good: Apple first-party, AppKit/SwiftUI, WinUI/WPF/WinForms, GTK4.
  - Poor: LibreOffice/VCL, Java, owner-drawn Win32, canvas.
  - Expect 10–30% of interactive targets to need vision **[unverified estimate]**.

## 2. Side effects observed black-box

| Channel | macOS | Windows | Linux |
|---|---|---|---|
| Files | `eslogger` (Endpoint Security JSON; root + Full Disk Access), `fs_usage`, FSEvents (coarse) | Process Monitor CLI (`/Quiet /Minimized /BackingFile`), ETW (krabsetw/SilkETW) | fanotify, inotify, `strace -e trace=%file`, eBPF |
| Prefs / state | `defaults export` and plist diff; `~/Library/Containers/<bundle>/Data`; Saved Application State | Registry snapshot diff (Regshot-style), `%APPDATA%` diff | XDG `~/.config` diff, `dconf dump /` |
| Network | mitmproxy **local capture mode** per process (`--mode local:<name\|pid>`) | same (WinDivert) | same (eBPF, kernel ≥ 6.8) |
| Processes | `eslogger exec fork exit` | ETW / Procmon | execsnoop |
| Clipboard | NSPasteboard `changeCount` | `AddClipboardFormatListener` | `wl-paste --watch` / X selection |
| Notifications | the banner, via AX **[unverified]** | the toast, via UIA | `dbus-monitor` on `org.freedesktop.Notifications` |
| IPC | XPC connect events in Endpoint Security (macOS 14+ **[unverified]**) | COM through ETW, named pipes through Procmon | `dbus-monitor` |

If certificate pinning hides traffic, **do not defeat it.** Record an unknown instead.

### Clean-room line: an `observation_tier` field on every claim

1. **`ui` and public effects: may become spec claims.**
   - Visible UI, persisted user-visible artifacts and output formats, "remembers the last value", visible prefs.
   - Third-party network requests at the protocol level.
   - Clipboard contents, notifications, published D-Bus or AppleScript interfaces.
2. **`effect` (grey): steering only.**
   - Private on-disk layout, private plist keys, private XPC names, helper topology.
   - The gate allows "persists the last result and restores it on relaunch". It rejects "writes key `LastResultValue` to com.apple.calculator.plist" unless that file is an interop target.
3. **`trace` (implementation): dirty side only.**
   - Syscall sequences, ordering, threads, library loads.
   - The only outputs allowed are "a file under X was modified" and coverage steering.

## 3. State abstraction

- **State key:** `(app, focused window role and identifier, modal/sheet stack, focused element path, masked tree hash)`.
- **Normalization:**
  - Drop frames.
  - Strip invisible Unicode. The spike found U+200E in every Calculator value.
  - Mask volatile values.
  - **Exclude system-owned menus.** The Apple menu showed "System Settings…, 1 update" and Recent Items.
  - Truncate long lists.
  - Key on `AXIdentifier` (170 of 239 nodes in the spike had one).
- **Identifier churn is state.** Calculator's `AllClear` becomes `Clear`, so re-resolve locators after every action.
- **Modal detection:**
  - macOS: AXSheet / AXDialog / AXSystemDialog.
  - Windows: UIA `IsModal`.
  - Linux: AT-SPI `STATE_MODAL`.
- **The menu bar is a feature inventory, which is the desktop's advantage.**
  - `AXMenuBar` gives every command with its enabled state and shortcut. The spike found 94 app-owned items, 25 with shortcuts, in 0.15 s.
  - **Enabled states are free state predicates.**
  - Windows ribbons hide commands; use UIA AccessKey/AcceleratorKey instead.
  - GTK4 uses hamburger menus; on KDE, use dbusmenu.

## 4. Reset and isolation

| OS | Mechanism | Cost (est.) | Notes |
|---|---|---|---|
| macOS VM | **Tart** (Virtualization.framework, OCI images, fair-source licence), UTM | APFS clone ~1 s; cold boot ~20–40 s; `saveMachineState` restore (macOS 14+) ~3–8 s **[unverified]** | **Hard limit of 2 concurrent macOS guests per Mac** (EULA §2B(iii); the framework returns VZErrorDomain code 6 on a third) |
| macOS fast tier | Kill the app, restore its Containers dir, `defaults delete`, remove Saved Application State | ~1–2 s | Only for sandboxed apps. Find non-sandboxed state roots with an fs-trace at intake. |
| Windows | Hyper-V checkpoints (~5–20 s **[unverified]**); Windows Sandbox (no snapshots, one at a time); RDP loopback (UFO2) | | WindowsAgentArena runs 40 parallel Azure VMs, ~20 minutes per evaluation |
| Linux | Docker + Xvfb, overlayfs/CRIU, fresh `$HOME` | <1–3 s | Cheapest and most parallel |

- **Reset ladder:** process + state-dir restore (~1 s) → VM saved-state restore → cold VM.
  - Escalate when a re-snapshot fingerprint differs from the baseline.
- **macOS query budget:** about 500–1500 membership queries per hour per VM, with 2 VMs per Mac.
  - That is enough for KV/TTT learning with about 10 symbols and 30 states, with caching.
  - It is not enough for naive L\* over a menu-sized alphabet. Partition the alphabet by feature.

## 5. Determinism

- **Time:**
  - Linux: libfaketime.
  - macOS: `DYLD_INSERT_LIBRARIES` is stripped for SIP-protected and hardened apps, so **set the guest VM clock** instead (NTP off, then `systemsetup -setdate`).
  - **Re-signing a target to strip its hardened runtime is modification and likely circumvention. Don't.**
  - Windows: set the VM clock.
- **Locale:**
  - macOS: launch with `-AppleLanguages '(en)' -AppleLocale en_US`.
  - Linux: `LANG`.
  - Windows: the image locale.
- **Rendering:**
  - Fix window size (set `AXSize` / `SetWindowPos`).
  - Display at 1× scale, fixed Xvfb DPI, pinned fonts.
- **Motion:**
  - macOS: `reduceMotion`, set in the guest only.
  - Windows: `SPI_SETCLIENTAREAANIMATION`.
  - GNOME: `enable-animations false`.
- **Saved state across launches is a trap.**
  - Calculator relaunched showing its previous result (`LastResultValue` / `RestoreInputValue`).
  - Either reset it, or probe it deliberately as a `default` claim.

## 6. Prior art and benchmarks

| Benchmark | What it offers | Results |
|---|---|---|
| OSWorld-Verified | Linux/Windows VMs with snapshot revert | Human 72.36%; Agent S3 72.6% (Dec 2025); ~85% in 2026 **[unverified]** |
| WindowsAgentArena | 154 tasks | Navi 19.5% |
| macOSWorld (NeurIPS 2025, arXiv 2506.04135) | 202 tasks, 30 apps | CUAs >30%, open models <5% |

- **All of them measure task completion, not behavior extraction.** Reuse their VM and checker harnesses, not their metrics.
- **GUI ripping (GUITAR; Memon, WCRE 2003)** began on Java and Windows desktop.
  - It builds event-flow graphs, which fit the menu-inventory alphabet.
  - Teardown's *explore* step is GUI ripping plus LLM naming.
- **TESTAR**, a scriptless UIA tester for Windows, is worth a look **[unverified status]**.
- **No black-box spec-to-clone pipeline for desktop has been published.**

## 7. Evaluation targets

**Rule: the hidden suite must drive the app through an external interface** (a11y, WebDriver, Playwright-Electron or CLI). In-process suites can't be pointed at a clone without porting; examples are KeePassXC's QTest suite and LibreOffice's UNO-based UITests.

| Target | Ground truth | Feasibility |
|---|---|---|
| **Windows Calculator** (microsoft/calculator) | `CalculatorUITests`: Appium/WinAppDriver, black-box by AutomationId | **High. Best first desktop target.** The clone keeps the AutomationIds (with a `compat_reason`). |
| **Joplin desktop** (Electron) | Playwright `_electron` integration tests, temp profile | **High** |
| **VS Code** (Electron) | `test/smoke` (Playwright) | High, but scope it to one feature |
| **GNOME Calculator / Text Editor / Characters** | dogtail/behave suites **[per-app availability unverified]** | Medium-high on Linux. Best for automata learning. |
| **KeePassXC** | Black-box tests for `keepassxc-cli`, plus the KDBX file as an output oracle | Medium |
| **LibreOffice** | In-process UNO tests, which need porting | Medium-low. A stress target. |
| **Inkscape** | Export render tests | Medium, for output-file claims |
| **Notepad++** | Few UI tests | Low |

## 8. Spike: AX tree of macOS Calculator (`spikes/desktop-ax/`)

- **Permission:** `AXIsProcessTrusted() = True` (the host already had the grant). No settings were changed.
- **Tree:** **239 nodes**, depth 7, read in **0.146 s**.
  - 170 nodes carry an AXIdentifier (`Seven`, `Equals`, `AllClear`, …) and 186 are labelled.
- **Menus:** 154 items, 94 app-owned, 25 with shortcuts.
  - Examples: View > Basic/Scientific/Programmer (⌘1/2/3), RPN Mode (⌘R).
  - Undo is disabled in the initial state.
- **Probes:** each AXPress took 11–18 ms.

  | Input | Display | Claim type |
  |---|---|---|
  | `12+34=` | `46` | arithmetic |
  | `1÷0=` | `Undefined` | refusal |
  | `7+1===` | `10` | repeat-last-op |
  | `0.1+0.2=` | `0.3` | decimal arithmetic |

- **Gotchas:**
  - U+200E in values.
  - The AllClear/Clear identifier swap.
  - Noise from host system menus.
  - **State persisted across relaunch** in the Containers plist.
- **Side effect on the host:** Calculator's saved last result is now `0.3`.

## Decisions

1. **One adapter with three backends:** AXBackend, UIABackend (FlaUI or `uiautomation`) and ATSPIBackend.
   - Methods: `snapshot()`, `act(semantic_action)`, `menu_inventory()`, `observe_effects()`.
   - Semantic actions by default, injected input as a fallback, and vision only for empty or unlabelled subtrees (fused the UFO2 way).
   - Own the backends. Wrap the existing MCPs only for experiments.
2. **Route Electron/CEF to the web pipeline** when the fuses allow it. Never flip fuses.
3. **Use the menu bar as the feature inventory and seed alphabet.** Its enabled states are free state predicates.
4. **State hash:** the normalized, masked a11y tree plus the window/modal stack, refined the APE way.
5. **`observe_effects`:** prefs and data-dir diff, mitmproxy local mode, and a file-event tracer. Tag each claim with `observation_tier`.
6. **Reset ladder,** with a fingerprint check after every reset.
7. **Run every dirty-side target in a disposable VM or container, never on the analyst's host.**
   - Tart on macOS, Hyper-V plus RDP loopback on Windows, Docker + Xvfb on Linux.
   - This also solves TCC prompts, time control, motion and DPI.
8. **Evaluation order:** Windows Calculator → Joplin → a GNOME app → LibreOffice later.
9. **Build order:** Linux first (cheapest reset and parallelism), macOS second (best a11y, but the 2-VM ceiling), Windows third (heaviest infrastructure).

## Risk

| OS | Rating | Why |
|---|---|---|
| **Linux** | medium-high | Cheap, deterministic, parallel; uneven a11y; Wayland friction; fewer commercial targets |
| **macOS** | medium | Best a11y, but the 2-VM cap, no DYLD time faking, monthly TCC prompts and scattered state |
| **Windows** | medium | Mature UIA and Hyper-V scale, but UIA gaps make vision mandatory for a real share of targets; heavy images; the WinAppDriver ecosystem is decaying |
| **Cross-cutting** | high | Canvas and game apps (out of scope for v1); in-process hidden suites need porting |
