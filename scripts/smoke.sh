#!/usr/bin/env bash
# End-to-end smoke test from example configs (no real infra needed):
# generate secrets + Caddyfile + nodes.json, render the portal, assert no real values.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

PY=""
for c in python3 python py; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys" >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "[smoke] python not found"; exit 1; }

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

cp "$ROOT/generate_caddy.py" "$ROOT/render.py" "$ROOT/status.py" "$tmp/"
mkdir -p "$tmp/scripts" "$tmp/conf" "$tmp/authelia" "$tmp/headscale"
cp "$ROOT/scripts/gen-secrets.sh" "$tmp/scripts/"
cp "$ROOT/conf/authelia-config.template.yml" "$ROOT/conf/users_database.template.yml" "$ROOT/conf/headscale-config.template.yml" "$tmp/conf/"
cp "$ROOT/caravan.env.example" "$tmp/caravan.env"
cp "$ROOT/conf/nodes.example.yaml" "$tmp/nodes.yaml"

cd "$tmp"
SECRETS_FILE="$tmp/secrets.env" bash scripts/gen-secrets.sh >/dev/null
$PY generate_caddy.py >/dev/null
$PY render.py conf/authelia-config.template.yml authelia/configuration.yml @secrets.env DOMAIN=example.com >/dev/null
$PY render.py conf/users_database.template.yml authelia/users_database.yml @secrets.env ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD_HASH=dummy >/dev/null
$PY render.py conf/headscale-config.template.yml headscale/config.yaml DOMAIN=example.com >/dev/null

[ -f caddy/Caddyfile ] || { echo "[smoke] no Caddyfile"; exit 1; }
[ -f nodes.json ] || { echo "[smoke] no nodes.json"; exit 1; }
grep -q 'example.com' caddy/Caddyfile || { echo "[smoke] example domain missing"; exit 1; }
leaks="$(grep -oE '[a-z0-9.-]+\.(com|net|org|io)' caddy/Caddyfile | grep -vE 'example\.com$' || true)"
if [ -n "$leaks" ]; then
  echo "[smoke] unexpected domains in Caddyfile: $leaks"; exit 1
fi
grep -q 'issuer: example.com' authelia/configuration.yml || { echo "[smoke] authelia render failed"; exit 1; }
grep -q 'server_url: https://mesh.example.com' headscale/config.yaml || { echo "[smoke] headscale render failed"; exit 1; }
$PY - <<'PY'
import importlib.util, json
spec = importlib.util.spec_from_file_location("status", "status.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
data = json.load(open("nodes.json"))
html = m.render(data, {e["name"]: {"status": "online", "ms": 1} for e in data["envs"]}, 0)
assert "example.com" in html, "portal render leaked"
PY
echo "[smoke] OK"
