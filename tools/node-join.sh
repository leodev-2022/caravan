#!/usr/bin/env bash
# node-join.sh — join a (Ubuntu/Debian) machine to a Caravan hub as a node.
# Idempotent. Run as root (or with sudo).
#
#   sudo bash node-join.sh \
#     --hub https://mesh.example.com --token hskey-auth-XXXX \
#     --name web1 --user dev --workspace-root /opt --bypass-vpn --stt
#
# After it finishes, note the mesh IPv4 shown and register it on the hub
# (portal "add env" or nodes.yaml + generate_caddy.py).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

# Self-bootstrap: when run via `curl ... | sudo bash -s -- ...`, the repo files
# are not next to us — fetch the repo and re-exec from there.
if [ ! -f "$HERE/lib.sh" ] && [ ! -f "$HERE/../scripts/lib.sh" ]; then
  _tarball="${CARAVAN_TARBALL:-https://github.com/leodev-2022/caravan/archive/refs/heads/main.tar.gz}"
  _tmp="$(mktemp -d)"
  echo "[caravan] fetching $_tarball"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$_tarball" | tar xz -C "$_tmp"
  else
    wget -qO- "$_tarball" | tar xz -C "$_tmp"
  fi
  _script="$(ls -d "$_tmp"/caravan-*/tools/node-join.sh | head -n1)"
  exec bash "$_script" "$@"
fi

if [ -f "$HERE/lib.sh" ]; then
  # shellcheck source=lib.sh
  . "$HERE/lib.sh"
else
  # shellcheck source=../scripts/lib.sh
  . "$HERE/../scripts/lib.sh"
fi

usage() {
  cat <<'EOF'
Caravan node onboarding

Usage: sudo bash node-join.sh --hub URL --token KEY [options]

  --hub URL            Headscale URL of the hub (e.g. https://mesh.example.com)
  --token KEY          Headscale preauth key (hskey-auth-...)
  --name NAME          node name in the mesh (default: hostname)
  --user USER          user that owns the workspace (default: sudo user)
  --workspace-root P   directory CodeNomad may browse (default: user's home)
  --port N             HTTP port (default: 9898 codenomad / 4096 opencode)
  --engine NAME        node engine: codenomad (default) or opencode (web UI)
  --dry-run            print the plan (engine/port/user) and exit
  --bypass-vpn         route hub/mesh traffic directly when the node full-tunnels
  --hub-ip IP          hub public IP (auto-resolved from --hub when needed)
  --stt                enable local speech-to-text (speaches) with the model
                       recommended for this machine's resources
  --stt-check          print the STT recommendation for this machine and exit
  --stt-model NAME     use an explicit Whisper model (implies --stt)
  --stt-gpu            force the CUDA image (implies --stt)
  --stt-cpu            force the CPU image (implies --stt)
  --stt-image IMG      explicit speaches image (implies --stt)
  --uninstall          remove Caravan node services (keeps files/packages)
  --purge              with --uninstall: also remove tailscale + STT container
EOF
}

NODE_PORT=""
ENGINE="codenomad"
DRY_RUN=0
WITH_STT=0
STT_MODEL=""
STT_IMAGE=""
STT_GPU=0
STT_CPU=0
STT_CHECK=0
BYPASS_VPN=0
UNINSTALL=0
PURGE=0
WORKSPACE_ROOT=""
NODE_NAME=""
RUN_USER=""
HEADSCALE_URL=""
PREAUTH_KEY=""
HUB_IP=""

while [ $# -gt 0 ]; do
  case "$1" in
    --hub) HEADSCALE_URL="${2:?--hub needs a value}"; shift 2 ;;
    --token) PREAUTH_KEY="${2:?--token needs a value}"; shift 2 ;;
    --name) NODE_NAME="${2:?--name needs a value}"; shift 2 ;;
    --user) RUN_USER="${2:?--user needs a value}"; shift 2 ;;
    --workspace-root) WORKSPACE_ROOT="${2:?--workspace-root needs a value}"; shift 2 ;;
    --port) NODE_PORT="${2:?--port needs a value}"; shift 2 ;;
    --engine) ENGINE="${2:?--engine needs a value}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --hub-ip) HUB_IP="${2:?--hub-ip needs a value}"; shift 2 ;;
    --bypass-vpn) BYPASS_VPN=1; shift ;;
    --stt) WITH_STT=1; shift ;;
    --stt-check) STT_CHECK=1; shift ;;
    --stt-model) WITH_STT=1; STT_MODEL="${2:?--stt-model needs a value}"; shift 2 ;;
    --stt-gpu) WITH_STT=1; STT_GPU=1; shift ;;
    --stt-cpu) WITH_STT=1; STT_CPU=1; shift ;;
    --stt-image) WITH_STT=1; STT_IMAGE="${2:?--stt-image needs a value}"; shift 2 ;;
    --uninstall) UNINSTALL=1; shift ;;
    --purge) PURGE=1; shift ;;
    -h | --help) usage; exit 0 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

