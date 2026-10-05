#!/usr/bin/env bash
# restore.sh — restore the Caravan hub from a backup made by backup.sh.
# Run on the hub (root). Stops the stack, restores configs + volumes, starts it.
#   sudo bash restore.sh --file /opt/backups/caravan-<ts>.tar.gz
# Set BACKUP_PASSPHRASE if the archive is encrypted.
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
ARCHIVE=""

usage() {
  cat <<'EOF'
Caravan — restore the hub from a backup

Usage: sudo bash restore.sh --file ARCHIVE [--dir DIR]

  --file ARCHIVE   backup archive (.tar.gz or .tar.gz.enc)
  --dir DIR        hub directory (default: /opt/caravan)
  BACKUP_PASSPHRASE   required if the archive is encrypted
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --file) ARCHIVE="${2:?--file needs a value}"; shift 2 ;;
    --dir) CARAVAN_DIR="${2:?--dir needs a value}"; shift 2 ;;
    -h | --help) usage; exit 0 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

require_root
[ -n "$ARCHIVE" ] || die "--file is required"
[ -f "$ARCHIVE" ] || die "no such archive: $ARCHIVE"

PROJECT="$(basename "$CARAVAN_DIR")"
HS_VOL="${HS_VOL:-${PROJECT}_headscale-data}"
CADDY_DATA="${CADDY_DATA:-${PROJECT}_caddy-data}"
CADDY_CFG="${CADDY_CONFIG:-${PROJECT}_caddy-config}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

log "extracting $ARCHIVE"
case "$ARCHIVE" in
  *.enc)
    [ -n "${BACKUP_PASSPHRASE:-}" ] || die "set BACKUP_PASSPHRASE to decrypt $ARCHIVE"
    openssl enc -d -aes-256-cbc -pbkdf2 -in "$ARCHIVE" -out "$TMP/backup.tar.gz" -pass env:BACKUP_PASSPHRASE
    tar -xzf "$TMP/backup.tar.gz" -C "$TMP"
    ;;
  *)
    tar -xzf "$ARCHIVE" -C "$TMP"
    ;;
esac
[ -d "$TMP/config" ] || die "not a Caravan backup (missing config/)"

if [ -f "$CARAVAN_DIR/docker-compose.yaml" ]; then
  log "stopping the stack"
  (cd "$CARAVAN_DIR" && docker compose down) || warn "compose down returned non-zero"
fi

log "restoring configs -> $CARAVAN_DIR"
mkdir -p "$CARAVAN_DIR"
cp -a "$TMP/config/." "$CARAVAN_DIR/"

restore_vol() {
  [ -d "$2" ] || return 0
  docker run --rm -v "$1:/data" -v "$2:/b" alpine sh -c 'rm -rf /data/* 2>/dev/null; cp -a /b/. /data/' 2>/dev/null ||
    warn "could not restore volume: $1"
}
log "restoring volumes"
restore_vol "$HS_VOL" "$TMP/volumes/headscale"
restore_vol "$CADDY_DATA" "$TMP/volumes/caddy-data"
restore_vol "$CADDY_CFG" "$TMP/volumes/caddy-config"

log "starting the stack"
(cd "$CARAVAN_DIR" && docker compose up -d)

log "restore done from $ARCHIVE"
