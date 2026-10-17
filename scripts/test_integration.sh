#!/usr/bin/env bash
# Integration test: bring up the full hub stack from example configs and verify
# health endpoints. Requires docker (skipped if unavailable). Uses host ports
# 8080/8443 to avoid clashing with anything already running.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "[integration] docker not available, skipping"
  exit 0
fi

PY=""
for c in python3 python py; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys" >/dev/null 2>&1; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "[integration] python not found"; exit 1; }

PROJECT="caravan-it"
work="$(mktemp -d)"
cleanup() {
  (cd "$work" 2>/dev/null && docker compose -p "$PROJECT" down -v >/dev/null 2>&1) || true
  # container-created files may be owned by another uid; fall back to a root rm
  if ! rm -rf "$work" 2>/dev/null; then
    docker run --rm -v "$(dirname "$work"):/p" alpine sh -c "rm -rf /p/$(basename "$work")" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "[integration] laying out stack in $work"
mkdir -p "$work"/{conf,tools,authelia,headscale,caddy,requests}
cp "$ROOT/compose/docker-compose.yaml" "$work/docker-compose.yaml"
cp "$ROOT/generate_caddy.py" "$ROOT/render.py" "$ROOT/status.py" "$work/"
cp "$ROOT/conf/"*.yml "$ROOT/conf/"*.yaml "$work/conf/"
cp "$ROOT/caravan.env.example" "$work/caravan.env"
cp "$ROOT/conf/nodes.example.yaml" "$work/nodes.yaml"

# non-privileged host ports + unique container names (avoid clashing with a
# running hub on the same host)
printf 'TZ=UTC\nTELEGRAM_TOKEN=\nTELEGRAM_CHAT=\nCADDY_HTTP_PORT=8080\nCADDY_HTTPS_PORT=8443\n' > "$work/.env"
cat > "$work/docker-compose.override.yaml" <<'YAML'
services:
  caddy:
    container_name: caravan-it-caddy
  headscale:
    container_name: caravan-it-headscale
  authelia:
    container_name: caravan-it-authelia
  portal:
    container_name: caravan-it-portal
YAML

echo "[integration] generating secrets"
SECRETS_FILE="$work/secrets.env" ADMIN_USER=admin bash "$ROOT/scripts/gen-secrets.sh" >/dev/null

echo "[integration] rendering configs (self-signed, example.com)"
(
  cd "$work"
  TLS_MODE=internal "$PY" generate_caddy.py >/dev/null
  "$PY" render.py conf/authelia-config.template.yml authelia/configuration.yml @secrets.env DOMAIN=example.com
  "$PY" render.py conf/users_database.template.yml authelia/users_database.yml @secrets.env ADMIN_EMAIL=admin@example.com
  "$PY" render.py conf/headscale-config.template.yml headscale/config.yaml DOMAIN=example.com
)

echo "[integration] docker compose up"
(cd "$work" && docker compose -p "$PROJECT" up -d)

echo "[integration] waiting for health"
ok=0
for i in $(seq 1 30); do
  a="$(curl -sk -o /dev/null -w '%{http_code}' --resolve auth.example.com:8443:127.0.0.1 "https://auth.example.com:8443/api/health" || true)"
  h="$(curl -sk -o /dev/null -w '%{http_code}' --resolve hub.example.com:8443:127.0.0.1 "https://hub.example.com:8443/" || true)"
  m="$(curl -sk -o /dev/null -w '%{http_code}' --resolve mesh.example.com:8443:127.0.0.1 "https://mesh.example.com:8443/health" || true)"
  echo "[integration] try $i: auth=$a hub=$h mesh=$m"
  if [ "$a" = 200 ] && [ "$h" = 302 ] && [ "$m" = 200 ]; then ok=1; break; fi
  sleep 3
done

if [ "$ok" != 1 ]; then
  echo "[integration] FAILED health checks"
  (cd "$work" && docker compose -p "$PROJECT" ps && docker compose -p "$PROJECT" logs --tail=30)
  exit 1
fi
echo "[integration] OK"
