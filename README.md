# Caravan

**Your AI coding cockpit — on your own servers, from anywhere.**

[Website](https://leodev-2022.github.io/caravan/) · [Docs](docs/) · [Security](SECURITY.md) · MIT

> ⚠️ **Early-stage software — use at your own risk.** Caravan is pre-1.0.
> **Test it on a fresh, throwaway machine** (a VM, an LXC container, or a spare
> VPS) — **not** on a server with critical data or production workloads. Back up
> anything important first. The installer changes the system (installs Docker,
> uses ports 80/443, runs containers). Provided "as is", without warranty (MIT).

Caravan turns a cheap VPS into a private dashboard for your AI coding agents
([OpenCode](https://opencode.ai) / [CodeNomad](https://github.com/NeuralNomadsAI/CodeNomad))
running across **all** your machines. One command to install, SSO + TOTP at the
door, and a self-hosted mesh so your machines never need inbound ports.

> OpenCode gives you the engine. Caravan gives you the cockpit across all your machines.

## Why Caravan
- **Multi-machine by default** — one window to every dev box: home, work, VPS.
- **Private & cheap** — runs on a ~$3 VPS (1 vCPU / 1–2 GB). Your code never
  leaves your infrastructure.
- **Secure by default** — default-deny firewall, SSO + TOTP, mesh-only nodes,
  root-only secrets. Hardening is built in, not a checklist you must pass.
- **One command, idempotent** — `install.sh` for the hub, `node-join.sh` for machines.
- **Open source** — MIT.

## Screenshots
![Caravan dashboard](docs/img/dashboard.png)

*Live dashboard — per-machine status, locations, tags, one-click open, behind SSO
(dark & light themes).*

![Add an environment](docs/img/add-node.png)

*Register a machine in seconds — onboard it with `node-join.sh`, then add it here.*

## How it works
```
Browser (anywhere)
   │ https://<env>.<DOMAIN>        (public :443)
   ▼
HUB (a cheap always-on VPS)
   ├─ caddy      TLS/ACME + forward_auth + reverse proxy
   ├─ authelia   SSO + TOTP
   ├─ headscale  self-hosted mesh coordinator (SQLite)
   └─ portal     status dashboard + Telegram alerts
   │  each node dials OUT — no inbound ports on your machines
   ▼
Nodes: CodeNomad on :9898 (mesh-only, HTTP)   [+ optional local STT]
```

## Quick start
### 1. Hub (one command)
```bash
curl -fsSL https://raw.githubusercontent.com/leodev-2022/caravan/main/install.sh | sudo bash
```
No domain needed — on a VPS with a public IP it auto-uses `<your-ip>.sslip.io` for
trusted HTTPS. Behind NAT (a home/lab box) it auto-falls back to a self-signed
cert — the browser will warn (pass `--domain example.com` for trusted TLS). It
prints the dashboard URL and a one-time admin password.

### 2. Connect a machine (node)

**Option A — one command (works everywhere, no SSH needed).**
In the dashboard click **Invite → Generate** and copy the one line; run it on the
new machine as root:
```bash
curl -fsSL https://raw.githubusercontent.com/leodev-2022/caravan/main/tools/node-join.sh | sudo bash -s -- --hub https://mesh.example.com --token <key>
```
(`sudo caravan token --expiry 1h` prints the same command from the CLI.)

**Windows node** (Windows 10/11) — run PowerShell **as Administrator**:
```powershell
curl.exe -fsSL https://raw.githubusercontent.com/leodev-2022/caravan/main/tools/node-join.ps1 -o node-join.ps1
.\node-join.ps1 -Hub https://mesh.example.com -Token <key> -Name pc1
```
It installs Node.js + the engine + Tailscale (direct downloads — no winget) and
registers both as Scheduled Tasks. Use the same `<key>` from `caravan token`.

**Option B — “magic”: provision over SSH from the dashboard.**
Open **Invite** and use the **Provision by SSH** form (host, ssh user, node name).
The hub logs in and sets everything up for you.
- A typical VPS with a root password: just enter the password.
- **Fresh Proxmox LXC/VM:** root has *no password* and sshd uses
  `PermitRootLogin prohibit-password`, so password login always fails. Add the
  hub's **public key** (shown in the same **Invite** dialog) to the machine and
  leave the password blank. Paste it into the PVE creation wizard's
  **“SSH public key”** field, or afterwards:
  ```
  pct enter <VMID>
  mkdir -p /root/.ssh
  echo "<HUB PUBLIC KEY>" >> /root/.ssh/authorized_keys
  chmod 700 /root/.ssh && chmod 600 /root/.ssh/authorized_keys
  ```
  Then click **Provision by SSH** with the password field empty.

### 3. Register the node
**Provision by SSH** registers the node for you. For the one-command join, register
the mesh IP it prints at the end (or click **+ Add** in the dashboard):
```bash
sudo caravan add-node --name web1 --ip <mesh-ip> --port 9898
```

## CLI
```
caravan install [--domain NAME | --sslip | --self-signed]   install the hub
caravan update                                              pull images + re-apply
caravan doctor                                              diagnose the hub
caravan nodes list                                          list mesh nodes
caravan token [--user NAME|ID] [--expiry 1h] [--reusable]   issue a join token
caravan add-node --name N --ip IP [--port 9898] [...]       register a node
caravan remove-node --name N                                unregister a node
caravan backup [--out DIR]      caravan restore --file ARCHIVE
caravan uninstall [--purge]
```

## Requirements
- **Hub:** any Ubuntu/Debian VPS; a public IP for ACME — or use `--sslip` /
  `--self-signed`. Runs comfortably on 1 vCPU / 2 GB.
- **Nodes:** Ubuntu/Debian, or Windows 10/11 (PowerShell). No public IP and no
  inbound ports required. For **dashboard provisioning** the hub must reach the
  machine over SSH: a root password, or (for Proxmox LXC/VM, where root has no
  password by default) the hub's public key in `authorized_keys`.

## Documentation
- [Architecture](docs/architecture.md)
- [Operations](docs/operations.md)
- [Security](docs/security.md)
- [FAQ](docs/faq.md)
- [Contributing](docs/contributing.md)

## Credits & disclaimer
Caravan is an independent project. It **consumes** these excellent MIT-licensed
projects as dependencies and does not fork or redistribute their source:
- **[OpenCode](https://opencode.ai)** (anomalyco) — the AI coding engine.
- **[CodeNomad](https://github.com/NeuralNomadsAI/CodeNomad)** (NeuralNomadsAI) — the cockpit UI.

Not affiliated with, or endorsed by, NeuralNomadsAI or the OpenCode team.
All trademarks belong to their respective owners.

## License
MIT
