#!/usr/bin/env bash
# Caravan VPN — AmneziaWG management (server side lives in a container)
set -euo pipefail
DIR=/opt/amnezia
AWGDIR=$DIR/awg
CONF=$AWGDIR/awg0.conf
RT=$AWGDIR/clientsTable
IMG=amnezia-awg2
CLIENTS=$AWGDIR/clients
DNS=1.1.1.1
SERVER_NAME="${SERVER_NAME:-Caravan VPN}"
VPNURI_PY=/opt/caravan/vpnuri.py

die(){ echo "error: $*" >&2; exit 1; }
need_root(){ [ "$(id -u)" = 0 ] || die "run as root"; }
get(){ grep -E "^$1[[:space:]]*=" "$CONF" | head -1 | sed -E "s/^$1[[:space:]]*=[[:space:]]*//" || true; }
port(){ get ListenPort; }
endpoint_ip(){ curl -fsS --max-time 8 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}'; }

iface_params(){
  for k in Jc Jmin Jmax S1 S2 S3 S4 H1 H2 H3 H4 HeaderProtectionKey RekeyAfterTime RekeyTimeout RejectAfterTime KeepaliveTimeout MaxHandshakeAttempts RandomTrailers DisableCookies I1 I2 I3 I4 I5; do
    v=$(get "$k")
    if [ -n "$v" ]; then echo "$k = $v"; fi
  done
}

next_ip(){
  local used n
  used=$(grep -c '^AllowedIPs = 10\.8\.1\.' "$CONF" 2>/dev/null || true)
  n=$((used+1))
  echo "10.8.1.$n"
}

apply(){ docker restart "$IMG" >/dev/null; sleep 2; }

