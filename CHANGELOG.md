# Changelog

Highlights of the Caravan journey. See **GitHub Releases** for the full notes of
each version.

## v0.7.x — onboarding & UX
- **Live step-by-step progress** while the hub provisions a machine over SSH
  (`installing Node` → `joining mesh` → `registered`), with elapsed time.
- A fresh hub hands you the **ready copy-paste command**; the **“magic”** SSH form
  (host + password/key) installs and registers a machine for you.
- **Auto-registration**: new mesh nodes appear on the dashboard by themselves.
- **Real delete** — removes the node from the dashboard, Caddy and the mesh
  (and it does not come back).

## v0.6.x — it just works
- The **hub joins its own mesh** (so it can reach nodes and proxy them).
- Self-signed mode serves the local CA at `/ca.crt` so nodes trust the control server.
- Windows nodes (`node-join.ps1`), multi-engine (CodeNomad / OpenCode), node metrics, PWA.

## v0.5.x — the new-user path
- **One-command hub install** with **automatic TOTP** (a scannable QR in the terminal).
- **One-command node join**; SSH provisioning; a friendly guard for Proxmox LXC (TUN).
- First-run **onboarding** screen instead of an empty dashboard.

## v0.1.0 — first public snapshot
- Hub stack (Caddy + Authelia + headscale + portal), the `caravan` CLI, node
  onboarding, docs and CI.

> Caravan consumes OpenCode (anomalyco, MIT) and CodeNomad (NeuralNomadsAI, MIT)
> as dependencies — it does not fork or rebrand them.
