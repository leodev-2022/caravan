#!/usr/bin/env bash
# Render the Caddyfile from example configs and validate it with caddy.
# Requires docker for `caddy validate` (skipped if docker is absent).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

PY=""
for c in python3 python py; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys" >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "[caddy-validate] python not found"; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
cp "$ROOT/generate_caddy.py" "$tmp/"
cp "$ROOT/caravan.env.example" "$tmp/caravan.env"
cp "$ROOT/conf/nodes.example.yaml" "$tmp/nodes.yaml"
(cd "$tmp" && "$PY" generate_caddy.py >/dev/null)

[ -f "$tmp/caddy/Caddyfile" ] || { echo "[caddy-validate] no Caddyfile rendered"; exit 1; }

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  docker run --rm -v "$tmp/caddy/Caddyfile:/Caddyfile:ro" caddy:2 caddy validate --config /Caddyfile
else
  echo "[caddy-validate] docker not available, skipping caddy validate"
fi
echo "[caddy-validate] OK"
