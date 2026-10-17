#!/usr/bin/env bash
# Remove the Caravan hub.
#   sudo bash scripts/uninstall.sh            # stop stack, keep data/secrets
#   sudo bash scripts/uninstall.sh --purge    # also delete $CARAVAN_DIR + volumes
#   sudo bash scripts/uninstall.sh --purge --remove-docker
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=scripts/lib.sh
. "$HERE/scripts/lib.sh"

CARAVAN_DIR="${CARAVAN_DIR:-/opt/caravan}"

usage() {
  cat <<'EOF'
Caravan hub uninstaller

Usage: sudo bash scripts/uninstall.sh [--purge] [--remove-docker]

  (default)        stop and remove containers; keep $CARAVAN_DIR (secrets/data)
  --purge          also delete $CARAVAN_DIR and the Docker volumes
  --remove-docker  also uninstall the Docker packages
EOF
}

PURGE=0
REMOVE_DOCKER=0
while [ $# -gt 0 ]; do
  case "$1" in
    --purge)
      PURGE=1
      shift
      ;;
    --remove-docker)
      REMOVE_DOCKER=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1 (try --help)"
      ;;
  esac
done

require_root

if [ -d "$CARAVAN_DIR" ] && [ -f "$CARAVAN_DIR/docker-compose.yaml" ]; then
  log "stopping the stack"
  if [ "$PURGE" = 1 ]; then
    (cd "$CARAVAN_DIR" && docker compose down --volumes) || warn "compose down returned non-zero"
  else
    (cd "$CARAVAN_DIR" && docker compose down) || warn "compose down returned non-zero"
  fi
else
  warn "no stack found at $CARAVAN_DIR"
fi

if [ "$PURGE" = 1 ]; then
  log "removing $CARAVAN_DIR (secrets/data)"
  rm -rf "$CARAVAN_DIR"
else
  log "keeping $CARAVAN_DIR — re-run with --purge to delete secrets/data"
fi

if [ "$REMOVE_DOCKER" = 1 ]; then
  log "removing Docker packages"
  apt-get purge -y docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin 2>/dev/null || true
  rm -rf /var/lib/docker /var/lib/containerd /etc/docker
fi

log "uninstall done"
