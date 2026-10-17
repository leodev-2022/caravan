#!/usr/bin/env python3
"""Generate the hub Caddyfile + nodes.json from caravan.env + nodes.yaml.

caravan.env is the source of truth for DOMAIN / EMAIL (env vars override it).
nodes.yaml holds only the environments. Runs on the hub (writes caddy/Caddyfile
and nodes.json next to this file).
"""
import json
import os

import yaml

BASE = os.path.dirname(os.path.abspath(__file__))


def load_env_file(path):
    data = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                data[key.strip()] = val.strip().strip('"').strip("'")
    return data


_env = load_env_file(os.path.join(BASE, "caravan.env"))


def resolve(key, fallback=""):
    return os.environ.get(key) or _env.get(key) or fallback


nodes_path = os.path.join(BASE, "nodes.yaml")
if not os.path.exists(nodes_path):
    nodes_path = os.path.join(BASE, "nodes.example.yaml")
with open(nodes_path, encoding="utf-8") as f:
    cfg = yaml.safe_load(f) or {}
domain = resolve("DOMAIN", cfg.get("domain", ""))
email = resolve("EMAIL", cfg.get("email", ""))
auth_url = resolve("AUTH_URL", f"https://auth.{domain}" if domain else "")
tls_mode = resolve("TLS_MODE", "acme").lower()
envs = cfg.get("envs", [])
if not domain:
    raise SystemExit("DOMAIN is required (set it in caravan.env or the environment)")

out = []
out.append("{")
out.append("  admin off")
out.append(f"  email {email}")
if tls_mode == "internal":
    out.append("  local_certs")
out.append("}")
out.append("")
out.append(f"{domain} {{")
out.append(f"  redir https://hub.{domain}{{uri}} permanent")
out.append("}")
out.append("")
out.append(f"www.{domain} {{")
out.append(f"  redir https://hub.{domain}{{uri}} permanent")
out.append("}")
out.append("")
out.append(f"mesh.{domain} {{")
if tls_mode == "internal":
    # Serve the internal CA so nodes can trust the control server (tailscale
    # validates its TLS strictly).
    out.append("  handle /ca.crt {")
    # Caddy's local CA file is named root.crt; expose it as /ca.crt
    out.append("    rewrite * /root.crt")
    out.append("    root * /data/caddy/pki/authorities/local")
    out.append("    file_server")
    out.append("  }")
out.append("  reverse_proxy headscale:8080")
out.append("}")
out.append("")
out.append(f"auth.{domain} {{")
out.append("  reverse_proxy authelia:9091")
out.append("}")
out.append("")
out.append(f"hub.{domain} {{")
out.append("  encode gzip zstd")
out.append("  @pwa path /manifest.webmanifest /sw.js /icon-192.png /icon-512.png /favicon.ico")
out.append("  handle @pwa {")
out.append("    reverse_proxy portal:8090")
out.append("  }")
out.append("  handle {")
out.append("    forward_auth authelia:9091 {")
out.append(f"      uri /api/authz/forward-auth?authelia_url={auth_url}/")
out.append("      copy_headers Remote-User Remote-Groups Remote-Email Remote-Name")
out.append("    }")
out.append("    reverse_proxy portal:8090")
out.append("  }")
out.append("}")

for e in envs:
    ip = e["ip"]
    port = e["port"]
    share = e.get("share")            # optional artifact-share port on the node
    hosts = [e["name"], *e.get("aliases", [])]
    for h in hosts:
        out.append("")
        out.append(f"{h}.{domain} {{")
        out.append("  encode gzip zstd")
        # The engine is a PWA behind SSO. Never let a stale service worker or index
        # outlive an engine upgrade — a cached v1 UI next to a v2 server breaks with
        # e.g. "diagnoseOnce is not defined". Hashed /assets/* stay cacheable.
        out.append("  @fresh path /sw.js / /index.html")
        out.append('  header @fresh Cache-Control "no-store"')
        # PWA assets must load without SSO: a redirect to the auth portal breaks the
        # service worker and the web manifest (CORS), and a stale SW is what leaves a
        # client on an old UI after an engine upgrade.
        out.append("  @pwa path /manifest.webmanifest /sw.js /registerSW.js /favicon.ico "
                   "/pwa-64x64.png /pwa-192x192.png /pwa-512x512.png "
                   "/apple-touch-icon-180x180.png")
        out.append("  handle @pwa {")
        out.append(f"    reverse_proxy http://{ip}:{port}")
        out.append("  }")
        if share:
            # Artifact share: files the node publishes are served over https on the
            # SAME origin as the chat, so a markdown ![..](/s/<token>) renders inline
            # (no mixed content, no cross-site cookie). The path carries an
            # unguessable token from the node's share service.
            out.append("  handle /s/* {")
            out.append("    route {")
            out.append("      forward_auth authelia:9091 {")
            out.append(f"        uri /api/authz/forward-auth?authelia_url={auth_url}/")
            out.append("        copy_headers Remote-User Remote-Groups Remote-Email Remote-Name")
            out.append("      }")
            out.append("      uri strip_prefix /s")
            out.append(f"      reverse_proxy http://{ip}:{share}")
            out.append("    }")
            out.append("  }")
        out.append("  handle {")
        out.append("    forward_auth authelia:9091 {")
        out.append(f"      uri /api/authz/forward-auth?authelia_url={auth_url}/")
        out.append("      copy_headers Remote-User Remote-Groups Remote-Email Remote-Name")
        out.append("    }")
        out.append(f"    reverse_proxy http://{ip}:{port}")
        out.append("  }")
        out.append("}")

text = "\n".join(out) + "\n"
os.makedirs(os.path.join(BASE, "caddy"), exist_ok=True)
with open(os.path.join(BASE, "caddy", "Caddyfile"), "w", encoding="utf-8") as f:
    f.write(text)

# --- emit nodes.json (consumed by the status portal) ---
portal_envs = []
for e in envs:
    hosts = [e["name"], *e.get("aliases", [])]
    portal_envs.append({
        "name": e["name"],
        "aliases": list(e.get("aliases", [])),
        "hosts": hosts,
        "ip": e["ip"],
        "port": e["port"],
        "label": e.get("label", e["name"]),
        "location": e.get("location", ""),
        "tags": list(e.get("tags", [])),
        "engine": e.get("engine", ""),
    })
# the hub's provisioning public key (the portal shows it so a new machine only
# needs it in authorized_keys). It is a public key, safe to surface.
pubkey = ""
try:
    with open(os.path.join(BASE, ".ssh", "id_ed25519.pub"), encoding="utf-8") as f:
        pubkey = f.read().strip()
except OSError:
    pass
with open(os.path.join(BASE, "nodes.json"), "w", encoding="utf-8") as f:
    json.dump({"domain": domain, "auth_url": auth_url, "provision_pubkey": pubkey,
               "envs": portal_envs}, f, ensure_ascii=False, indent=2)

print(f"generated {len(envs)} env route(s) [{tls_mode} TLS]; wrote caddy/Caddyfile + nodes.json")
