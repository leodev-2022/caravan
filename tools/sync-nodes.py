#!/usr/bin/env python3
"""Auto-register new mesh nodes into nodes.yaml (the hub-side "magic").

Run periodically by `caravan-sync-nodes.timer`. Any headscale node that is not
the hub itself and not yet in nodes.yaml is registered; the engine/port is
detected by probing the node over the mesh. Nodes whose backend is not listening
yet are skipped and picked up on a later tick. A known node whose mesh IP changed
(e.g. it re-joined after a key expiry) is updated in place, so the card follows the
node instead of a duplicate appearing.
"""
import fcntl
import json
import os
import subprocess
import urllib.request

import yaml

BASE = os.environ.get("CARAVAN_DIR", "/opt/caravan")
HS = os.environ.get("HS_CONTAINER", "headscale")
PORTS = ((9898, "codenomad"), (4096, "opencode"))


def headscale_nodes():
    try:
        r = subprocess.run(
            ["docker", "exec", HS, "headscale", "nodes", "list", "-o", "json"],
            capture_output=True, text=True, timeout=20,
        )
        return json.loads(r.stdout or "[]")
    except Exception:
        return []


def hub_ips():
    ips = set()
    for cmd in (["tailscale", "ip", "-4"], ["tailscale", "ip", "-6"]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            ips.update(x for x in r.stdout.split() if x)
        except Exception:
            pass
    return ips


def known_envs():
    """Existing nodes.yaml entries (a card may have been renamed)."""
    try:
        with open(os.path.join(BASE, "nodes.yaml"), encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("envs") or []
    except Exception:
        return []


def find_env(envs, ip, name):
    """Match a mesh node to a card. Returns (env, moved).

    An exact IP match means "already known". A match on the card name, its stored
    `mesh_name` (the mesh name it came from, kept across renames) or an alias —
    compared case-insensitively, since a hostname like `IT-WorkTerm` may reach the
    mesh as `it-workterm` — means the node is known but its mesh IP changed, so we
    update it instead of adding a duplicate.
    """
    for e in envs:
        if e.get("ip") == ip:
            return e, False
    key = name.strip().lower()
    for e in envs:
        names = {str(e.get("name", "")), str(e.get("mesh_name", ""))}
        names.update(str(a) for a in (e.get("aliases") or []))
        if key and key in {n.strip().lower() for n in names}:
            return e, True
    return None, False


def probe(ip):
    for port, engine in PORTS:
        try:
            urllib.request.urlopen(f"http://{ip}:{port}/", timeout=3)
            return port, engine
        except Exception:
            continue
    return None, None


def main():
    # one run at a time: a manual run alongside the timer would race add-node
    lock_path = os.path.join(BASE, "state", "sync-nodes.lock")
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    lock = open(lock_path, "w", encoding="utf-8")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return  # another sync is running
    hubbed = hub_ips()
    envs = known_envs()
    for n in headscale_nodes():
        name = (n.get("given_name") or n.get("name") or "").strip()
        ips = [a for a in (n.get("ip_addresses") or []) if ":" not in a]
        if not name or not ips:
            continue
        ip = ips[0]
        if ip in hubbed:
            continue
        env, moved = find_env(envs, ip, name)
        if env is not None:
            if not moved:
                continue  # already registered under this IP
            if not env.get("port"):
                continue
            print(f"[sync] {env.get('name')} moved to {ip} — updating its card", flush=True)
            subprocess.run(["bash", os.path.join(BASE, "tools", "add-node.sh"),
                            "--name", str(env["name"]), "--ip", ip,
                            "--port", str(env["port"]), "--dir", BASE,
                            "--mesh-name", name], check=False)
            envs = known_envs()  # add-node rewrote nodes.yaml
            continue
        port, engine = probe(ip)
        if not port:
            continue  # backend not up yet — a later tick retries
        print(f"[sync] registering {name} ({ip}:{port}, {engine})", flush=True)
        args = ["bash", os.path.join(BASE, "tools", "add-node.sh"),
                "--name", name, "--ip", ip, "--port", str(port), "--dir", BASE,
                "--mesh-name", name]
        if engine != "codenomad":
            args += ["--engine", engine]
        subprocess.run(args, check=False)
        envs = known_envs()  # add-node rewrote nodes.yaml


if __name__ == "__main__":
    main()
