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
ADMIN_OTPAUTH=""

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
  local ip="" local_ip=""
  # zero questions: if no domain was given, fall back to <ip>.sslip.io
  if [ "$SSLIP" = 1 ] || [ -z "$DOMAIN" ]; then
    ip="${HUB_IP:-}"
    if [ -z "$ip" ]; then
      ip="$(curl -fsS --max-time 8 https://api.ipify.org 2>/dev/null ||
        curl -fsS --max-time 8 https://ifconfig.me 2>/dev/null || true)"
    fi
    [ -n "$ip" ] || die "cannot determine public IP — set HUB_IP in caravan.env or pass --domain"
    local_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
    # If the public IP is not bound to this host, we are behind NAT: sslip.io +
    # ACME (HTTP-01 on :80) cannot validate, and a public-IP name would not route
    # back to us either. Use the local IP and (unless asked for a real domain)
    # the internal CA, so the browser still reaches us.
    if ! ip -4 -o addr show 2>/dev/null | grep -qw "$ip"; then
      if [ "$TLS_MODE" != "internal" ]; then
        warn "public IP $ip is not on this machine (behind NAT?) — sslip.io/ACME would fail"
        warn "falling back to --self-signed (browser will warn); pass --domain NAME for trusted TLS"
        TLS_MODE="internal"
      fi
      ip="${local_ip:-$ip}"
    fi
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
  log "this can take a few minutes and prints little — it is not stuck"
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
  log "generating secrets (the admin password hash pulls Authelia — can take ~1 min)"
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

install_provision_key() {
  # keypair the hub uses to provision nodes over SSH. The portal shows the
  # public half, so a new machine only needs it in ~/.ssh/authorized_keys.
  local d="$CARAVAN_DIR/.ssh"
  mkdir -p "$d"
  chmod 700 "$d"
  if [ ! -f "$d/id_ed25519" ]; then
    have ssh-keygen || apt-get install -y -qq openssh-client >/dev/null 2>&1 || true
    ssh-keygen -t ed25519 -N "" -C caravan-provision -f "$d/id_ed25519" -q 2>/dev/null || true
  fi
  chmod 600 "$d/id_ed25519" 2>/dev/null || true
  chmod 644 "$d/id_ed25519.pub" 2>/dev/null || true
}

join_hub_mesh() {
  # The hub must be on its own mesh: the portal checks node mesh IPs and Caddy
  # reverse-proxies to them, so without this every node would show offline.
  if have tailscale && tailscale status >/dev/null 2>&1; then
    log "hub is already on the mesh"
    return 0
  fi
  if ! have tailscale; then
    log "installing tailscale on the hub (so it can reach nodes)"
    retry curl -fsSL "https://pkgs.tailscale.com/stable/${OS_ID}/${OS_CODENAME}.noarmor.gpg" \
      -o /usr/share/keyrings/tailscale-archive-keyring.gpg
    retry curl -fsSL "https://pkgs.tailscale.com/stable/${OS_ID}/${OS_CODENAME}.tailscale-keyring.list" \
      -o /etc/apt/sources.list.d/tailscale.list
    apt-get update -qq || warn "apt-get update reported errors; continuing"
    apt-get install -y -qq tailscale >/dev/null
  fi
  if [ "$TLS_MODE" = internal ]; then
    # trust Caddy's local CA so tailscale can reach the self-signed control server
    if docker cp caddy:/data/caddy/pki/authorities/local/root.crt \
      /usr/local/share/ca-certificates/caravan-hub.crt >/dev/null 2>&1; then
      update-ca-certificates >/dev/null 2>&1 || true
    fi
  fi
  systemctl restart tailscaled 2>/dev/null || true
  sleep 2
  local users uid key
  users="$(docker exec headscale headscale users list -o json 2>/dev/null || echo '[]')"
  uid="$(printf '%s' "$users" | python3 -c 'import json,sys;u=json.load(sys.stdin);print(u[0]["id"] if u else "")')"
  if [ -z "$uid" ]; then
    docker exec headscale headscale users create caravan >/dev/null 2>&1 || true
    users="$(docker exec headscale headscale users list -o json 2>/dev/null || echo '[]')"
    uid="$(printf '%s' "$users" | python3 -c 'import json,sys;print(json.load(sys.stdin)[0]["id"])')"
  fi
  key="$(docker exec headscale headscale preauthkeys create --user "$uid" \
    --reusable --expiration 1h 2>/dev/null | tail -n1)"
  if [ -z "$key" ]; then
    warn "could not mint a mesh key — the hub stays off the mesh (nodes show offline)"
    return 0
  fi
  tailscale up --login-server="https://mesh.${DOMAIN}" --authkey="$key" \
    --hostname=caravan-hub --accept-dns=false >/dev/null 2>&1 ||
    warn "hub failed to join the mesh"
  sleep 3
  if tailscale ip -4 >/dev/null 2>&1; then
    log "hub joined the mesh ($(tailscale ip -4 | head -n1))"
  else
    warn "hub is not on the mesh — nodes will show offline until it is"
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
  mkdir -p "$CARAVAN_DIR"/{conf,tools,systemd,authelia,headscale,caddy,requests,state}
  cp -f "$HERE/compose/docker-compose.yaml" "$CARAVAN_DIR/docker-compose.yaml"
  cp -f "$HERE/generate_caddy.py" "$HERE/render.py" "$HERE/status.py" "$CARAVAN_DIR/"
  cp -f "$HERE/conf/"*.yml "$HERE/conf/"*.yaml "$CARAVAN_DIR/conf/"
  cp -f "$HERE/tools/"*.py "$HERE/tools/"*.sh "$CARAVAN_DIR/tools/" 2>/dev/null || true
  mkdir -p "$CARAVAN_DIR/scripts"
  cp -f "$HERE/scripts/lib.sh" "$CARAVAN_DIR/scripts/lib.sh"
  cp -f "$HERE/scripts/register-totp.py" "$CARAVAN_DIR/scripts/" 2>/dev/null || true
  cp -f "$HERE/systemd/"*.service "$HERE/systemd/"*.path "$CARAVAN_DIR/systemd/" 2>/dev/null || true
  if [ ! -f "$CARAVAN_DIR/nodes.yaml" ]; then
    # Start empty: never seed the example nodes into a real hub (they would
    # show up as phantom "offline" machines in the portal on first login).
    {
      echo "# Caravan environments (source of truth)."
      echo "# Add machines via the portal (+ Add / Invite) or tools/add-node.sh."
      echo "envs: []"
    } > "$CARAVAN_DIR/nodes.yaml"
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
  log "first run pulls images — this can take several minutes"
  (
    cd "$CARAVAN_DIR"
    docker compose up -d
    sleep 3
    docker compose ps
  )
}

