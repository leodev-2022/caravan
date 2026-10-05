# Operations

Everything runs via Docker Compose on the **hub** (`/opt/caravan`). Secrets come
from `/opt/caravan/.env` (root-only).

> ⚠️ **Pre-1.0 — use at your own risk.** Test on a **fresh / throwaway machine**
> (VM, LXC, or a spare VPS), **not** on a server with critical data or production
> workloads. Back up first (see *Backup / restore* below).

## Bring up / update
```bash
sudo caravan update     # pull latest images + re-apply (keeps secrets/config/data)
sudo caravan doctor     # diagnose: containers, caddy validate, endpoints
```

## Add a node (machine)

Two ways: run **one command** on the machine (works everywhere), or let the hub
**provision it over SSH** from the dashboard.

### Option A — one command (recommended; no SSH needed)
1. On the hub, get a ready-to-paste invite (mints a short-lived token):
   ```bash
   sudo caravan token --expiry 1h
   ```
2. Paste the **one command** it prints on the new machine — no flags to learn:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/leodev-2022/caravan/main/tools/node-join.sh \
     | sudo bash -s -- --hub https://mesh.example.com --token <key>
   ```
   - It uses the machine's hostname as the node name (`--name` to override).
   - `--user` / `--workspace-root /` — account + browsable root.
   - `--engine opencode` — run the **opencode web** UI instead of CodeNomad (port 4096).
   - `--bypass-vpn` — for full-tunnel nodes (see below).
3. Register it (note the printed mesh IP):
   ```bash
   sudo caravan add-node --name <name> --ip <mesh-ip> --port 9898
   ```
   …or use the dashboard **+ Add**. New mesh nodes are registered **automatically**
   (a hub timer watches headscale), so the one-command join needs no manual step.
   Deleting a node (dashboard 🗑 or `caravan remove-node --name <name>`) also drops
   it from the mesh — otherwise the sync would re-add it.

### Option B — provision over SSH (dashboard “magic”)
Dashboard **Invite → Provision by SSH** (or `sudo bash tools/provision.sh --host IP
--user USER ...`). The hub logs in, onboards a machine **reachable from the hub**
(public IP / same network), and **registers it automatically**. NAT'd machines must
run the one-command join themselves.

The hub authenticates with either:
- **the hub's SSH key (recommended)** — its public half is shown in the **Invite**
  dialog; add it to the target's `authorized_keys` and leave the password empty; or
- **a password** (`sshpass`) — only where password SSH is enabled.

> **Proxmox LXC/VM gotcha.** A fresh Debian/Ubuntu container template has **no root
> password**, and sshd defaults to `PermitRootLogin prohibit-password`, so password
> login always fails (“Permission denied”) no matter what you type. Fix it either way:
> ```bash
> # 1) run the Option-A command in the container console (no SSH at all):
> pct enter <VMID>     # then paste the join command
>
> # 2) add the hub public key, then Provision by SSH with a blank password:
> pct enter <VMID>
> mkdir -p /root/.ssh
> echo "<HUB PUBLIC KEY>" >> /root/.ssh/authorized_keys
> chmod 700 /root/.ssh && chmod 600 /root/.ssh/authorized_keys
> ```
> In the PVE GUI, paste the key straight into the creation wizard's **“SSH public
> key”** field (or `pct create ... --ssh-public-keys FILE`).

> **Proxmox LXC needs TUN (otherwise the node can't join the mesh).** An
> unprivileged container has no `/dev/net/tun`, so `tailscaled` fails and the node
> never comes online. `node-join.sh` detects this up front and stops with guidance.
> Fix it on the **Proxmox host**:
> ```bash
> pct set <VMID> -features nesting=1
> # if that is not enough, add to /etc/pve/lxc/<VMID>.conf:
> #   lxc.cgroup2.devices.allow: c 10:200 rwm
> #   lxc.mount.entry: /dev/net/tun dev/net/tun none bind,create=file
> pct reboot <VMID>          # then verify inside: ls -l /dev/net/tun
> ```
> A **VM** works out of the box — if in doubt, use a VM for nodes.

### Windows node
On a Windows machine, run PowerShell **as Administrator** (registers Scheduled
Tasks instead of systemd; Node.js and Tailscale are downloaded directly, so
`winget` is not required):
```powershell
.\tools\node-join.ps1 -Hub https://mesh.example.com -Token <key> -Name pc1
```
- It installs Node.js + the engine + Tailscale, joins the mesh, and registers
  the engine, the metrics agent and a 5-minute watchdog as Scheduled Tasks (SYSTEM,
highest, **no execution-time limit**, restart-on-failure). The watchdog re-starts a
service whose port stops listening, so the node self-heals — Windows' default 72 h
task limit would otherwise silently kill it after three days.
- `-Engine opencode` — run the **opencode web** UI instead of CodeNomad.
- `-WorkspaceRoot C:\dev` — the browsable root (default: the user's profile).
- `-Yes` — skip the confirmation prompt (unattended/SSH runs); `-DryRun` prints the plan.
- Uninstall: `schtasks /Delete /TN CaravanNode /F ; schtasks /Delete /TN CaravanMetrics /F`.
- The metrics agent (`tools/metrics.ps1`) reads uptime/CPU/RAM via fast Win32 APIs
  (`GlobalMemoryStatusEx`/`GetSystemTimes`; WMI/CIM can take seconds per query) and
  binds to the mesh IP only.

### STT (voice → text), optional per node
STT is **capability-aware**: on a machine with the resources for it (≥12 GB RAM
or a GPU) `node-join.sh` **offers** voice-to-text interactively after the join
(interactive runs only — `CARAVAN_YES=1`/no TTY just prints a hint). Ask for the
recommendation explicitly:
```bash
sudo bash node-join.sh --stt-check      # prints RAM/GPU + the recommended model
```
Then install the recommended model, or choose explicitly:
```bash
sudo bash node-join.sh ... --stt              # recommended model
sudo bash node-join.sh ... --stt-model small  # explicit choice
```
`node-join.sh` starts `speaches` on `127.0.0.1:8000`, downloads the model, and
writes `server.speech` into the node's CodeNomad config. On weak machines
(`<4 GB`, no GPU) STT is **not** installed unless you pass `--stt-model`.

## Backup / restore
```bash
sudo caravan backup                           # -> /opt/backups/caravan-<ts>.tar.gz
BACKUP_PASSPHRASE=secret sudo caravan backup  # encrypted (.enc)
sudo caravan restore --file /opt/backups/caravan-<ts>.tar.gz
```
Contains configs + the headscale SQLite DB + Caddy data. `restore` stops the
stack, restores configs and volumes, then starts it again.

## Alerts
`portal` sends Telegram on down/recovery transitions. Configure in `/opt/caravan/.env`:
`TELEGRAM_TOKEN`, `TELEGRAM_CHAT` (see `conf/.env.example`). `mesh.example.com`
is intentionally NOT behind SSO, so node joins keep working.

## Troubleshooting
- **Every node shows offline** → the hub itself may be off the mesh. `install.sh`
  joins the hub as `caravan-hub`; verify with `tailscale status` on the hub (it
  should list its own node). If it was skipped, re-run the installer or join by hand:
  ```bash
  tailscale up --login-server https://mesh.<DOMAIN> --authkey <key> --accept-dns=false
  ```
  Then `curl http://<mesh-ip>:9898/` from the hub should answer.