require_root
detect_os
case "$OS_ID" in
  ubuntu | debian) : ;;
  *) die "unsupported OS: ${OS_ID:-unknown} (Ubuntu/Debian expected)" ;;
esac

if [ "$UNINSTALL" = 0 ] && [ "$STT_CHECK" = 0 ]; then
  NODE_NAME="${NODE_NAME:-$(hostname)}"
  RUN_USER="${RUN_USER:-${SUDO_USER:-root}}"
  [ -n "$HEADSCALE_URL" ] || die "--hub is required"
  [ -n "$PREAUTH_KEY" ] || die "--token is required"
  log "$NODE_NAME -> $HEADSCALE_URL as user $RUN_USER (engine=$ENGINE)"
fi

case "$ENGINE" in
  codenomad | opencode) : ;;
  *) die "unknown engine: $ENGINE (codenomad | opencode)" ;;
esac
if [ -z "$NODE_PORT" ]; then
  if [ "$ENGINE" = opencode ]; then NODE_PORT=4096; else NODE_PORT=9898; fi
fi

ensure_base_deps() {
  have curl && return 0
  log "installing base deps (curl, ca-certificates)"
  apt-get update -qq || warn "apt-get update reported errors; continuing"
  apt-get install -y -qq curl ca-certificates >/dev/null
}

install_node() {
  if have node; then
    log "node already present ($(node --version))"
    return 0
  fi
  log "installing Node.js 22 (NodeSource)"
  retry bash -c 'curl -fsSL https://deb.nodesource.com/setup_22.x | bash -'
  apt-get install -y -qq nodejs >/dev/null
}

install_engine() {
  if [ "$ENGINE" = opencode ]; then
    if have opencode; then
      log "opencode already present"
      return 0
    fi
    log "installing opencode (npm -g)"
    npm install -g opencode-ai >/dev/null
  else
    if have codenomad; then
      log "codenomad already present"
      return 0
    fi
    log "installing opencode + codenomad (npm -g)"
    npm install -g opencode-ai @neuralnomads/codenomad >/dev/null
  fi
}

install_tailscale() {
  have tailscale && return 0
  log "installing tailscale (apt repo)"
  local codename="${OS_CODENAME:-}"
  [ -n "$codename" ] || die "cannot detect distro codename (OS_CODENAME)"
  retry curl -fsSL "https://pkgs.tailscale.com/stable/${OS_ID}/${codename}.noarmor.gpg" \
    -o /usr/share/keyrings/tailscale-archive-keyring.gpg
  retry curl -fsSL "https://pkgs.tailscale.com/stable/${OS_ID}/${codename}.tailscale-keyring.list" \
    -o /etc/apt/sources.list.d/tailscale.list
  apt-get update -qq || warn "apt-get update reported errors; continuing"
  apt-get install -y -qq tailscale >/dev/null
}

join_mesh() {
  install_tailscale
  if tailscale status >/dev/null 2>&1; then
    log "already joined to the mesh"
  else
    log "joining mesh as $NODE_NAME"
    tailscale up --login-server="$HEADSCALE_URL" --authkey="$PREAUTH_KEY" \
      --hostname="$NODE_NAME" --accept-dns=false
  fi
  sleep 4
}

