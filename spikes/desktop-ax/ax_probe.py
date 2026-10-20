"""Spike: actuate Calculator via AXPress and observe the display (behavior probe).
Read-only w.r.t. system settings. Quits Calculator at the end."""
import subprocess
import time

from AppKit import NSWorkspace
from ApplicationServices import (
    AXUIElementCopyAttributeValue,
    AXUIElementCreateApplication,
    AXUIElementPerformAction,
)


def attr(el, n):
    e, v = AXUIElementCopyAttributeValue(el, n, None)
    return v if e == 0 else None


def find_all(el, out):
    out.append(el)
    for c in attr(el, "AXChildren") or []:
        find_all(c, out)
    return out


subprocess.run(["open", "-a", "Calculator"], check=True)
time.sleep(2.0)
pid = next(a.processIdentifier() for a in NSWorkspace.sharedWorkspace().runningApplications()
           if a.localizedName() == "Calculator")
app = AXUIElementCreateApplication(pid)
win = attr(app, "AXWindows")[0]
els = find_all(win, [])
by_id = {attr(e, "AXIdentifier"): e for e in els if attr(e, "AXIdentifier")}
display = next(e for e in els if attr(e, "AXRole") == "AXStaticText")


def ids_now():
    els = find_all(win, [])
    return {attr(e, "AXIdentifier"): e for e in els if attr(e, "AXIdentifier")}


print("ids at launch:", sorted(k for k in by_id if "Clear" in k))


def press_seq(ids):
    lat = []
    for i in ids:
        cur = ids_now()  # re-resolve: AC/C key swaps identifier with state
        if i == "AllClear" and i not in cur:
            for _ in range(2):
                AXUIElementPerformAction(cur.get("Clear") or cur["AllClear"], "AXPress")
                cur = ids_now()
            continue
        t0 = time.time()
        AXUIElementPerformAction(cur[i], "AXPress")
        lat.append(time.time() - t0)
    time.sleep(0.3)
    return attr(display, "AXValue"), max(lat)


probes = {
    "12+34=": ["AllClear", "One", "Two", "Add", "Three", "Four", "Equals"],
    "1/0=": ["AllClear", "One", "Divide", "Zero", "Equals"],
    "7==(repeat equals)": ["AllClear", "Seven", "Add", "One", "Equals", "Equals", "Equals"],
    "0.1+0.2=": ["AllClear", "Zero", "Decimal", "One", "Add", "Zero", "Decimal", "Two", "Equals"],
}
for name, seq in probes.items():
    v, lat = press_seq(seq)
    print(f"{name:22s} -> display={v!r}  max_press_latency={lat*1000:.1f}ms")

t0 = time.time()
subprocess.run(["osascript", "-e", 'quit app "Calculator"'])
print("quit took", round(time.time() - t0, 2), "s")