- **A single node shows offline** → check `tailscale status` and confirm the
  backend answers `curl http://<mesh-ip>:9898/` from the hub.
- **Service won't start on a node** → `203/EXEC` usually means wrong npm-global
  path; node-join.sh now auto-detects it, or fix the unit's `ExecStart`/`PATH`.
- **Dashboard provisioning fails with «Permission denied» on a container** → the
  target has no root password / `PermitRootLogin prohibit-password`. Add the hub's
  public key (Invite dialog) to `authorized_keys`, or run the one-command join in
  the console. See *Option B* above.
- **Lost the TOTP** → on the hub, `python3 scripts/register-totp.py` re-runs
  registration via the Authelia API and prints a fresh `otpauth://` (the installer
  does this automatically and prints it once).

### Node unreachable over the mesh (TCP timeout) — VPN full-tunnel
Symptom: `tailscale ping` to the node works, but TCP to its port (22/9898/…) times
out, and the hub shows the node's direct endpoint as the **VPN server IP** instead
of the site's real IP. Cause: the node routes **all** outbound traffic through a
VPN (Amnezia, `AllowedIPs = 0.0.0.0/0`) that is needed for other purposes (e.g.
Telegram). Amnezia re-adds its `ip rule`s on every tunnel (re)start — and a
watchdog may restart the tunnel after e.g. a Proxmox VM backup — so a one-off
route fix gets overridden.

