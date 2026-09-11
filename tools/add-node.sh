#!/usr/bin/env bash
# add-node.sh — register/update a node in nodes.yaml, regenerate the Caddyfile,
# and reload Caddy. Runs on the hub (root).
#
#   sudo bash add-node.sh --name web1 --ip 100.64.0.10 --port 9898 \
#     --label "Server S1" --location "Office" --tags ai,work
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
IP=""
PORT=9898
LABEL=""
LOCATION=""
TAGS=""
ALIASES=""
ENGINE=""

usage() {
  cat <<'EOF'
Caravan — register a node on the hub

Usage: sudo bash add-node.sh --name NAME --ip IP [options]

  --name NAME        node name (served at <name>.<DOMAIN>)
  --ip IP            mesh IP of the node
  --port N           CodeNomad port (default: 9898)
  --label L          dashboard label
  --location L       free-text location/group label
  --tags a,b         comma-separated tags
  --aliases x,y      extra subdomains for the same backend
  --engine NAME      node engine: codenomad (default) or opencode
  --dir DIR          hub directory (default: /opt/caravan)
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --name) NAME="${2:?--name needs a value}"; shift 2 ;;
    --ip) IP="${2:?--ip needs a value}"; shift 2 ;;
    --port) PORT="${2:?--port needs a value}"; shift 2 ;;
    --label) LABEL="${2:?--label needs a value}"; shift 2 ;;
    --location) LOCATION="${2:?--location needs a value}"; shift 2 ;;
    --tags) TAGS="${2:?--tags needs a value}"; shift 2 ;;
    --aliases) ALIASES="${2:?--aliases needs a value}"; shift 2 ;;
    --engine) ENGINE="${2:?--engine needs a value}"; shift 2 ;;
    --dir) CARAVAN_DIR="${2:?--dir needs a value}"; shift 2 ;;
    -h | --help) usage; exit 0 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

require_root
[ -n "$NAME" ] || die "--name is required"
[ -n "$IP" ] || die "--ip is required"
[ -f "$CARAVAN_DIR/nodes.yaml" ] || die "no nodes.yaml in $CARAVAN_DIR"

python3 - "$CARAVAN_DIR/nodes.yaml" "$NAME" "$IP" "$PORT" "$LABEL" "$LOCATION" "$TAGS" "$ALIASES" "$ENGINE" <<'PY'
import sys

import yaml

path, name, ip, port, label, location, tags, aliases, engine = sys.argv[1:10]
with open(path, encoding="utf-8") as fh:
    data = yaml.safe_load(fh) or {}
envs = data.get("envs") or []
env = {"name": name, "ip": ip, "port": int(port)}
if engine:
    env["engine"] = engine
if label:
    env["label"] = label
if location:
    env["location"] = location
if tags:
    env["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
if aliases:
    env["aliases"] = [a.strip() for a in aliases.split(",") if a.strip()]
data["envs"] = [e for e in envs if e.get("name") != name] + [env]
with open(path, "w", encoding="utf-8") as fh:
    yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
print(f"[add-node] nodes.yaml: {name} -> {ip}:{port}")
PY

log "regenerating Caddyfile + nodes.json"
(cd "$CARAVAN_DIR" && python3 generate_caddy.py)

log "reloading caddy"
(cd "$CARAVAN_DIR" && docker compose restart caddy) || docker restart caddy

domain="$(python3 -c "import sys,yaml;d=yaml.safe_load(open(sys.argv[1])) or {};print(d.get('domain',''))" "$CARAVAN_DIR/nodes.yaml")"
[ -n "$domain" ] || domain="$(grep -m1 '^DOMAIN=' "$CARAVAN_DIR/caravan.env" 2>/dev/null | cut -d= -f2)"
log "done: https://${NAME}${domain:+.$domain}"
