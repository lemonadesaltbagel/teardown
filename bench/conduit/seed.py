"""Seed the self-hosted Conduit backend with the demo users the RealWorld E2E suite expects (via the public API)."""

from __future__ import annotations

import json
import sys
import urllib.request

API = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/api"


def call(method: str, path: str, body: dict | None = None, token: str | None = None) -> dict:
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body else None, method=method,
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Token {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read() or b"{}")


users = {}
for name in ("johndoe", "janedoe"):
    users[name] = call("POST", "/users", {"user": {"username": name, "email": f"{name}@example.com",
                                                   "password": f"{name}-password-1"}})["user"]["token"]
for i, (author, tags) in enumerate([("johndoe", ["welcome", "intro"]), ("johndoe", ["dragons"]),
                                    ("janedoe", ["training", "dragons"]), ("janedoe", ["welcome"])]):
    art = call("POST", "/articles", {"article": {"title": f"Seed article {i} by {author}",
                                                 "description": f"About seed {i}", "body": f"Body of seed article {i}.",
                                                 "tagList": tags}}, users[author])["article"]
    other = "janedoe" if author == "johndoe" else "johndoe"
    call("POST", f"/articles/{art['slug']}/comments", {"comment": {"body": f"Comment on seed {i}"}}, users[other])
print("seeded", list(users))
