"""Web driver: Playwright (Chromium) with a determinism profile; actions are role/name locators only.

Target specs::

    web:<url>                      the page an episode starts on (reset = fresh browser context + navigation)

What is observed (behavior tier only): the accessibility snapshot of the page, the URL path, open dialogs, and the
constraint-validation state of form controls (read through one allow-listed probe function). Script, style and
WASM bodies are never read; ``evaluate`` against application globals is never used.

Each worker thread gets its own Playwright instance (the sync API is thread-bound) and each episode its own
browser context, so cookies and storage never leak between episodes.
"""

from __future__ import annotations

import functools
import http.server
import re
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict

from teardown.core.ids import content_id
from teardown.drivers.base import Action, Driver, DriverCapabilities


class WebAction(BaseModel):
    """One UI action addressed by ARIA role and accessible name (portable between original and clone)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    op: Literal["click", "fill", "check", "uncheck", "select", "press", "goto"]
    role: str | None = None
    name: str | None = None
    name_regex: bool = False
    value: str | None = None


# Read-only probe of the constraint-validation API: the shipped UI contract, not application code.
_FORM_PROBE = """() => Array.from(document.querySelectorAll('input, select, textarea')).map(el => ({
  name: (el.labels && el.labels[0] ? el.labels[0].textContent.trim() : '')
        || el.getAttribute('aria-label') || el.name || '',
  type: el.type || el.tagName.toLowerCase(), required: el.required, disabled: el.disabled,
  empty: !el.value, valid: el.validity ? el.validity.valid : true,
  constraints: Object.fromEntries(['minLength','maxLength','min','max','pattern','step']
    .map(k => [k, el[k]]).filter(([k, v]) => v !== '' && v !== -1 && v !== undefined && v !== null))
}))"""

_SEED_RANDOM = """(() => {
  let s = 0x2545F491;
  const next = () => { s ^= s << 13; s ^= s >>> 17; s ^= s << 5; return (s >>> 0) / 4294967296; };
  Math.random = next;
  if (window.crypto) {
    crypto.getRandomValues = (a) => { for (let i = 0; i < a.length; i++) a[i] = Math.floor(next() * 256); return a; };
    crypto.randomUUID = () => 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c =>
      ((c === 'x' ? next() * 16 : (next() * 4) + 8) | 0).toString(16));
  }
})();"""

_LOCAL = threading.local()


def _browser():
    if getattr(_LOCAL, "browser", None) is None:
        from playwright.sync_api import sync_playwright

        _LOCAL.pw = sync_playwright().start()
        _LOCAL.browser = _LOCAL.pw.chromium.launch(headless=True)
    return _LOCAL.browser


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str = "UTC"
    locale: str = "en-US"
    viewport: tuple[int, int] = (1280, 800)
    reduced_motion: bool = True
    seed_random: bool = True
    block_service_workers: bool = True
    action_timeout_ms: int = 2000
    navigation_timeout_ms: int = 15000
    settle: Literal["none", "stable", "network"] = "network"
    settle_timeout_ms: int = 3000


class ResetFailed(RuntimeError):
    pass


class WebDriver(Driver):
    """``reset_command`` (argv) restores self-hosted backend state before every episode (e.g. copy a pristine
    database file into place). ``reset_check_url`` is fetched after each reset; if its response differs from the
    first one, state leaked between episodes and the reset is refused rather than silently trusted."""

    name = "web"

    def __init__(self, target_spec: str, actions: dict[str, WebAction] | None = None, profile: Profile | None = None,
                 reset_command: list[str] | None = None, reset_check_url: str | None = None):
        self.url = target_spec.removeprefix("web:")
        self.table = dict(actions or {})
        self.profile = profile or Profile()
        self.reset_command = list(reset_command or [])
        self.reset_check_url = reset_check_url
        self._baseline: bytes | None = None
        self._ctx = None
        self.page = None
        self._inflight = 0
        self._requests_since_observe = 0

    def target_fingerprint(self) -> str:
        return content_id("tgt", {"platform": "web", "url": self.url, "profile": self.profile.model_dump()})

    def capabilities(self) -> DriverCapabilities:
        return DriverCapabilities(platform="web", reset_cost_ms=50.0, soft_reset=True, parallelism=8)

    def _reset_backend(self) -> None:
        if self.reset_command:
            subprocess.run(self.reset_command, check=True, capture_output=True, timeout=60)
        if self.reset_check_url:
            with urllib.request.urlopen(self.reset_check_url, timeout=10) as resp:  # noqa: S310 - target's own URL
                body = resp.read()
            if self._baseline is None:
                self._baseline = body
            elif body != self._baseline:
                raise ResetFailed(f"reset check failed: {self.reset_check_url} differs from its post-reset baseline")

    def reset(self) -> Any:
        self._reset_backend()
        if self._ctx is not None:
            self._ctx.close()
        p = self.profile
        self._ctx = _browser().new_context(
            timezone_id=p.timezone, locale=p.locale, viewport={"width": p.viewport[0], "height": p.viewport[1]},
            reduced_motion="reduce" if p.reduced_motion else "no-preference",
            service_workers="block" if p.block_service_workers else "allow",
        )
        self._ctx.set_default_timeout(p.action_timeout_ms)
        self._ctx.set_default_navigation_timeout(p.navigation_timeout_ms)
        if p.seed_random:
            self._ctx.add_init_script(_SEED_RANDOM)
        self.page = self._ctx.new_page()
        self._inflight = 0
        self._requests_since_observe = 1  # the initial navigation always settles

        def started(_request):
            self._inflight += 1
            self._requests_since_observe += 1

        def ended(_request):
            self._inflight = max(0, self._inflight - 1)

        self.page.on("request", started)
        self.page.on("requestfinished", ended)
        self.page.on("requestfailed", ended)
        self.page.goto(self.url, wait_until="load")
        return self.observe()

    def step(self, action: Action) -> Any | None:
        if self.page is None:
            self.reset()
        spec = WebAction.model_validate(action.params) if action.params else self.table.get(action.name)
        if spec is None:
            return None
        outcome = self._perform(spec)
        if outcome == "absent":
            return None
        if outcome == "disabled":
            return "DISABLED"
        return self.observe()

    def _perform(self, a: WebAction) -> str:
        page = self.page
        if a.op == "goto":
            page.goto(a.value or self.url, wait_until="load")
            return "ok"
        if a.op == "press" and not a.role:
            page.keyboard.press(a.value or "Enter")
            return "ok"
        name = re.compile(a.name, re.I) if (a.name and a.name_regex) else a.name
        loc = page.get_by_role(a.role, name=name, exact=not a.name_regex) if name else page.get_by_role(a.role)
        if loc.count() == 0:
            return "absent"
        loc = loc.first
        if a.op in ("click", "check", "uncheck") and loc.is_disabled():
            return "disabled"
        # force=True skips Playwright's actionability waits (~30 ms per click); presence and enabled state
        # were checked above.
        if a.op == "click":
            loc.click(force=True)
        elif a.op == "fill":
            loc.fill(a.value or "", force=True)
        elif a.op == "check":
            loc.check(force=True)
        elif a.op == "uncheck":
            loc.uncheck(force=True)
        elif a.op == "select":
            loc.select_option(a.value)
        elif a.op == "press":
            loc.press(a.value or "Enter")
        return "ok"

    def _settle(self) -> None:
        """'network': wait (bounded) until no request is in flight for two consecutive 10 ms polls, then for two
        equal snapshots. Costs ~nothing on pages without traffic; needed for SPAs whose state arrives async."""
        if self.profile.settle != "network":
            return
        deadline, quiet = time.monotonic() + self.profile.settle_timeout_ms / 1000, 0
        while time.monotonic() < deadline and quiet < 2:
            self.page.wait_for_timeout(10)
            quiet = quiet + 1 if self._inflight == 0 else 0

    def observe(self) -> Any:
        if self.page is None:
            return self.reset()
        # 'network' settles only when the last action caused requests; a synchronous DOM update needs no wait.
        waiting = self.profile.settle == "stable" or (self.profile.settle == "network" and self._requests_since_observe)
        if waiting:
            self._settle()
        self._requests_since_observe = 0
        snap = self.page.locator("body").aria_snapshot()
        if waiting:
            for _ in range(20):
                self.page.wait_for_timeout(25)
                again = self.page.locator("body").aria_snapshot()
                if again == snap:
                    break
                snap = again
        return {
            "path": urlparse(self.page.url).path or "/",
            "aria": snap,
            "form": self.page.evaluate(_FORM_PROBE),
        }

    def actions(self) -> list[str]:
        return sorted(self.table)

    def close(self) -> None:
        if self._ctx is not None:
            self._ctx.close()
            self._ctx = self.page = None


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    spa = False

    def log_message(self, *args):
        pass

    def send_head(self):
        if self.spa:
            target = Path(self.translate_path(self.path))
            if not target.exists() and "." not in Path(urlparse(self.path).path).name:
                self.path = "/index.html"  # single-page app: unknown routes are client-side
        return super().send_head()


class LocalSite:
    """Serve a directory on 127.0.0.1 (for examples, tests and self-hosted static targets)."""

    def __init__(self, root: str | Path, *, spa: bool = False, port: int = 0):
        handler_cls = type("Handler", (_QuietHandler,), {"spa": spa})
        handler = functools.partial(handler_cls, directory=str(root))
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, name: str = "") -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}/{name}"

    def close(self) -> None:
        self.httpd.shutdown()


EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "web"
