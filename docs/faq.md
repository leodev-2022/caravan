# FAQ

**What is Caravan?**
A self-hosted control panel ("cockpit") that gives you one SSO-protected window
to run AI coding agents (OpenCode / CodeNomad) across **all** your machines.

**Do I need to be a sysadmin?**
No. One command installs the hub; one command joins each machine. Sensible
security is on by default.

**What server do I need?**
Any cheap Ubuntu/Debian VPS. It runs comfortably on 1 vCPU / 1–2 GB. You need a
public IP for automatic HTTPS — or use `--sslip` / `--self-signed`.

**Do I need a domain?**
No. `--sslip` derives a working hostname from your IP (via sslip.io). `--domain`
is best for production; `--self-signed` is for offline/testing.

**Do my machines need public IPs or open ports?**
No. Nodes dial **out** to the hub over a WireGuard mesh — nothing to expose.

**Is my code sent anywhere?**
No. Everything runs on your own infrastructure. Caravan has no telemetry.

**How many machines can I add?**
As many as you like; each is a "node". Register them in the dashboard or with
`caravan add-node`.

**Does it work behind a full-tunnel VPN (e.g. Amnezia)?**
Yes — pass `--bypass-vpn` to `node-join.sh` so hub/mesh traffic bypasses the tunnel.

**Voice / speech-to-text?**
Optional, per node. `node-join.sh --stt-check` prints a recommendation for your
hardware; `--stt` installs the recommended model; `--stt-model` lets you choose
explicitly. On weak machines it is **not** installed unless you ask.

**Is it free?**
Yes — MIT. A managed cloud and team features (SSO/OIDC, RBAC, audit) are planned
(open-core).

**Is Caravan affiliated with OpenCode or CodeNomad?**
No. Caravan consumes them as dependencies and credits them. See the disclaimer in
the README.

**How do I update?**
`sudo caravan update` pulls the latest images and re-applies (keeps your secrets,
config, and data).

**How do I back up / restore?**
`sudo caravan backup` and `sudo caravan restore --file <archive>`.
