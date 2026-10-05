# Changelog

Highlights of the Caravan journey. See **GitHub Releases** for the full notes of
each version.

## v0.7.9 - nodes that survive a re-join
- **Metrics bind the node's *current* mesh IP** at service start — on **Linux and
  Windows** alike. A node that re-joins under a new address keeps reporting instead
  of silently going offline; the agent stays mesh-only (loopback fallback, never a
  public interface).
- **Node auto-sync reconciles by name, not just IP**: a re-joined node's card
  *follows* it — matched case-insensitively on the mesh name / alias — instead of a
  duplicate card appearing. `add-node` now preserves a card's label/location/tags
  and records the mesh name (`mesh_name`), which survives a rename in the portal.

## v0.7.8 - onboarding robustness (found on a real work machine)
- **Node.js must be >= 22**: the engine pair calls `Promise.withResolvers()`, so an
  older Node (18/20) made the engine fail silently — CodeNomad then showed
  *"failed to load session permission decisions"*. `node-join` now checks the major
  version (Linux **and** Windows) and upgrades Node if it is too old.
- **No self-referential `/usr/bin` link** when the Node prefix is `/usr` (it broke
  `codenomad` with *"Too many levels of symbolic links"*); broken links are repaired.
- **Services restart** on re-run (the metrics agent used to keep a stale mesh IP).
- **Tailnet switching works**: a machine already on another tailnet is detected by
  `ControlURL` and re-joined to the hub.
- **Pre-flight checks** with clear messages: OS, privileges, Node version, TUN,
  free ports, another tailnet, existing engine, resources.

## v0.7.5 - engine updates & polish
- **Engine versioning, visible**: every node's card shows its engine pair
  (`CodeNomad` + `opencode`); the hub knows the newest *compatible* pair.
- **One-click engine updates**: the hub checks npm, shows "update available" with the
  **release notes**, and rolls the new pair out to the whole fleet — nodes pull it
  over the mesh (no inbound ports), canary-friendly.
- **Windows nodes are headless**: `tailscale --unattended` + a metrics agent that
  waits for the mesh IP, so a node comes back online after a reboot with **no RDP
  login**.
- **Durable VPN coexistence**: the mesh bypass adapts to the VPN's drifting
  `ip rule` priorities and re-applies on every tunnel up.
- A **landing page + demo GIF**.

## v0.7.x - onboarding & UX
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
