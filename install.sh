#!/usr/bin/env bash
# Caravan hub installer (idempotent). Run as root on a fresh Ubuntu/Debian VPS.
#   sudo bash install.sh --domain example.com
#   sudo bash install.sh --sslip
#   sudo bash install.sh --self-signed
#
# Stages are added incrementally (see docs/roadmap.md).
#   [2.2] Docker + Compose
#   [2.3] secrets (Authelia) + stack .env
#   [2.4] lay out the stack in $CARAVAN_DIR + render configs
#   [2.5] TLS modes: --domain / --sslip / --self-signed
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

# Self-bootstrap: when run via `curl ... | sudo bash`, the repo files are not
# next to us — fetch the repo and re-exec from there.
if [ ! -f "$HERE/scripts/lib.sh" ]; then
  _tarball="${CARAVAN_TARBALL:-https://github.com/leodev-2022/caravan/archive/refs/heads/main.tar.gz}"
  _tmp="$(mktemp -d)"
  echo "[caravan] fetching $_tarball"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$_tarball" | tar xz -C "$_tmp"
  else
    wget -qO- "$_tarball" | tar xz -C "$_tmp"
  fi
  _script="$(ls -d "$_tmp"/caravan-*/install.sh | head -n1)"
  exec bash "$_script" "$@"
fi

# shellcheck source=scripts/lib.sh
. "$HERE/scripts/lib.sh"

CARAVAN_DIR="${CARAVAN_DIR:-/opt/caravan}"
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASSWORD_SHOWN=""

usage() {
  cat <<'EOF'
Caravan hub installer

Usage: sudo bash install.sh [--domain NAME | --sslip | --self-signed]

  --domain NAME   real domain with DNS A -> this server (ACME/Let's Encrypt)
  --sslip         use <public-ip>.sslip.io (ACME; no domain needed)
  --self-signed   Caddy internal CA (no public DNS/ports; browser warning)
  --update        pull latest images and re-apply (keeps secrets/config/DB)
  --dry-run       resolve the domain/TLS and print the plan, then exit
EOF
}

TLS_MODE=""
DOMAIN_FLAG=""
SSLIP=0
SELF_SIGNED=0
UPDATE=0
DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --domain)
      [ $# -ge 2 ] || die "--domain needs a value"
      DOMAIN_FLAG="$2"
      shift 2
      ;;
    --sslip)
      SSLIP=1
      shift
      ;;
    --self-signed)
      SELF_SIGNED=1
      shift
      ;;
    --update)
      UPDATE=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
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
detect_os

case "$OS_ID" in
  ubuntu | debian) : ;;
  *) die "unsupported OS: ${OS_ID:-unknown} (Ubuntu/Debian expected)" ;;
esac

load_config() {
  local f=""
  [ -f "$CARAVAN_DIR/caravan.env" ] && f="$CARAVAN_DIR/caravan.env"
  [ -z "$f" ] && [ -f "$HERE/caravan.env" ] && f="$HERE/caravan.env"
  if [ -n "$f" ]; then
    # shellcheck disable=SC1090
    . "$f"
    log "config loaded: $f"
  else
    warn "no caravan.env found — using flags/defaults (see caravan.env.example)"
  fi
  DOMAIN="${DOMAIN:-}"
  EMAIL="${EMAIL:-}"
  HUB_IP="${HUB_IP:-}"
  TZ="${TZ:-UTC}"
  TLS_MODE="${TLS_MODE:-acme}"
}

resolve_tls() {
  local ip=""
  # zero questions: if no domain was given, fall back to <public-ip>.sslip.io
  if [ "$SSLIP" = 1 ] || [ -z "$DOMAIN" ]; then
    ip="${HUB_IP:-}"
    if [ -z "$ip" ]; then
      ip="$(curl -fsS --max-time 8 https://api.ipify.org 2>/dev/null ||
        curl -fsS --max-time 8 https://ifconfig.me 2>/dev/null || true)"
    fi
    [ -n "$ip" ] || die "cannot determine public IP — set HUB_IP in caravan.env or pass --domain"
    DOMAIN="$(printf '%s' "$ip" | tr '.' '-').sslip.io"
    SSLIP=1
    log "no domain given — using sslip.io: $DOMAIN"
  fi
  [ -n "$EMAIL" ] || EMAIL="admin@${DOMAIN}"
  TLS_MODE="${TLS_MODE:-acme}"
  export DOMAIN EMAIL HUB_IP TZ TLS_MODE
  log "TLS: mode=${TLS_MODE} domain=${DOMAIN}"
}