write_unit() {
  local node_bin workspace wsroot
  node_bin="$(npm prefix -g)/bin"
  workspace="$(getent passwd "$RUN_USER" | cut -d: -f6)"
  [ -n "$workspace" ] || workspace="/root"
  mkdir -p "$workspace"
  wsroot="${WORKSPACE_ROOT:-$workspace}"
  mkdir -p "$wsroot"
  local desc doc execline workdir
  if [ "$ENGINE" = opencode ]; then
    desc="Caravan node (opencode web)"
    doc="https://opencode.ai/docs/web/"
    execline="$node_bin/opencode web --port $NODE_PORT --hostname 0.0.0.0"
    workdir="$wsroot"
  else
    desc="Caravan node (CodeNomad)"
    doc="https://github.com/NeuralNomadsAI/CodeNomad"
    execline="$node_bin/codenomad --https=false --http=true --host 0.0.0.0 --http-port $NODE_PORT --dangerously-skip-auth --workspace-root $wsroot"
    workdir="$workspace"
  fi
  log "writing systemd unit (engine=$ENGINE user=$RUN_USER port=$NODE_PORT ws=$wsroot)"
  cat > /etc/systemd/system/codenomad.service <<UNIT
[Unit]
Description=$desc
Documentation=$doc
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_USER
Environment=HOME=$workspace
Environment=PATH=$node_bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
WorkingDirectory=$workdir
ExecStart=$execline
Restart=always
RestartSec=5
TimeoutStartSec=60
StandardOutput=journal
StandardError=journal
SyslogIdentifier=codenomad

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable --now codenomad
}

setup_vpn_bypass() {
  local gw iface host
  [ -n "$HUB_IP" ] || {
    host="${HEADSCALE_URL#*://}"
    host="${host%%/*}"
    HUB_IP="$(getent hosts "$host" | awk '{print $1; exit}')"
  }
  [ -n "$HUB_IP" ] || die "--bypass-vpn: cannot resolve hub IP (pass --hub-ip)"
  gw="$(ip route show default 2>/dev/null | awk '/default/{print $3; exit}')"
  iface="$(ip route show default 2>/dev/null | awk '/default/{print $5; exit}')"
  [ -n "$gw" ] && [ -n "$iface" ] || {
    warn "--bypass-vpn: no default route found; skipping"
    return 0
  }
  cat > /etc/systemd/system/codenomad-mesh-route.service <<UNIT
[Unit]
Description=Route CodeNomad hub traffic directly (bypass VPN tunnel) for the mesh
After=network-online.target
Wants=network-online.target
Before=tailscaled.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=/bin/bash -c 'for p in 100 101 200 205; do ip rule del pref \$p 2>/dev/null || true; done'
ExecStart=ip rule add pref 100 to ${HUB_IP}/32 lookup main
ExecStart=ip route replace ${HUB_IP}/32 via ${gw} dev ${iface} table main
ExecStart=ip rule add pref 101 to 100.64.0.0/10 lookup 52

[Install]
WantedBy=multi-user.target
UNIT
  systemctl daemon-reload
  systemctl enable --now codenomad-mesh-route.service

  local awg_conf="/etc/amnezia/amneziawg/awg0.conf"
  if [ -f "$awg_conf" ] && have python3 && ! grep -q 'codenomad-mesh bypass' "$awg_conf"; then
    cp "$awg_conf" "$awg_conf.bak.$(date +%Y%m%d-%H%M%S)"
    HUB_IP="$HUB_IP" GW="$gw" IFACE="$iface" AWG_CONF="$awg_conf" python3 - <<'PY'
import os
p = os.environ["AWG_CONF"]; hub = os.environ["HUB_IP"]; gw = os.environ["GW"]; ifc = os.environ["IFACE"]
s = open(p).read()
block = ("# codenomad-mesh bypass (keep mesh + hub direct while full-tunnel)\n"
         f"PostUp = bash -c 'ip rule del pref 100 2>/dev/null; ip rule add pref 100 to {hub}/32 lookup main; "
         f"ip route replace {hub}/32 via {gw} dev {ifc} table main; ip rule del pref 101 2>/dev/null; "
         "ip rule add pref 101 to 100.64.0.0/10 lookup 52; true'\n"
         "PreDown = bash -c 'ip rule del pref 100 2>/dev/null; ip rule del pref 101 2>/dev/null; true'\n")
if "[Peer]" in s:
    open(p, "w").write(s.replace("[Peer]", block + "\n[Peer]", 1))
    print("postup inserted")
else:
    print("no [Peer] section; skipped")
PY
    systemctl restart awg-quick@awg0.service 2>/dev/null || true
  fi
  log "VPN bypass: hub $HUB_IP routed via $gw ($iface)"
  systemctl restart tailscaled
  sleep 8
}

