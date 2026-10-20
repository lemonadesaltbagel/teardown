#!/bin/sh
# Self-hosted Conduit (RealWorld) target: Django Ninja API on 127.0.0.1:8000 with a SQLite file we can reset,
# Angular frontend built against it (served by Teardown's LocalSite with SPA fallback).
set -e
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
DATA="$ROOT/.teardown/conduit/db"
cp "$ROOT/.teardown/conduit/pristine.sqlite3" "$DATA/db.sqlite3"
docker rm -f teardown-conduit-api >/dev/null 2>&1 || true
docker run -d --name teardown-conduit-api -p 127.0.0.1:8000:8000 -e DEBUG=True -e ALLOWED_HOSTS='*' \
  -e DATABASE_URL=file:/data/db.sqlite3 -v "$DATA:/data" teardown/conduit-api >/dev/null
for i in $(seq 1 30); do curl -sf http://127.0.0.1:8000/api/tags >/dev/null && break; sleep 0.5; done
curl -s http://127.0.0.1:8000/api/tags; echo
