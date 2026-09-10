#!/usr/bin/env bash
# backup.sh — back up the Caravan hub (configs + headscale DB + caddy data).
# Run on the hub (root).
#   sudo bash backup.sh [--dir DIR] [--out DIR]
# Set BACKUP_PASSPHRASE to encrypt the archive (openssl aes-256).
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
OUT_DIR="${BACKUP_DIR:-/opt/backups}"

usage() {
  cat <<'EOF'
Caravan — back up the hub

Usage: sudo bash backup.sh [--dir DIR] [--out DIR]

  --dir DIR   hub directory (default: /opt/caravan)
  --out DIR   output directory (default: /opt/backups)
  BACKUP_PASSPHRASE   if set, encrypt the archive (aes-256-cbc)
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dir) CARAVAN_DIR="${2:?--dir needs a value}"; shift 2 ;;
    --out) OUT_DIR="${2:?--out needs a value}"; shift 2 ;;
    -h | --help) usage; exit 0 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

require_root
[ -f "$CARAVAN_DIR/docker-compose.yaml" ] || die "no stack found in $CARAVAN_DIR"

PROJECT="$(basename "$CARAVAN_DIR")"
HS_VOL="${HS_VOL:-${PROJECT}_headscale-data}"
CADDY_DATA="${CADDY_DATA:-${PROJECT}_caddy-data}"
CADDY_CFG="${CADDY_CONFIG:-${PROJECT}_caddy-config}"

TS="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/caravan-$TS.tar.gz"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/config" "$TMP/volumes/headscale" "$TMP/volumes/caddy-data" "$TMP/volumes/caddy-config"

log "copying configs from $CARAVAN_DIR"
cp -a "$CARAVAN_DIR/." "$TMP/config/"

dump_vol() {
  docker run --rm -v "$1:/data" -v "$2:/b" alpine sh -c 'cp -a /data/. /b/' 2>/dev/null ||
    warn "volume not found (skipped): $1"
}
log "dumping volumes"
dump_vol "$HS_VOL" "$TMP/volumes/headscale"
dump_vol "$CADDY_DATA" "$TMP/volumes/caddy-data"
dump_vol "$CADDY_CFG" "$TMP/volumes/caddy-config"

tar -czf "$OUT" -C "$TMP" config volumes
chmod 600 "$OUT"

if [ -n "${BACKUP_PASSPHRASE:-}" ]; then
  openssl enc -aes-256-cbc -pbkdf2 -salt -in "$OUT" -out "$OUT.enc" -pass env:BACKUP_PASSPHRASE
  rm -f "$OUT"
  OUT="$OUT.enc"
  chmod 600 "$OUT"
  log "archive encrypted"
fi

log "backup: $OUT ($(du -h "$OUT" | cut -f1))"