register_admin_totp() {
  # Register the admin's TOTP programmatically so the first login needs no
  # browser "identity verification" dance. Only possible when we know the
  # plaintext password (a fresh install); on re-runs we skip it.
  [ -n "$ADMIN_PASSWORD_SHOWN" ] || return 0
  local script="$CARAVAN_DIR/scripts/register-totp.py"
  [ -f "$script" ] || script="$HERE/scripts/register-totp.py"
  [ -f "$script" ] || return 0
  log "waiting for Authelia to become ready"
  local i
  for i in $(seq 1 30); do
    curl -fsS -k --max-time 5 "https://auth.$DOMAIN/api/health" >/dev/null 2>&1 && break
    sleep 2
  done
  log "registering TOTP for '$ADMIN_USER' (no browser setup needed)"
  local otpauth=""
  otpauth="$(python3 "$script" --base "https://auth.$DOMAIN" --user "$ADMIN_USER" \
    --password "$ADMIN_PASSWORD_SHOWN" --notify "$CARAVAN_DIR/authelia/notification.txt" \
    --target "https://hub.$DOMAIN/" 2>/dev/null || true)"
  if [ -n "$otpauth" ]; then
    ADMIN_OTPAUTH="$otpauth"
  else
    warn "could not auto-register TOTP — register it in the Authelia UI on first login"
  fi
}

ensure_qrencode() {
  have qrencode && return 0
  have apt-get || return 1
  apt-get install -y -qq qrencode >/dev/null 2>&1 || return 1
  have qrencode
}

print_qr() {
  # $1 = text to encode; renders an ASCII QR that a phone can scan off-screen
  have qrencode || return 1
  qrencode -t ANSIUTF8 -o - "$1" 2>/dev/null
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
  if [ -n "$ADMIN_OTPAUTH" ]; then
    local secret="${ADMIN_OTPAUTH##*secret=}"
    secret="${secret%%&*}"
    printf '    TOTP   : scan this QR with your authenticator app (Google Authenticator, Aegis, ...):\n\n'
    if print_qr "$ADMIN_OTPAUTH"; then
      printf '\n'
      printf '             (if the QR will not scan, add the key below manually)\n'
    else
      printf '             (no qrencode — add manually) otpauth: %s\n' "$ADMIN_OTPAUTH"
    fi
    printf '             manual key: %s\n' "$secret"
    printf '             then log in with the 6-digit code it shows\n'
  else
    printf '    first login: register TOTP when prompted\n'
  fi
  if [ "$TLS_MODE" = internal ]; then
    printf '    note: self-signed cert — the browser will warn; accept to continue\n'
  fi
}

install_units() {
  log "installing host units (systemd)"
  mkdir -p /etc/systemd/system
  python3 "$CARAVAN_DIR/render.py" "$CARAVAN_DIR/systemd/codenomad-apply.path" \
    /etc/systemd/system/codenomad-apply.path "CARAVAN_DIR=$CARAVAN_DIR"
  python3 "$CARAVAN_DIR/render.py" "$CARAVAN_DIR/systemd/codenomad-apply.service" \
    /etc/systemd/system/codenomad-apply.service "CARAVAN_DIR=$CARAVAN_DIR"
  systemctl daemon-reload
  systemctl enable --now codenomad-apply.path
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
  # Ask on the controlling terminal so the prompt also works for
  # `curl ... | sudo bash` (where stdin is the pipe, not a TTY).
  if [ "${CARAVAN_YES:-0}" != "1" ] && [ -r /dev/tty ]; then
    printf 'Continue? [y/N] '
    read -r ans < /dev/tty || ans=""
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
  ensure_qrencode || true
  layout_stack
  install_provision_key
  write_stack_config
  render_configs
  install_units
  [ "$UPDATE" = 1 ] && pull_images
  start_stack
  join_hub_mesh
  register_admin_totp
  print_summary
  log "stage done: docker + compose + secrets + .env + stack + configs (tls=$TLS_MODE)"
}

main "$@"
