#!/usr/bin/env python3
# Apply CodeNomad hub change requests (written by the portal) to nodes.yaml,
# regenerate the Caddyfile, and reload Caddy. Runs on the hub (root).
import glob
import json
import os
import subprocess
import sys

import yaml

BASE = "/opt/hub"
REQ = os.path.join(BASE, "requests")
CFG = os.path.join(BASE, "nodes.yaml")

def load():
    with open(CFG, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def save(data):
    with open(CFG, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

def apply_one(envs, req):
    """Apply a single add/delete request to the envs list. Returns (envs, changed)."""
    act = req.get("action", "add")
    if act == "add" and isinstance(req.get("env"), dict) and req["env"].get("name"):
        env = req["env"]
        return [e for e in envs if e.get("name") != env["name"]] + [env], True
    if act == "delete" and req.get("name"):
        kept = [e for e in envs if e.get("name") != req["name"]]
        return kept, len(kept) != len(envs)
    return envs, False


def main():
    files = sorted(glob.glob(os.path.join(REQ, "*.json")))
    if not files:
        return
    data = load()
    envs = data.get("envs", [])
    changed = False
    for fn in files:
        try:
            with open(fn, encoding="utf-8") as f:
                req = json.load(f)
        except Exception as e:
            print(f"[apply] bad request {fn}: {e}")
            os.remove(fn)
            continue
        envs, ch = apply_one(envs, req)
        if ch:
            changed = True
            name = req.get("env", {}).get("name") or req.get("name")
            print(f"[apply] {req.get('action', 'add')} {name}")
        os.remove(fn)
    if changed:
        data["envs"] = envs
        save(data)
        subprocess.run([sys.executable, os.path.join(BASE, "generate_caddy.py")], check=False)
        subprocess.run(["docker", "restart", "caddy"], check=False)
        print("[apply] regenerated + reloaded caddy")

if __name__ == "__main__":
    main()
