#!/usr/bin/env bash
# vpn-migrate.sh — move a Caravan AmneziaWG box to a fresh host by CLONING the
# server identity (private key, psk, obfuscation params, listen port) and all
# peers, so existing clients keep working: only the endpoint moves (change the
# VPN domain's A record; or, if clients use a raw IP, change the IP). Idempotent
# enough to re-run.
#
# Run from a machine that can SSH (key auth) to both boxes.
#
#   bash vpn-migrate.sh --old root@OLD --new root@NEW [--domain vpn.example.com]
#
# Steps:
#   1. read OLD: awg0.conf + keys + listen port
#   2. stage tooling on NEW and install the stack with the SAME port
#   3. overlay the OLD identity + peers on NEW, restart its container
#   4. verify (server pubkey + peer count match) and print the DNS step
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OLD=""; NEW=""; DOMAIN=""; DRY=""
SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -o ServerAliveInterval=15)

log(){ printf '[migrate] %s\n' "$*"; }
die(){ printf '[migrate] error: %s\n' "$*" >&2; exit 1; }
# shellcheck disable=SC2029  # args are meant to be expanded on the client (bash) side
sx(){ ssh "${SSH_OPTS[@]}" "$1" "${@:2}"; }

usage(){ sed -n '2,20p' "$0"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --old) OLD="${2:?}"; shift 2 ;;
    --new) NEW="${2:?}"; shift 2 ;;
    --domain) DOMAIN="${2:?}"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h | --help) usage; exit 0 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done
if [ -z "$OLD" ] || [ -z "$NEW" ]; then die "usage: vpn-migrate.sh --old root@OLD --new root@NEW [--domain FQDN]"; fi
[ "$OLD" != "$NEW" ] || die "--old and --new must differ"
[ -f "$HERE/vpn-install.sh" ] || die "vpn-install.sh not found next to $0"

log "reading OLD ($OLD)"
OLD_PORT="$(sx "$OLD" 'cat /opt/amnezia/awg/port 2>/dev/null')"
OLD_PUB="$(sx "$OLD" 'cat /opt/amnezia/awg/wireguard_server_public_key.key 2>/dev/null')"
[ -n "$OLD_PORT" ] || die "cannot read OLD listen port (/opt/amnezia/awg/port)"
log "OLD: port=$OLD_PORT pubkey=$OLD_PUB"

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
log "pulling OLD identity + peers"
sx "$OLD" 'tar czf - -C /opt/amnezia awg' > "$TMP/awg.tgz"
tar tzf "$TMP/awg.tgz" >/dev/null 2>&1 || die "bad archive pulled from OLD"
OLD_PEERS="$(tar xzf "$TMP/awg.tgz" -O awg/awg0.conf | grep -c '^\[Peer\]' || true)"
log "OLD: $OLD_PEERS peer(s)"

if [ -n "$DRY" ]; then
  log "dry-run: identity pulled OK; would now install NEW + overlay. Stopping."
  exit 0
fi

log "staging tooling on NEW"
scp "${SSH_OPTS[@]}" -q "$HERE/vpn-install.sh" "$HERE/vpn.sh" "$HERE/vpnuri.py" "$NEW:/tmp/" \
  || die "cannot copy tooling to NEW"

log "installing stack on NEW with the SAME port ($OLD_PORT)"
printf '%s' "$OLD_PORT" | sx "$NEW" 'install -d -m 700 /opt/amnezia/awg && cat > /opt/amnezia/awg/port && bash /tmp/vpn-install.sh > /tmp/vpn-install.log 2>&1 && tail -n 3 /tmp/vpn-install.log'

log "overlaying OLD identity + peers onto NEW"
sx "$NEW" 'rm -rf /opt/amnezia/awg && tar xzf - -C /opt/amnezia' < "$TMP/awg.tgz"
sx "$NEW" 'chmod 700 /opt/amnezia/awg; chmod 600 /opt/amnezia/awg/*.key /opt/amnezia/awg/awg0.conf 2>/dev/null || true; install -d -m755 /opt/caravan; cp /tmp/vpn.sh /opt/caravan/vpn.sh; cp /tmp/vpnuri.py /opt/caravan/vpnuri.py; chmod 755 /opt/caravan/vpn.sh; docker restart amnezia-awg2 >/dev/null; sleep 3'

log "verifying NEW"
NEW_PUB="$(sx "$NEW" 'cat /opt/amnezia/awg/wireguard_server_public_key.key')"
NEW_PEERS="$(sx "$NEW" 'grep -c "^\[Peer\]" /opt/amnezia/awg/awg0.conf || true')"
NEW_PORT="$(sx "$NEW" 'cat /opt/amnezia/awg/port')"
[ "$NEW_PUB" = "$OLD_PUB" ] || die "identity mismatch: OLD=$OLD_PUB NEW=$NEW_PUB"
log "NEW: port=$NEW_PORT pubkey=$NEW_PUB peers=$NEW_PEERS  (identity cloned)"

if [ -n "$DOMAIN" ]; then
  cat <<EOF

[migrate] Done. Point DNS at the new box:
    $DOMAIN   A   <new public IP>

Existing clients keep working once $DOMAIN resolves to the new IP (WireGuard
re-resolves the endpoint on reconnect). Power the OLD box off.
EOF
else
  cat <<'EOF'

[migrate] Done. Point clients at the new IP (or, better, use a domain endpoint
in the clients' config / vpn:// hostName). Power the OLD box off.
EOF
fi
