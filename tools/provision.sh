#!/usr/bin/env bash
# provision.sh — provision a reachable machine as a node over SSH. The hub runs
# this. The target must be reachable from the hub and accept SSH (root, or a
# user with passwordless sudo).
#   sudo bash provision.sh --host 1.2.3.4 --user root [--key FILE | --password PW] \
#     [--name NAME] [--engine codenomad|opencode] [--dir DIR] [--dry-run]
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
HOST=""
USER=""
KEY=""
PASSWORD=""
NAME=""
ENGINE=""
DRY=0

usage() {
  cat <<'EOF'
Caravan — provision a node over SSH

Usage: sudo bash provision.sh --host IP --user USER [--key FILE | --password PW]

  --host IP        target machine (reachable from the hub)
  --user USER      SSH user (root, or a user with passwordless sudo)
  --key FILE       SSH private key (default: the hub key, $CARAVAN_DIR/.ssh/id_ed25519)
  --password PW    SSH password (requires sshpass; often disabled on LXC)
  --name NAME      node name (default: host with dots -> dashes)
  --engine NAME    codenomad (default) or opencode
  --dir DIR        hub directory (default: /opt/caravan)
  --dry-run        only check SSH connectivity, then exit
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="${2:?--host needs a value}"; shift 2 ;;
    --user) USER="${2:?--user needs a value}"; shift 2 ;;
    --key) KEY="${2:?--key needs a value}"; shift 2 ;;
    --password) PASSWORD="${2:?--password needs a value}"; shift 2 ;;
    --name) NAME="${2:?--name needs a value}"; shift 2 ;;
    --engine) ENGINE="${2:?--engine needs a value}"; shift 2 ;;
    --dir) CARAVAN_DIR="${2:?--dir needs a value}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h | --help) usage; exit 0 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

require_root
[ -n "$HOST" ] || die "--host is required"
[ -n "$USER" ] || die "--user is required"
# prefer the env var (keeps the password out of process args)
[ -n "$PASSWORD" ] || PASSWORD="${PROVISION_PASSWORD:-}"
# no key/password given? fall back to the hub's provisioning key, whose public
# half the portal shows (paste it into the target's authorized_keys).
if [ -z "$KEY" ] && [ -z "$PASSWORD" ] && [ -f "$CARAVAN_DIR/.ssh/id_ed25519" ]; then
  KEY="$CARAVAN_DIR/.ssh/id_ed25519"
fi

domain="$(grep -m1 '^DOMAIN=' "$CARAVAN_DIR/caravan.env" 2>/dev/null | cut -d= -f2 || true)"
[ -n "$domain" ] || domain="$(python3 -c "import sys,yaml;print((yaml.safe_load(open(sys.argv[1])) or {}).get('domain',''))" "$CARAVAN_DIR/nodes.yaml" 2>/dev/null || true)"
MESH="https://mesh.${domain}"

SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)
if [ -n "$KEY" ]; then
  SSH=(ssh -i "$KEY" -o BatchMode=yes "${SSH_OPTS[@]}")
elif [ -n "$PASSWORD" ]; then
  have sshpass || die "sshpass not found (needed for --password); use --key instead"
  SSH=(sshpass -p "$PASSWORD" ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no "${SSH_OPTS[@]}")
else
  die "no SSH auth: add the hub key to the target (portal shows it), or pass --key/--password"
fi

if [ "$USER" = "root" ]; then
  SUDO=""
else
  SUDO="sudo -n "
fi

if [ "$DRY" = 1 ]; then
  log "dry-run: checking SSH to $USER@$HOST"
  # shellcheck disable=SC2029
  "${SSH[@]}" "$USER@$HOST" "echo ssh-ok; ${SUDO}id -u" || die "SSH check failed"
  log "dry-run OK — would join $HOST to $MESH"
  exit 0
fi

token="$(bash "$CARAVAN_DIR/tools/invite.sh" --token-only --dir "$CARAVAN_DIR" | tail -n1)"
[ -n "$token" ] || die "could not mint a join token"

JOIN_ARGS="--hub $MESH --token $token"
if [ -n "$NAME" ]; then JOIN_ARGS="$JOIN_ARGS --name $NAME"; fi
if [ -n "$ENGINE" ]; then JOIN_ARGS="$JOIN_ARGS --engine $ENGINE"; fi
remote="curl -fsSL https://raw.githubusercontent.com/leodev-2022/caravan/main/tools/node-join.sh | ${SUDO}bash -s -- $JOIN_ARGS"

log "provisioning $USER@$HOST (this can take a few minutes)"
# shellcheck disable=SC2029
out="$("${SSH[@]}" "$USER@$HOST" "$remote" 2>&1)" || {
  printf '%s\n' "$out" | tail -n 20
  die "provisioning failed"
}
printf '%s\n' "$out" | tail -n 6

ip="$(printf '%s\n' "$out" | sed -n 's/.*mesh-ip=\([0-9.]*\).*/\1/p' | tail -n1)"
port="$(printf '%s\n' "$out" | sed -n 's/.*port=\([0-9]*\).*/\1/p' | tail -n1)"
if [ -n "$ip" ]; then
  reg_name="${NAME:-$(printf '%s' "$HOST" | tr '.' '-')}"
  log "registering $reg_name ($ip:${port:-9898})"
  bash "$CARAVAN_DIR/tools/add-node.sh" --name "$reg_name" --ip "$ip" --port "${port:-9898}" --dir "$CARAVAN_DIR"
else
  warn "could not detect the mesh IP; register the node manually"
fi
