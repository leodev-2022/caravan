#!/usr/bin/env bash
# Caravan shared shell helpers. Source this file, do not execute it:
#   . "$(dirname "$0")/lib.sh"
#
# Provides: log/warn/err/die, require_root, detect_os, retry, have.

# --- logging ---------------------------------------------------------------
log()  { printf '\033[1;34m[caravan]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[caravan]\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31m[caravan]\033[0m %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }

# --- misc ------------------------------------------------------------------
have() { command -v "$1" >/dev/null 2>&1; }

require_root() {
  [ "$(id -u)" -eq 0 ] || die "must run as root (try: sudo $0)"
}

# Sets OS_ID, OS_VERSION_ID, OS_CODENAME, OS_ARCH (exported).
detect_os() {
  OS_ID=""; OS_VERSION_ID=""; OS_CODENAME=""; OS_ARCH="$(uname -m)"
  if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    OS_ID="${ID:-}"; OS_VERSION_ID="${VERSION_ID:-}"; OS_CODENAME="${VERSION_CODENAME:-}"
  fi
  export OS_ID OS_VERSION_ID OS_CODENAME OS_ARCH
}

# retry <cmd...> — up to RETRY_TRIES (default 3), RETRY_DELAY seconds apart.
retry() {
  local tries="${RETRY_TRIES:-3}" delay="${RETRY_DELAY:-3}" n=1
  until "$@"; do
    if [ "$n" -ge "$tries" ]; then
      warn "command failed after $n attempts: $*"
      return 1
    fi
    warn "attempt $n failed; retrying in ${delay}s: $*"
    sleep "$delay"
    n=$((n + 1))
  done
}