detect_resources() {
  RAM_MB="$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo)"
  CORES="$(nproc)"
  DISK_FREE_GB="$(df -Pk / | awk 'NR==2{print int($4/1024/1024)}')"
  GPU=""
  if have nvidia-smi; then GPU="$(nvidia-smi -L 2>/dev/null | head -n1)"; fi
}

# Sets REC_MODEL, REC_IMAGE, REC_VERDICT from the machine's resources.
stt_recommend() {
  detect_resources
  local cpu_img="ghcr.io/speaches-ai/speaches:0.8.3-cpu"
  local gpu_img="ghcr.io/speaches-ai/speaches:0.8.3-cuda"
  if [ -n "$GPU" ]; then
    REC_MODEL="large-v3"; REC_IMAGE="$gpu_img"; REC_VERDICT="strongly recommended (GPU)"
  elif [ "$RAM_MB" -ge 24000 ]; then
    REC_MODEL="large-v3"; REC_IMAGE="$cpu_img"; REC_VERDICT="recommended"
  elif [ "$RAM_MB" -ge 12000 ]; then
    REC_MODEL="medium"; REC_IMAGE="$cpu_img"; REC_VERDICT="recommended"
  elif [ "$RAM_MB" -ge 8000 ]; then
    REC_MODEL="small"; REC_IMAGE="$cpu_img"; REC_VERDICT="ok"
  elif [ "$RAM_MB" -ge 4000 ]; then
    REC_MODEL="base"; REC_IMAGE="$cpu_img"; REC_VERDICT="marginal (may be tight)"
  else
    REC_MODEL="tiny"; REC_IMAGE="$cpu_img"; REC_VERDICT="NOT recommended (low RAM)"
  fi
}

stt_report() {
  log "STT resources: RAM=$((RAM_MB / 1024))GB cores=$CORES disk=${DISK_FREE_GB}GB free gpu=${GPU:-none}"
  log "STT recommendation: model=$REC_MODEL image=${REC_IMAGE##*:} -> $REC_VERDICT"
}

stt_underpowered() {
  [ "$RAM_MB" -lt 4000 ] && [ -z "$GPU" ]
}

