"""Playwright driver: localhost static server, browser lifecycle, reset strategies, settle, metrics."""
from __future__ import annotations

import functools
import http.server
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import sync_playwright

TARGETS = Path(__file__).resolve().parent.parent / 'targets'


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


class LocalServer:
    """Serves targets/ on 127.0.0.1:<random port>. Nothing leaves the machine."""

    def __init__(self, root: Path = TARGETS):
        handler = functools.partial(_QuietHandler, directory=str(root))
        self.httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, name: str, query: str = '') -> str:
        return f'http://127.0.0.1:{self.port}/{name}' + (f'?{query}' if query else '')

    def close(self):
        self.httpd.shutdown()


@dataclass
class Metrics:
    resets: int = 0
    actions: int = 0
    snapshots: int = 0
    t_reset: float = 0.0
    t_action: float = 0.0
    t_snapshot: float = 0.0

    def as_dict(self):
        d = dict(self.__dict__)
        d['ms_per_reset'] = round(1000 * self.t_reset / max(1, self.resets), 2)
        d['ms_per_action'] = round(1000 * self.t_action / max(1, self.actions), 2)
        d['ms_per_snapshot'] = round(1000 * self.t_snapshot / max(1, self.snapshots), 2)
        return d


_SHARED: dict = {}


def _browser(headless: bool):
    """One Playwright + Chromium per process (the sync API cannot be started twice in a thread);
    each WebDriver gets its own BrowserContext(s) for isolation."""
    if headless not in _SHARED:
        pw = _SHARED.get('pw') or sync_playwright().start()
        _SHARED['pw'] = pw
        _SHARED[headless] = pw.chromium.launch(headless=headless)
    return _SHARED[headless]


class WebDriver:
    """reset_mode: 'context' = fresh BrowserContext + goto (true isolation: cookies/storage);
                   'goto'    = same context, navigate again (cheaper, leaks storage).
       settle:     'none'   = read snapshot once (OK for synchronous DOM updates),
                   'stable' = re-read until two consecutive snapshots agree (async-safe, ~2x snapshot cost)."""

    def __init__(self, url: str, reset_mode: str = 'context', settle: str = 'none', headless: bool = True,
                 action_timeout_ms: int = 2000):
        self.url, self.reset_mode, self.settle = url, reset_mode, settle
        self.browser = _browser(headless)
        self.ctx = None
        self.page = None
        self.action_timeout_ms = action_timeout_ms
        self.m = Metrics()

    def reset(self):
        t = time.perf_counter()
        if self.reset_mode == 'context' or self.page is None:
            if self.ctx:
                self.ctx.close()
            self.ctx = self.browser.new_context()
            self.ctx.set_default_timeout(self.action_timeout_ms)
            self.page = self.ctx.new_page()
        self.page.goto(self.url, wait_until='load')
        self.m.resets += 1
        self.m.t_reset += time.perf_counter() - t

    def act(self, fn) -> str | None:
        """Run a mapper action; returns None if performed, else a short reason ('NA', 'DISABLED')."""
        t = time.perf_counter()
        try:
            return fn(self.page)
        finally:
            self.m.actions += 1
            self.m.t_action += time.perf_counter() - t

    def snapshot(self) -> str:
        t = time.perf_counter()
        snap = self.page.locator('body').aria_snapshot()
        if self.settle == 'stable':
            for _ in range(20):
                self.page.wait_for_timeout(25)
                again = self.page.locator('body').aria_snapshot()
                if again == snap:
                    break
                snap = again
        self.m.snapshots += 1
        self.m.t_snapshot += time.perf_counter() - t
        return snap

    def close(self):
        if self.ctx:
            self.ctx.close()
            self.ctx = self.page = None
