# Architecture

## Goal
One window to switch between several CodeNomad environments, from anywhere,
behind a single protected entry point.

## Topology
```
Browser → https://<env>.example.com (public 443)
                     │
        ┌────────────▼────────────┐
        │  HUB — always-on box     │
        │  caddy  (TLS/ACME, proxy, forward_auth)
        │  authelia (SSO + TOTP)
        │  headscale (mesh coordinator, SQLite)
        │  portal  (status + Telegram alerts)
        └────────────┬────────────┘
                     │  nodes dial OUT (WireGuard) — no inbound needed
        ┌────────────┼─────────────┐
        ▼            ▼             ▼
      node1      node2   (…)
   CodeNomad:9898  CodeNomad:9898
   (+ local STT)   (+ local STT)
```

## Components
- **headscale** (self-hosted Tailscale control). Nodes join via `mesh.example.com`
  and establish a WireGuard mesh; DERP used only as relay fallback. Coordinator is
  NOT behind SSO (nodes authenticate with preauth keys / noise).
- **caddy** — public 443 entry. Obtains Let's Encrypt certs (HTTP-01, host is public),
  does `forward_auth` to Authelia, then `reverse_proxy` to the target node's mesh IP.
- **authelia** — SSO + TOTP. Password from the file backend; TOTP is enrolled by
  the user via the portal (stored in Authelia's DB, not the file).
- **portal** (`status.py`) — reads `conf/nodes.json`, health-checks each backend,
  renders a dashboard on `hub.example.com`, and sends Telegram alerts on
  down/recovery transitions.
- **node-join.sh** — idempotent onboarding: Node + opencode + codenomad +
  tailscale, a systemd unit (`CodeNomad` HTTP + `--dangerously-skip-auth`), and
  `WORKSPACE_ROOT` support for projects outside home (e.g. `/opt`).
- **generate_caddy.py** — data-driven: renders the Caddyfile routes (env name +
  aliases) and `nodes.json` from `conf/nodes.yaml`.

## Naming
- `name` → `<name>.example.com` (canonical, DNS-safe slug).
- `aliases` → extra subdomains to the same backend.
- `label / host / role / tags` → metadata for portal cards.
- `role`: dev | prod | tools | vpn (color-coded on the dashboard).

## Security model
- Only the hub exposes a public port (443). Nodes are reachable only inside the
  mesh (WAN). 
- Auth is terminated at the hub (Authelia). Nodes run CodeNomad with
  `--dangerously-skip-auth` — safe because they are not publicly reachable.
- Secrets: `/opt/caravan/.env` + `authelia/configuration.yml` + `users_database.yml`
  are kept off the hub and are not in git (see `.gitignore`, `conf/.env.example`).
