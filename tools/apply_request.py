#!/usr/bin/env python3
# Apply CodeNomad hub change requests (written by the portal) to nodes.yaml,
# regenerate the Caddyfile, and reload Caddy. Runs on the hub (root).
import glob
import json
import os
import subprocess
import sys

import yaml

BASE = os.environ.get("CARAVAN_DIR", "/opt/hub")
REQ = os.path.join(BASE, "requests")
CFG = os.path.join(BASE, "nodes.yaml")


def handle_provision(base, req):
    """Provision a reachable machine over SSH (tools/provision.sh)."""
    script = os.path.join(base, "tools", "provision.sh")
    if not os.path.exists(script):
        print("[apply] provision: tools/provision.sh not found")
        return
    host = str(req.get("host", "")).strip()
    user = str(req.get("user", "")).strip()
    if not host or not user:
        print("[apply] provision: host & user required")
        return
    args = ["bash", script, "--dir", base, "--host", host, "--user", user]
    if req.get("name"):
        args += ["--name", str(req["name"])]
    if req.get("engine"):
        args += ["--engine", str(req["engine"])]
    env = dict(os.environ)
    if req.get("password"):
        env["PROVISION_PASSWORD"] = str(req["password"])
    elif req.get("key"):
        args += ["--key", str(req["key"])]
    else:
        print("[apply] provision: password or key required")
        return
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=1800, env=env)
        for line in (r.stdout or "").strip().splitlines()[-6:]:
            print("[apply] provision:", line)
        if r.returncode != 0:
            print("[apply] provision failed:", (r.stderr or "").strip()[:200])
    except Exception as e:
        print("[apply] provision error:", e)


def handle_invite(base, req_dir):
    """Mint a join token and write the one-line command to requests/invite.txt."""
    out = os.path.join(req_dir, "invite.txt")
    script = os.path.join(base, "tools", "invite.sh")
    if not os.path.exists(script):
        print("[apply] invite: tools/invite.sh not found")
        return
    try:
        r = subprocess.run(
            ["bash", script, "--command-only", "--write", out, "--dir", base],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode == 0:
            print("[apply] invite ready:", r.stdout.strip())
        else:
            print("[apply] invite failed:", (r.stderr or r.stdout).strip()[:200])
    except Exception as e:
        print("[apply] invite error:", e)

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
        if req.get("action") == "invite":
            handle_invite(BASE, REQ)
            os.remove(fn)
            continue
        if req.get("action") == "provision":
            handle_provision(BASE, req)
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
