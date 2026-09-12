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
   …or use the dashboard **+ Add**. `caravan remove-node --name <name>` removes it.

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

### Windows node
On a Windows machine, run PowerShell **as Administrator** (registers Scheduled
Tasks instead of systemd; Node.js and Tailscale are downloaded directly, so
`winget` is not required):
```powershell
.\tools\node-join.ps1 -Hub https://mesh.example.com -Token <key> -Name pc1
```
- It installs Node.js + the engine + Tailscale, joins the mesh, and registers
  the engine and the metrics agent as Scheduled Tasks (ONSTART, SYSTEM, highest).
- `-Engine opencode` — run the **opencode web** UI instead of CodeNomad.
- `-WorkspaceRoot C:\dev` — the browsable root (default: the user's profile).
- `-Yes` — skip the confirmation prompt (unattended/SSH runs); `-DryRun` prints the plan.
- Uninstall: `schtasks /Delete /TN CaravanNode /F ; schtasks /Delete /TN CaravanMetrics /F`.
- The metrics agent (`tools/metrics.ps1`) reads uptime/CPU/RAM via fast Win32 APIs
  (`GlobalMemoryStatusEx`/`GetSystemTimes`; WMI/CIM can take seconds per query) and
  binds to the mesh IP only.

### STT (voice → text), optional per node
STT is **capability-aware**. On the node, ask for a recommendation first:
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
- **Node shows offline** → check `tailscale status` on the hub; confirm the
  backend answers `curl http://<mesh-ip>:9898/`.
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

**Recommended fix — put the bypass in `awg0.conf` (`PostUp`/`PreDown`)**, so it is
(re)applied on every tunnel up, at a rule priority **above** Amnezia's (Amnezia
may use 198/199 or 5208/5209 — use 100/101):
```ini
# /etc/amnezia/amneziawg/awg0.conf  [Interface]
PostUp   = bash -c 'ip rule del pref 100 2>/dev/null; ip rule add pref 100 to <HUB_IP>/32 lookup main; ip route replace <HUB_IP>/32 via <GATEWAY> dev <IFACE> table main; ip rule del pref 101 2>/dev/null; ip rule add pref 101 to 100.64.0.0/10 lookup 52; true'
PreDown  = bash -c 'ip rule del pref 100 2>/dev/null; ip rule del pref 101 2>/dev/null; true'
```
Then `systemctl restart awg-quick@awg0.service`. Verify `ip route get 100.64.0.1`
shows `dev tailscale0` (not `awg0`).

The same pattern is used on `node2` to keep the **work LAN** direct
(`PostUp = ip route add 192.168.0.0/24 dev <LAN-IFACE>`).

Alternative/belt-and-suspenders: `--bypass-vpn` in `node-join.sh` writes a
`codenomad-mesh-route.service` oneshot (pref 100/101) for boot-time application.
For full-tunnel nodes, prefer the `PostUp` hook above (survives tunnel restarts).
