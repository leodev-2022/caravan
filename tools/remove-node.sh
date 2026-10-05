#!/usr/bin/env bash
# remove-node.sh — remove a node from nodes.yaml, regenerate the Caddyfile,
# and reload Caddy. Runs on the hub (root).
#
#   sudo bash remove-node.sh --name s1
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
NAME=""

usage() {
  cat <<'EOF'
Caravan — unregister a node from the hub

Usage: sudo bash remove-node.sh --name NAME [--dir DIR]

  --name NAME   node name to remove
  --dir DIR     hub directory (default: /opt/caravan)
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --name) NAME="${2:?--name needs a value}"; shift 2 ;;
    --dir) CARAVAN_DIR="${2:?--dir needs a value}"; shift 2 ;;
    -h | --help) usage; exit 0 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

require_root
[ -n "$NAME" ] || die "--name is required"
[ -f "$CARAVAN_DIR/nodes.yaml" ] || die "no nodes.yaml in $CARAVAN_DIR"

python3 - "$CARAVAN_DIR/nodes.yaml" "$NAME" <<'PY'
import sys

import yaml

path, name = sys.argv[1:3]
with open(path, encoding="utf-8") as fh:
    data = yaml.safe_load(fh) or {}
envs = data.get("envs") or []
kept = [e for e in envs if e.get("name") != name]
if len(kept) == len(envs):
    sys.exit(f"[remove-node] not found: {name}")
data["envs"] = kept
with open(path, "w", encoding="utf-8") as fh:
    yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
print(f"[remove-node] removed {name}")
PY

# also drop it from the mesh, otherwise the auto-sync timer re-registers it
mesh_id="$(docker exec "${HS_CONTAINER:-headscale}" headscale nodes list -o json 2>/dev/null |
  python3 -c 'import json,sys; n=sys.argv[1]; s=sys.stdin.read() or "[]"; nodes=json.loads(s); print(next((x.get("id") for x in nodes if (x.get("given_name") or x.get("name")) == n), ""))' "$NAME" 2>/dev/null || true)"
if [ -n "$mesh_id" ]; then
  docker exec "${HS_CONTAINER:-headscale}" headscale nodes delete -i "$mesh_id" --force >/dev/null 2>&1 || true
  log "removed $NAME from the mesh"
fi

log "regenerating Caddyfile + nodes.json"
(cd "$CARAVAN_DIR" && python3 generate_caddy.py)

log "reloading caddy"
(cd "$CARAVAN_DIR" && docker compose restart caddy) || docker restart caddy

log "done: removed $NAME"
