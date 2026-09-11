#!/usr/bin/env bash
# invite.sh — mint a node join token and print the one-line command to run on
# the new machine. Runs on the hub (root).
#   sudo bash invite.sh [--expiry 1h] [--reusable] [--user NAME|ID] [--dir DIR]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$HERE/lib.sh" ]; then
  # shellcheck source=lib.sh
  . "$HERE/lib.sh"
else
  # shellcheck source=../scripts/lib.sh
  . "$HERE/../scripts/lib.sh"
fi

CARAVAN_DIR="${CARAVAN_DIR:-/opt/caravan}"
HS_CONTAINER="${HS_CONTAINER:-headscale}"
EXPIRY="1h"
REUSABLE=""
USER=""

usage() {
  cat <<'EOF'
Caravan — invite a machine

Usage: sudo bash invite.sh [--expiry 1h] [--reusable] [--user NAME|ID] [--dir DIR]

  --expiry DUR    token lifetime (default: 1h)
  --reusable      allow the token to be reused
  --user NAME|ID  headscale user (default: the first one)
  --dir DIR       hub directory (default: /opt/caravan)
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --expiry) EXPIRY="${2:?--expiry needs a value}"; shift 2 ;;
    --reusable) REUSABLE="--reusable"; shift ;;
    --user) USER="${2:?--user needs a value}"; shift 2 ;;
    --dir) CARAVAN_DIR="${2:?--dir needs a value}"; shift 2 ;;
    -h | --help) usage; exit 0 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

require_root
have docker || die "docker not found — run this on the hub"
docker ps --format '{{.Names}}' | grep -qx "$HS_CONTAINER" ||
  die "headscale container '$HS_CONTAINER' is not running"

users="$(docker exec "$HS_CONTAINER" headscale users list -o json 2>/dev/null || echo '[]')"
count="$(printf '%s' "$users" | python3 -c 'import json,sys;print(len(json.load(sys.stdin)))' 2>/dev/null || echo 0)"
if [ "$count" = 0 ]; then
  log "no headscale user yet — creating 'caravan'"
  docker exec "$HS_CONTAINER" headscale users create caravan >/dev/null 2>&1 || true
  users="$(docker exec "$HS_CONTAINER" headscale users list -o json 2>/dev/null || echo '[]')"
fi
uid="$(printf '%s' "$users" | python3 -c '
import json, sys
users = json.load(sys.stdin)
want = sys.argv[1] if len(sys.argv) > 1 else ""
if want:
    for u in users:
        if str(u.get("id")) == want or u.get("name") == want:
            print(u["id"]); break
else:
    print(users[0]["id"] if users else "")
' "$USER")"
[ -n "$uid" ] || die "headscale user not found: ${USER:-<default>}"

# shellcheck disable=SC2086
key="$(docker exec "$HS_CONTAINER" headscale preauthkeys create --user "$uid" $REUSABLE --expiration "$EXPIRY" | tail -n1)"

domain="$(grep -m1 '^DOMAIN=' "$CARAVAN_DIR/caravan.env" 2>/dev/null | cut -d= -f2 || true)"
if [ -z "$domain" ]; then
  domain="$(python3 -c "import sys,yaml;print((yaml.safe_load(open(sys.argv[1])) or {}).get('domain',''))" "$CARAVAN_DIR/nodes.yaml" 2>/dev/null || true)"
fi
mesh="https://mesh.${domain}"

cat <<EOF

Token (expires in ${EXPIRY}${REUSABLE:+, reusable}):
  ${key}

On the new machine, run this one line:
  curl -fsSL https://raw.githubusercontent.com/leodev-2022/caravan/main/tools/node-join.sh | sudo bash -s -- --hub ${mesh} --token ${key}

It uses the machine's hostname as the node name (add --name NAME to override).
EOF
