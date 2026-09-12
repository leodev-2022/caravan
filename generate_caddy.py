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
    cfg = yaml.safe_load(f)
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
    hosts = [e["name"], *e.get("aliases", [])]
    for h in hosts:
        out.append("")
        out.append(f"{h}.{domain} {{")
        out.append("  encode gzip zstd")
        out.append("  forward_auth authelia:9091 {")
        out.append(f"    uri /api/authz/forward-auth?authelia_url={auth_url}/")
        out.append("    copy_headers Remote-User Remote-Groups Remote-Email Remote-Name")
        out.append("  }")
        out.append(f"  reverse_proxy http://{ip}:{port}")
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
with open(os.path.join(BASE, "nodes.json"), "w", encoding="utf-8") as f:
    json.dump({"domain": domain, "auth_url": auth_url, "envs": portal_envs}, f, ensure_ascii=False, indent=2)

print(f"generated {len(envs)} env route(s) [{tls_mode} TLS]; wrote caddy/Caddyfile + nodes.json")