**Recommended fix — a script that computes the bypass pref and hook it into
`awg0.conf` (`PostUp`) + a boot unit.** The VPN's rule block **drifts down between
builds** (AmneziaWG seen at 98/99, 88/89, 78/79, 68/69, 48/49, 5208/5209), so a
**fixed** pref always eventually loses (68, 80/81, 90/91, 100/101 all silently lose;
the trap: `tailscale ping`/`online` still work, only TCP/ICMP dies). Instead place
ours *just below* whatever the VPN installed, and clean old rules **by destination**:
```bash
# /usr/local/sbin/caravan-mesh-route.sh
HUB=<HUB_IP>
while ip rule show | grep -q "to 100.64.0.0/10 lookup 52"; do ip rule del to 100.64.0.0/10 lookup 52 2>/dev/null || break; done
while ip rule show | grep -q "to $HUB lookup main"; do ip rule del to $HUB lookup main 2>/dev/null || break; done
LOW=$(ip rule show | awk -F: '/suppress_prefixlength|51820|0xca6c/{gsub(/ /,"",$1);print $1}' | sort -n | head -1)
P=40; [ -n "$LOW" ] && [ "$LOW" -gt 4 ] && P=$((LOW-2))
GW=$(ip route show default | awk '{print $3; exit}'); IF=$(ip route show default | awk '{print $5; exit}')
ip rule add pref "$P" to "$HUB/32" lookup main
ip route replace "$HUB/32" via "$GW" dev "$IF" table main
ip rule add pref "$((P+1))" to 100.64.0.0/10 lookup 52
```
Run it from a boot unit (`codenomad-mesh-route.service`, `Before=tailscaled`) **and**
from the VPN conf's `[Interface]` `PostUp` (so it re-applies on every tunnel
restart — a VPN watchdog restarting the tunnel won't break the mesh). Verify
`ip route get 100.64.0.1` shows `dev tailscale0` (not `awg0`).

The same pattern is used on `node2` to keep the **work LAN** direct
(`PostUp = ip route add 192.168.0.0/24 dev <LAN-IFACE>`).

Alternative/belt-and-suspenders: `--bypass-vpn` in `node-join.sh` writes a
`codenomad-mesh-route.service` oneshot (pref 50/51) for boot-time application.
For full-tunnel nodes, prefer the `PostUp` hook above (survives tunnel restarts).

### Fast VPN-box migration (a blocked IP)
When a VPN box's IP gets blocked (RU side: the host may still answer ICMP/TCP but
the tunnel dies for everyone), replace the box **keeping the server identity**, so
clients only need to point at the new IP — no re-keying:

1. Stand up a fresh cheap host (same provider/tariff is fine — the block is on the
   old IP; a different provider/range is even better).
2. From a machine that can SSH (key auth) to both boxes:
   ```bash
   bash tools/vpn/vpn-migrate.sh --old root@<old> --new root@<new>
   ```
   It reads the old box's `awg0.conf` + keys + listen port, installs the stack on the
   new host with the **same port**, overlays the old identity + all peers, and
   verifies the server public key and peer count match. `--dry-run` pulls and checks
   the old identity without touching the new box.
3. Point every client at the **new IP** (keys/params unchanged): in the Amnezia app
   re-add the server with the new IP; for raw configs change `Endpoint`. Power the
   old box off.

**Why not a domain + DNS flip:** for a small circle of friends/family it is one more
moving part with little gain — a clone + IP change is enough (roadmap 6.38).
