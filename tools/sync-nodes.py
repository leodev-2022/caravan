#!/usr/bin/env python3
"""Auto-register new mesh nodes into nodes.yaml (the hub-side "magic").

Run periodically by `caravan-sync-nodes.timer`. Any headscale node that is not
the hub itself and not yet in nodes.yaml is registered; the engine/port is
detected by probing the node over the mesh. Nodes whose backend is not listening
yet are skipped and picked up on a later tick.
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


def known_names():
    try:
        with open(os.path.join(BASE, "nodes.yaml"), encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return {e.get("name") for e in data.get("envs", [])}
    except Exception:
        return set()


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
    known = known_names()
    for n in headscale_nodes():
        name = (n.get("given_name") or n.get("name") or "").strip()
        ips = [a for a in (n.get("ip_addresses") or []) if ":" not in a]
        if not name or not ips:
            continue
        ip = ips[0]
        if ip in hubbed or name in known:
            continue
        port, engine = probe(ip)
        if not port:
            continue  # backend not up yet — a later tick retries
        print(f"[sync] registering {name} ({ip}:{port}, {engine})", flush=True)
        args = ["bash", os.path.join(BASE, "tools", "add-node.sh"),
                "--name", name, "--ip", ip, "--port", str(port), "--dir", BASE]
        if engine != "codenomad":
            args += ["--engine", engine]
        subprocess.run(args, check=False)


if __name__ == "__main__":
    main()
