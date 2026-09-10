# Security

Caravan is **secure by default**: the hardening lives in the installer and the
node agent, so you don't have to be a security engineer to run it. Paranoid
operators can go further (see the checklist at the end).

## Threat model
- **Protect:** your code, your credentials, and access to your machines.
- **From:** internet scanners, a compromised node, a curious tenant on a shared host.
- **Design goal:** one compromised component must not own the rest.

## Perimeter
- Only **443** is public (80 only for the ACME HTTP-01 redirect).
- **Nodes are mesh-only.** They dial **out** to the coordinator and expose **no
  inbound ports**. CodeNomad listens on the mesh, never on the internet.
- **SSO + TOTP (Authelia)** guards the dashboard and every node route; TOTP is
  enrolled on first login.

## Secrets
- Authelia `jwt` / `session` / `encryption` keys and the admin password hash live
  in `/opt/caravan/secrets.env` — **mode 600, root-only**.
- The stack env `/opt/caravan/.env` is **mode 600**.
- **Nothing secret is committed.** Only `*.template.yml` and `*.example` files are
  tracked. `make check` runs a secret scan; a local `.leak-patterns` guard (never
  committed) also fails the build on real infra values.

## Mesh & TLS
- **headscale** (self-hosted) coordinates a WireGuard mesh; DERP is only a relay
  fallback. Nodes authenticate with **short-lived preauth keys**.
- TLS terminates at the edge (Caddy, automatic ACME). Backends stay plain HTTP on
  the private mesh. `--self-signed` uses Caddy's internal CA for offline tests.

## Backups
- `caravan backup` captures configs + the headscale DB + Caddy data.
- Set `BACKUP_PASSPHRASE` to **encrypt** the archive (AES-256). Store it offsite
  and **test a restore** with `caravan restore`.

## Hardening checklist
Already done by the stack:
- [x] Default-deny inbound; only 443 public (80 for ACME).
- [x] Nodes mesh-only, no inbound ports.
- [x] SSO + TOTP at the perimeter.
- [x] Secrets root-only (600); never in git, logs, or process args.
- [x] Config generated from templates (never hand-edited); input validated;
      commands quoted; fail closed.
- [x] Pinned image versions.

Do on your host / for production:
- [ ] Enable the firewall: `ufw allow 80 && ufw allow 443 && ufw enable`.
- [ ] Encrypt backups (`BACKUP_PASSPHRASE`) and test a restore.
- [ ] Keep the host patched (unattended-upgrades).

## Reporting a vulnerability
Please report privately (see the repository profile) rather than opening a public
issue. We will acknowledge and coordinate a fix.