wire_codenomad() {
  local model="$1" port="$2" home cfg
  home="$(getent passwd "$RUN_USER" | cut -d: -f6)"
  [ -n "$home" ] || home="/root"
  cfg="$home/.config/codenomad/config.yaml"
  if have python3 && python3 -c 'import yaml' >/dev/null 2>&1; then
    mkdir -p "$(dirname "$cfg")"
    CFG="$cfg" MODEL="$model" PORT="$port" python3 - <<'PY'
import os

import yaml

cfg = os.environ["CFG"]
data = {}
if os.path.exists(cfg):
    with open(cfg, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
data.setdefault("server", {})["speech"] = {
    "baseUrl": f"http://127.0.0.1:{os.environ['PORT']}/v1",
    "apiKey": "local",
    "sttModel": os.environ["MODEL"],
}
with open(cfg, "w", encoding="utf-8") as fh:
    yaml.safe_dump(data, fh, sort_keys=False)
print(f"[caravan] wrote CodeNomad speech config: {cfg}")
PY
    chown "$RUN_USER":"$RUN_USER" "$cfg" 2>/dev/null || true
    systemctl restart codenomad 2>/dev/null || true
  else
    warn "python3+yaml missing — add this to CodeNomad config manually:"
    echo "  server.speech: { baseUrl: http://127.0.0.1:$port/v1, apiKey: \"local\", sttModel: $model }"
  fi
}

setup_stt() {
  stt_recommend
  stt_report
  local model image
  model="${STT_MODEL:-$REC_MODEL}"
  image="${STT_IMAGE:-$REC_IMAGE}"
  [ "$STT_CPU" = 1 ] && image="ghcr.io/speaches-ai/speaches:0.8.3-cpu"
  [ "$STT_GPU" = 1 ] && image="ghcr.io/speaches-ai/speaches:0.8.3-cuda"
  if [ -z "$STT_MODEL" ] && stt_underpowered; then
    warn "STT is NOT recommended on this machine (RAM=$((RAM_MB / 1024))GB, no GPU) — skipping."
    warn "To force it anyway: --stt-model tiny (or another model)."
    return 0
  fi
  if [ -n "$STT_MODEL" ] && [ "$model" != "$REC_MODEL" ]; then
    log "STT: using explicitly requested model=$model (recommendation was $REC_MODEL)"
  fi
  if ! have docker; then
    log "installing Docker (for STT)"
    retry bash -c 'curl -fsSL https://get.docker.com | sh'
  fi
  log "STT: starting speaches (image=${image##*:})"
  docker rm -f codenomad-stt >/dev/null 2>&1 || true
  docker run -d --name codenomad-stt --restart unless-stopped \
    -p 127.0.0.1:8000:8000 "$image" >/dev/null
  log "STT: downloading model $model (first run can take a while)"
  local i
  for i in $(seq 1 10); do
    if curl -fsS -X POST "http://127.0.0.1:8000/v1/models/$model" >/dev/null 2>&1; then
      log "STT: model ready ($model)"
      break
    fi
    [ "$i" = 10 ] && warn "STT: model download not confirmed yet (may still be in progress)"
    sleep 6
  done
  wire_codenomad "$model" 8000
  log "STT ready on http://127.0.0.1:8000"
}

remove_awg_bypass() {
  local awg="/etc/amnezia/amneziawg/awg0.conf"
  [ -f "$awg" ] || return 0
  grep -q 'codenomad-mesh bypass' "$awg" || return 0
  cp "$awg" "$awg.bak.$(date +%Y%m%d-%H%M%S)"
  sed -i '/# codenomad-mesh bypass/,+2d' "$awg"
  systemctl restart awg-quick@awg0.service 2>/dev/null || true
  log "removed VPN-bypass block from $awg"
}

uninstall() {
  log "uninstalling Caravan node services (files and packages are kept)"
  if have tailscale && tailscale status >/dev/null 2>&1; then
    tailscale down 2>/dev/null || true
    log "left the mesh (tailscale down)"
  fi
  systemctl disable --now codenomad 2>/dev/null || true
  rm -f /etc/systemd/system/codenomad.service
  systemctl disable --now codenomad-mesh-route.service 2>/dev/null || true
  rm -f /etc/systemd/system/codenomad-mesh-route.service
  systemctl daemon-reload
  remove_awg_bypass
  if [ "$PURGE" = 1 ]; then
    log "purging tailscale package + STT container"
    docker rm -f codenomad-stt >/dev/null 2>&1 || true
    apt-get purge -y tailscale >/dev/null 2>&1 || true
  fi
  log "done — workspace and user files untouched"
}

warn_early_stage() {
  printf '\n\033[1;33m%s\033[0m\n' "WARNING: Caravan is early-stage (pre-1.0) software — use at your own risk."
  cat <<'EOF'
  * Join a FRESH / throwaway machine (VM, LXC, or a spare box) —
    NOT one with critical data or production workloads.
  * Back up first. This installs Node.js + tailscale, joins a mesh, and
    writes a systemd unit for CodeNomad.
  * MIT licence: provided "as is", without warranty of any kind.
EOF
  if [ -t 0 ] && [ "${CARAVAN_YES:-0}" != "1" ]; then
    printf 'Continue? [y/N] '
    read -r ans
    case "$ans" in y | Y | yes | YES) : ;; *) die "aborted by user" ;; esac
  fi
}

main() {
  if [ "$UNINSTALL" = 1 ]; then
    uninstall
    return 0
  fi
  if [ "$STT_CHECK" = 1 ]; then
    stt_recommend
    stt_report
    return 0
  fi
  warn_early_stage
  if [ "$DRY_RUN" = 1 ]; then
    log "dry-run: engine=$ENGINE name=$NODE_NAME port=$NODE_PORT user=$RUN_USER ws=${WORKSPACE_ROOT:-<home>}"
    return 0
  fi
  ensure_base_deps
  install_node
  install_engine
  join_mesh
  write_unit
  [ "$BYPASS_VPN" = 1 ] && setup_vpn_bypass
  [ "$WITH_STT" = 1 ] && setup_stt
  local ip
  ip="$(tailscale ip -4 | head -n1)"
  log "DONE. $NODE_NAME mesh-ip=$ip port=$NODE_PORT"
  echo
  echo "Register on the hub (run there):"
  echo "  bash tools/add-node.sh --name $NODE_NAME --ip $ip --port $NODE_PORT"
  echo "or via the portal UI: https://hub.<DOMAIN>  (+ Add)"
}

main "$@"