rt_add(){ # name pub ip
  python3 - "$RT" "$1" "$2" "$3" <<'PY'
import json, sys, datetime
rt, name, pub, ip = sys.argv[1:5]
try: arr = json.load(open(rt))
except Exception: arr = []
arr = [c for c in arr if c.get("userData", {}).get("clientName") != name]
arr.append({"clientId": pub,
            "userData": {"allowedIps": ip + "/32", "allowed_ips": ip + "/32",
                         "clientName": name,
                         "creationDate": datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y")}})
json.dump(arr, open(rt, "w"), indent=4)
PY
}

rt_del(){ # name
  python3 - "$RT" "$1" <<'PY'
import json, sys
rt, name = sys.argv[1:3]
try: arr = json.load(open(rt))
except Exception: arr = []
arr = [c for c in arr if c.get("userData", {}).get("clientName") != name]
json.dump(arr, open(rt, "w"), indent=4)
PY
}

cmd_add(){
  local name="$1"
  grep -qF "# client: $name" "$CONF" && die "client '$name' already exists"
  local ip cpriv cpub psk spub
  ip=$(next_ip)
  cpriv=$(docker exec "$IMG" awg genkey)
  cpub=$(printf '%s\n' "$cpriv" | docker exec -i "$IMG" awg pubkey)
  psk=$(tr -d '\n' < "$AWGDIR/wireguard_psk.key")
  spub=$(tr -d '\n' < "$AWGDIR/wireguard_server_public_key.key")
  {
    echo ""; echo "[Peer]"; echo "# client: $name"
    echo "PublicKey = $cpub"; echo "PresharedKey = $psk"; echo "AllowedIPs = $ip/32"
  } >> "$CONF"
  apply
  mkdir -p "$CLIENTS"
  local ep; ep=$(endpoint_ip)
  {
    echo "[Interface]"; echo "PrivateKey = $cpriv"; echo "Address = $ip/32"; echo "DNS = $DNS"
    iface_params
    echo ""; echo "[Peer]"; echo "PublicKey = $spub"; echo "PresharedKey = $psk"
    echo "AllowedIPs = 0.0.0.0/0, ::/0"; echo "Endpoint = $ep:$(port)"; echo "PersistentKeepalive = 25"
  } > "$CLIENTS/$name.conf"
  chmod 600 "$CLIENTS/$name.conf"
  rt_add "$name" "$cpub" "$ip"
  echo "added '$name' -> $ip ; config: $CLIENTS/$name.conf"
  if [ -f "$VPNURI_PY" ]; then cmd_link "$name" >/dev/null 2>&1 || true; fi
}

cmd_del(){
  local name="$1"
  grep -qF "# client: $name" "$CONF" || die "no client '$name'"
  awk -v n="$name" '
    /^\[Peer\]/ { if (buf!="" && !drop) printf "%s", buf; buf=$0"\n"; drop=0; next }
    { if (buf=="") { print; next } buf=buf $0"\n"; if (index($0, "# client: " n) > 0) drop=1 }
    END { if (buf!="" && !drop) printf "%s", buf }
  ' "$CONF" > "$CONF.tmp" && mv "$CONF.tmp" "$CONF"
  rm -f "$CLIENTS/$name.conf" "$CLIENTS/$name.vpnuri" "$CLIENTS/$name.vpnuri.png"
  rt_del "$name"
  apply
  echo "removed '$name'"
}

cmd_list(){
  python3 - "$RT" "$CONF" <<'PY'
import json, sys, re
rt, conf = sys.argv[1:3]
try: arr = json.load(open(rt))
except Exception: arr = []
if arr:
    for c in arr:
        ud = c.get("userData", {})
        print("-", ud.get("clientName", "?"), "|", ud.get("allowedIps") or ud.get("allowed_ips") or "?")
else:
    for m in re.findall(r"^# client: (.+)$", open(conf).read(), re.M):
        print("-", m)
PY
}

cmd_report(){
  docker exec "$IMG" awg show 2>/dev/null > /tmp/.awgshow.$$ || true
  python3 - "$RT" "/tmp/.awgshow.$$" <<'PY'
import json, sys, re
rt, awgf = sys.argv[1:3]
live, cur = {}, None
for line in open(awgf):
    m = re.match(r"^peer:\s*(\S+)", line)
    if m:
        cur = m.group(1); live[cur] = {}
    elif cur:
        mm = re.search(r"latest handshake:\s*(.+)", line)
        if mm: live[cur]["hs"] = mm.group(1).strip()
        me = re.search(r"endpoint:\s*(\S+)", line)
        if me: live[cur]["ep"] = me.group(1).strip()
try: arr = json.load(open(rt))
except Exception: arr = []
print(f'{"name":34} {"ip":13} {"last handshake":26} {"endpoint":22}')
print("-" * 100)
for c in arr:
    ud = c.get("userData", {}); pub = c.get("clientId", "")
    ip = ud.get("allowedIps") or ud.get("allowed_ips") or "?"
    L = live.get(pub, {})
    hs = L.get("hs", "— (нет handshake)")
    ep = L.get("ep", "")
    print(f"{ud.get('clientName','?')[:34]:34} {ip:13} {hs:26} {ep:22}")
active = sum(1 for c in arr if live.get(c.get("clientId", ""), {}).get("hs"))
print(f"\nвсего: {len(arr)}   с активным handshake: {active}")
PY
  rm -f /tmp/.awgshow.$$
}

cmd_sync(){
  [ -f "$VPNURI_PY" ] || true
  python3 - "$CONF" "$CLIENTS" "$RT" <<'PY'
import json, os, re, subprocess, sys, glob, datetime
conf, clients, rt = sys.argv[1:4]
# map client pubkey -> allowed ip from the conf peers (comments give names)
text = open(conf).read()
blocks = re.split(r"(?m)^\[Peer\]\s*$", text)[1:]
entries = []
for b in blocks:
    m = re.search(r"#\s*client:\s*(.+)", b)
    name = m.group(1).strip() if m else "Client"
    pk = re.search(r"PublicKey\s*=\s*(\S+)", b)
    ip = re.search(r"AllowedIPs\s*=\s*(\S+)", b)
    if pk and ip:
        entries.append((name, pk.group(1), ip.group(1).split("/")[0]))
arr = [{"clientId": pk, "userData": {"allowedIps": ip + "/32", "allowed_ips": ip + "/32", "clientName": name}}
       for (name, pk, ip) in entries]
json.dump(arr, open(rt, "w"), indent=4)
print(f"clientsTable synced: {len(arr)} clients")
PY
}

cmd_link(){
  local name="$1"; local cf="$CLIENTS/$name.conf"
  [ -f "$cf" ] || die "no client '$name'"
  [ -f "$VPNURI_PY" ] || die "missing $VPNURI_PY"
  python3 "$VPNURI_PY" "$cf" "$SERVER_NAME" > "$CLIENTS/$name.vpnuri"
  cat "$CLIENTS/$name.vpnuri"; echo
}

cmd_qrlink(){
  local name="$1"; local uf="$CLIENTS/$name.vpnuri"
  [ -f "$uf" ] || cmd_link "$name" >/dev/null
  if command -v qrencode >/dev/null 2>&1; then qrencode -t ansiutf8 < "$uf"; else cat "$uf"; fi
}

cmd_show(){ docker exec "$IMG" awg show 2>/dev/null | sed -E 's/(private key:).*/\1 (hidden)/'; }
cmd_conf(){ cat "$CLIENTS/$1.conf"; }

usage(){ echo "usage: vpn.sh {add NAME|del NAME|list|report|sync|conf NAME|link NAME|qrlink NAME|show}"; }

need_root
[ -f "$CONF" ] || die "server not installed ($CONF missing)"
case "${1:-}" in
  add) cmd_add "${2:?name}";;
  del) cmd_del "${2:?name}";;
  list) cmd_list;;
  report) cmd_report;;
  sync) cmd_sync;;
  conf) cmd_conf "${2:?name}";;
  link) cmd_link "${2:?name}";;
  qrlink) cmd_qrlink "${2:?name}";;
  show) cmd_show;;
  *) usage;;
esac