install_docker() {
  if have docker && docker compose version >/dev/null 2>&1; then
    log "docker + compose already present ($(docker --version | cut -d, -f1))"
    return 0
  fi
  log "installing Docker + Compose (official apt repo)"
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl gnupg >/dev/null
  install -m 0755 -d /etc/apt/keyrings
  if [ ! -s /etc/apt/keyrings/docker.asc ]; then
    retry curl -fsSL "https://download.docker.com/linux/${OS_ID}/gpg" -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
  fi
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${OS_ID} ${OS_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
  systemctl enable --now docker
  log "docker installed: $(docker --version)"
}

install_python() {
  if have python3 && python3 -c 'import yaml' >/dev/null 2>&1; then
    log "python3 + PyYAML already present"
    return 0
  fi
  log "installing python3 + PyYAML"
  apt-get update -qq
  apt-get install -y -qq python3 python3-yaml >/dev/null
}

install_secrets() {
  mkdir -p "$CARAVAN_DIR"
  chmod 755 "$CARAVAN_DIR"
  local fresh=0 out
  [ -f "$CARAVAN_DIR/secrets.env" ] || fresh=1
  out="$(SECRETS_FILE="$CARAVAN_DIR/secrets.env" ADMIN_USER="$ADMIN_USER" \
    bash "$HERE/scripts/gen-secrets.sh")"
  printf '%s\n' "$out"
  ADMIN_PASSWORD_SHOWN="$(printf '%s\n' "$out" | sed -n 's/.*admin password: *\([^ ]*\).*/\1/p' | head -n1)"
  if [ "$fresh" = 1 ]; then
    # a freshly generated encryption key makes any pre-existing Authelia DB
    # unusable; drop stale runtime state so it is recreated cleanly.
    rm -f "$CARAVAN_DIR/authelia/db.sqlite" "$CARAVAN_DIR/authelia/notification.txt"
  fi
}

write_env() {
  local envf="$CARAVAN_DIR/.env"
  if [ -f "$envf" ]; then
    log ".env already present ($envf) — keeping"
    return 0
  fi
  umask 077
  {
    echo "# Caravan stack env (root-only, mode 600). Generated by install.sh."
    echo "TZ=${TZ:-UTC}"
    echo "TELEGRAM_TOKEN=${TELEGRAM_TOKEN:-REPLACE_ME}"
    echo "TELEGRAM_CHAT=${TELEGRAM_CHAT:-REPLACE_ME}"
    echo "CODENOMAD_HS_KEY=REPLACE_ME"
  } > "$envf"
  chmod 600 "$envf"
  log "wrote $envf (mode 600)"
}

layout_stack() {
  log "laying out stack in $CARAVAN_DIR"
  mkdir -p "$CARAVAN_DIR"/{conf,tools,systemd,authelia,headscale,caddy,requests}
  cp -f "$HERE/compose/docker-compose.yaml" "$CARAVAN_DIR/docker-compose.yaml"
  cp -f "$HERE/generate_caddy.py" "$HERE/render.py" "$HERE/status.py" "$CARAVAN_DIR/"
  cp -f "$HERE/conf/"*.yml "$HERE/conf/"*.yaml "$CARAVAN_DIR/conf/"
  cp -f "$HERE/tools/"*.py "$HERE/tools/"*.sh "$CARAVAN_DIR/tools/" 2>/dev/null || true
  cp -f "$HERE/systemd/"*.service "$HERE/systemd/"*.path "$CARAVAN_DIR/systemd/" 2>/dev/null || true
  if [ ! -f "$CARAVAN_DIR/nodes.yaml" ]; then
    cp -f "$HERE/conf/nodes.example.yaml" "$CARAVAN_DIR/nodes.yaml"
  fi
}

write_stack_config() {
  local f="$CARAVAN_DIR/caravan.env"
  {
    echo "# Caravan hub config (non-secret) — written by install.sh."
    echo "DOMAIN=$DOMAIN"
    echo "EMAIL=$EMAIL"
    echo "HUB_IP=${HUB_IP:-}"
    echo "TZ=${TZ:-UTC}"
    echo "TLS_MODE=${TLS_MODE:-acme}"
  } > "$f"
  chmod 644 "$f"
  log "wrote $f (domain=$DOMAIN, tls=$TLS_MODE)"
}

render_configs() {
  log "rendering configs (Caddyfile, Authelia, Headscale)"
  if [ -f "$CARAVAN_DIR/caravan.env" ]; then
    # stack config is the source of truth (may differ from the repo copy)
    # shellcheck disable=SC1090
    set -a
    . "$CARAVAN_DIR/caravan.env"
    set +a
  fi
  if ! grep -q '^ADMIN_PASSWORD_HASH=' "$CARAVAN_DIR/secrets.env"; then
    warn "no ADMIN_PASSWORD_HASH in secrets.env — Authelia login will not work until it is set"
  fi
  (
    cd "$CARAVAN_DIR"
    python3 generate_caddy.py
    python3 render.py conf/authelia-config.template.yml authelia/configuration.yml \
      "@secrets.env" "DOMAIN=$DOMAIN"
    python3 render.py conf/users_database.template.yml authelia/users_database.yml \
      "@secrets.env" "ADMIN_EMAIL=${EMAIL:-admin@${DOMAIN}}"
    python3 render.py conf/headscale-config.template.yml headscale/config.yaml \
      "DOMAIN=$DOMAIN"
    chmod 600 authelia/configuration.yml authelia/users_database.yml
  )
}

pull_images() {
  log "pulling latest images (--update)"
  (
    cd "$CARAVAN_DIR"
    docker compose pull
  )
}

start_stack() {
  log "starting the stack (docker compose up -d)"
  (
    cd "$CARAVAN_DIR"
    docker compose up -d
    sleep 3
    docker compose ps
  )
}

print_summary() {
  echo
  log "Caravan hub is up."
  printf '    portal : https://hub.%s\n' "$DOMAIN"
  printf '    SSO    : https://auth.%s\n' "$DOMAIN"
  printf '    mesh   : https://mesh.%s\n' "$DOMAIN"
  printf '    login  : %s\n' "$ADMIN_USER"
  if [ -n "$ADMIN_PASSWORD_SHOWN" ]; then
    printf '    password: %s   (shown once — store it now)\n' "$ADMIN_PASSWORD_SHOWN"
  else
    printf '    password: unchanged (set ADMIN_PASSWORD and re-run scripts/gen-secrets.sh to reset)\n'
  fi
  printf '    first login: register TOTP when prompted\n'
  if [ "$TLS_MODE" = internal ]; then
    printf '    note: self-signed cert — the browser will warn; accept to continue\n'
  fi
}

warn_early_stage() {
  printf '\n\033[1;33m%s\033[0m\n' "WARNING: Caravan is early-stage (pre-1.0) software — use at your own risk."
  cat <<'EOF'
  * Install on a FRESH / throwaway machine (VM, LXC, or a spare VPS) —
    NOT on a server with critical data or production workloads.
  * Back up anything important first. The installer changes the system
    (installs Docker, uses ports 80/443, runs containers, writes configs).
  * MIT licence: provided "as is", without warranty of any kind.
EOF
  if [ -t 0 ] && [ "${CARAVAN_YES:-0}" != "1" ]; then
    printf 'Continue? [y/N] '
    read -r ans
    case "$ans" in y | Y | yes | YES) : ;; *) die "aborted by user" ;; esac
  fi
}

main() {
  warn_early_stage
  load_config
  [ -n "$DOMAIN_FLAG" ] && DOMAIN="$DOMAIN_FLAG"
  [ "$SELF_SIGNED" = 1 ] && TLS_MODE="internal"
  resolve_tls
  if [ "$DRY_RUN" = 1 ]; then
    log "dry-run: dir=$CARAVAN_DIR tls=$TLS_MODE domain=$DOMAIN"
    return 0
  fi
  install_docker
  install_secrets
  write_env
  install_python
  layout_stack
  write_stack_config
  render_configs
  [ "$UPDATE" = 1 ] && pull_images
  start_stack
  print_summary
  log "stage done: docker + compose + secrets + .env + stack + configs (tls=$TLS_MODE)"
}

main "$@"
