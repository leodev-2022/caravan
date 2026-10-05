#!/usr/bin/env bash
# Caravan hub diagnostics. Safe to run anytime (read-only).
#   sudo bash scripts/doctor.sh
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/lib.sh
. "$HERE/scripts/lib.sh"

CARAVAN_DIR="${CARAVAN_DIR:-/opt/caravan}"
fails=0
warns=0
ok()  { printf '  \033[1;32mOK\033[0m   %s\n' "$*"; }
bad() { printf '  \033[1;31mFAIL\033[0m %s\n' "$*"; fails=$((fails + 1)); }
meh() { printf '  \033[1;33mWARN\033[0m %s\n' "$*"; warns=$((warns + 1)); }
section() { printf '\n\033[1;34m== %s ==\033[0m\n' "$*"; }

section "host"
detect_os
ok "OS: ${OS_ID:-?} ${OS_VERSION_ID:-?} (${OS_ARCH:-?})"
if [ "$(id -u)" -eq 0 ]; then ok "running as root"; else meh "not root — some checks limited"; fi

section "docker"
if have docker; then ok "docker: $(docker --version)"; else bad "docker not found"; fi
if have docker && docker info >/dev/null 2>&1; then ok "docker daemon reachable"; else bad "docker daemon not reachable"; fi
if have docker && docker compose version >/dev/null 2>&1; then
  ok "compose: $(docker compose version)"
else
  bad "compose plugin missing"
fi

section "stack files ($CARAVAN_DIR)"
for f in docker-compose.yaml caddy/Caddyfile authelia/configuration.yml \
  authelia/users_database.yml headscale/config.yaml nodes.json secrets.env .env; do
  if [ -f "$CARAVAN_DIR/$f" ]; then ok "$f"; else bad "missing $f"; fi
done
if [ -f "$CARAVAN_DIR/secrets.env" ]; then
  m="$(stat -c '%a' "$CARAVAN_DIR/secrets.env" 2>/dev/null || echo '?')"
  if [ "$m" = 600 ]; then ok "secrets.env mode 600"; else meh "secrets.env mode $m (want 600)"; fi
fi

section "caddyfile"
if have docker && [ -f "$CARAVAN_DIR/caddy/Caddyfile" ]; then
  if docker run --rm -v "$CARAVAN_DIR/caddy/Caddyfile:/Caddyfile:ro" caddy:2 \
    caddy validate --config /Caddyfile >/dev/null 2>&1; then
    ok "caddy validate"
  else
    bad "caddy validate failed"
  fi
fi

section "containers"
if have docker && [ -f "$CARAVAN_DIR/docker-compose.yaml" ]; then
  (cd "$CARAVAN_DIR" && docker compose ps --format '{{.Name}}	{{.Status}}') | sed 's/^/  /'
fi

section "endpoints (via 127.0.0.1)"
D="$(grep -m1 '^DOMAIN=' "$CARAVAN_DIR/caravan.env" 2>/dev/null | cut -d= -f2)"
if [ -n "$D" ]; then
  for pair in "auth.$D|/api/health" "hub.$D|/" "mesh.$D|/health"; do
    host="${pair%%|*}"
    path="${pair##*|}"
    code="$(curl -sk -o /dev/null -w '%{http_code}' --max-time 8 \
      --resolve "$host:443:127.0.0.1" "https://$host$path" 2>/dev/null)"
    case "$code" in
      200 | 302 | 401) ok "$host$path -> $code" ;;
      000 | "") bad "$host$path -> no response" ;;
      *) meh "$host$path -> $code" ;;
    esac
  done
else
  meh "no DOMAIN in caravan.env — skipping endpoint checks"
fi

section "resources"
ok "disk /: $(df -h / | awk 'NR==2{print $4" free ("$5" used)"}')"
ok "memory: $(free -h | awk '/Mem:/{print $7" available"}')"

printf '\n\033[1mdoctor: %d fail, %d warn\033[0m\n' "$fails" "$warns"
[ "$fails" -eq 0 ] || exit 1
