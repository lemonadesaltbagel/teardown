"""Serve a Conduit frontend build on a fixed port with SPA fallback until killed."""

import sys
import time

from teardown.drivers.web.driver import LocalSite

site = LocalSite(sys.argv[1], spa=True, port=int(sys.argv[2]))
print(f"serving {sys.argv[1]} on {site.url('')}", flush=True)
while True:
    time.sleep(3600)
