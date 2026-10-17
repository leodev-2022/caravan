#!/usr/bin/env bash
# Caravan VPN box installer (AmneziaWG, fresh image, host-persisted config)
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
log(){ echo "[vpn] $*"; }

DIR=/opt/amnezia
AWGDIR=$DIR/awg
NET=amnezia-dns-net
IMG=amnezia-awg2
BASE=amneziavpn/amneziawg-go:latest
SUBNET=10.8.1.0/24
I1='<r 2><b 0x858000010001000000000669636c6f756403636f6d0000010001c00c000100010000105a00044d583737>'

log "docker"
if ! command -v docker >/dev/null 2>&1; then
  apt-get install -y --no-install-recommends docker.io
fi
systemctl enable --now docker >/dev/null 2>&1 || true

log "dirs + random port"
install -d -m 700 "$AWGDIR"
[ -f "$AWGDIR/port" ] || shuf -i 20000-60000 -n1 > "$AWGDIR/port"
PORT=$(tr -d '[:space:]' < "$AWGDIR/port")
[ -f "$AWGDIR/hpk" ] || openssl rand -base64 32 | tr -d '\n' > "$AWGDIR/hpk"
HPK=$(tr -d '[:space:]' < "$AWGDIR/hpk")
log "port=$PORT"

log "network $NET"
if ! docker network inspect "$NET" >/dev/null 2>&1; then
  docker network create -d bridge --subnet 172.29.172.0/24 \
    --opt com.docker.network.bridge.name=amn0 "$NET" >/dev/null
fi

log "pull fresh base + build image $IMG"
docker pull "$BASE" >/dev/null
install -d -m 755 "$DIR/$IMG"
cat > "$DIR/$IMG/Dockerfile" <<'EOF'
FROM amneziavpn/amneziawg-go:latest
RUN apk add --no-cache bash curl dumb-init
RUN mkdir -p /opt/amnezia
ENTRYPOINT [ "dumb-init", "/opt/amnezia/start.sh" ]
CMD [ "" ]
EOF
docker build -q -t "$IMG" "$DIR/$IMG" >/dev/null

log "server keys"
docker run --rm --entrypoint sh -v "$AWGDIR:/awg" "$IMG" -c '
  set -e; umask 077; cd /awg
  [ -s wireguard_server_private_key.key ] || awg genkey > wireguard_server_private_key.key
  [ -s wireguard_server_public_key.key ] || awg pubkey < wireguard_server_private_key.key > wireguard_server_public_key.key
  [ -s wireguard_psk.key ] || awg genpsk > wireguard_psk.key
  chmod 600 wireguard_server_private_key.key
'
PRIV=$(tr -d '[:space:]' < "$AWGDIR/wireguard_server_private_key.key")

hb=$(( 1950000000 + (RANDOM*32768+RANDOM) % 10000000 ))
h_range(){ local a=$(( hb + $1 )); local s=$(( 500000 + (RANDOM*32768+RANDOM) % 8000000 )); echo "$a-$((a+s))"; }
S1=$(( 10 + RANDOM % 131 )); S2=$(( 10 + RANDOM % 131 )); S3=12; S4=12
H1=$(h_range 0); H2=$(h_range 20000000); H3=$(h_range 40000000); H4=$(h_range 60000000)
log "obfuscation: S=($S1,$S2,$S3,$S4) H=($H1|$H2|$H3|$H4)"

log "awg0.conf"
cat > "$AWGDIR/awg0.conf" <<EOF
[Interface]
PrivateKey = $PRIV
Address = $SUBNET
ListenPort = $PORT
Jc = 6
Jmin = 10
Jmax = 50
S1 = $S1
S2 = $S2
S3 = $S3
S4 = $S4
H1 = $H1
H2 = $H2
H3 = $H3
H4 = $H4
HeaderProtectionKey = $HPK
RekeyAfterTime = 100-120
RekeyTimeout = 3-7
RejectAfterTime = 150-180
KeepaliveTimeout = 5-15
MaxHandshakeAttempts = 15-20
RandomTrailers = on
DisableCookies = on
# I1 = $I1
EOF
chmod 600 "$AWGDIR/awg0.conf"
[ -f "$AWGDIR/clientsTable" ] || echo '[]' > "$AWGDIR/clientsTable"

log "start.sh (host-side, persistent)"
cat > "$DIR/start.sh" <<'EOF'
#!/bin/bash
echo "Container startup"
[ -f /opt/amnezia/awg/awg0.conf ] && {
  awg-quick down /opt/amnezia/awg/awg0.conf 2>/dev/null || true
  awg-quick up /opt/amnezia/awg/awg0.conf
}
iptables -A INPUT -i awg0 -j ACCEPT 2>/dev/null || true
iptables -A FORWARD -i awg0 -j ACCEPT 2>/dev/null || true
iptables -A OUTPUT -o awg0 -j ACCEPT 2>/dev/null || true
iptables -A FORWARD -i awg0 -o eth0 -s 10.8.1.0/24 -j ACCEPT 2>/dev/null || true
iptables -A FORWARD -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || true
iptables -t nat -A POSTROUTING -s 10.8.1.0/24 -o eth0 -j MASQUERADE 2>/dev/null || true
tail -f /dev/null
EOF
chmod 755 "$DIR/start.sh"

log "run container"
docker rm -f "$IMG" >/dev/null 2>&1 || true
docker run -d --name "$IMG" \
  --restart always \
  --privileged \
  --cap-add NET_ADMIN --cap-add SYS_MODULE \
  --sysctl net.ipv4.conf.all.src_valid_mark=1 \
  -v /lib/modules:/lib/modules:ro \
  -v "$DIR:$DIR" \
  -p "${PORT}:${PORT}/udp" \
  --network "$NET" \
  "$IMG" >/dev/null

sysctl -w net.ipv4.ip_forward=1 >/dev/null
grep -q '^net.ipv4.ip_forward=1' /etc/sysctl.conf || echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf

sleep 2
log "== status =="
docker ps --format '{{.Names}} | {{.Image}} | {{.Status}} | {{.Ports}}'
echo "--- awg show ---"
docker exec "$IMG" awg show 2>/dev/null | sed -E 's/(private key:).*/\1 (hidden)/' || echo "(awg not up yet)"
echo "--- listening ---"
ss -ulpnH | awk '{print $1,$5}' | sort -u
echo "--- host base digest ---"
docker inspect --format '{{index .RepoDigests 0}}' "$BASE" 2>/dev/null || true
log 'done'
