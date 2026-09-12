#!/usr/bin/env python3
# Apply CodeNomad hub change requests (written by the portal) to nodes.yaml,
# regenerate the Caddyfile, and reload Caddy. Runs on the hub (root).
import glob
import json
import os
import re
import subprocess
import sys
import time

import yaml

ANSI = re.compile(r"\x1b\[[0-9;]*m")

BASE = os.environ.get("CARAVAN_DIR", "/opt/hub")
REQ = os.path.join(BASE, "requests")
CFG = os.path.join(BASE, "nodes.yaml")
HS = os.environ.get("HS_CONTAINER", "headscale")


def delete_from_mesh(name):
    """Remove the node from headscale too — otherwise the auto-sync re-adds it."""
    try:
        r = subprocess.run(["docker", "exec", HS, "headscale", "nodes", "list", "-o", "json"],
                           capture_output=True, text=True, timeout=20)
        nodes = json.loads(r.stdout or "[]")
        nid = next((n.get("id") for n in nodes
                    if (n.get("given_name") or n.get("name")) == name), None)
        if nid is None:
            return False
        r = subprocess.run(["docker", "exec", HS, "headscale", "nodes", "delete",
                            "-i", str(nid), "--force"], capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            print("[apply] mesh delete failed:", (r.stderr or "").strip()[:200])
            return False
        print(f"[apply] removed {name} from the mesh (headscale)")
        return True
    except Exception:
        return False


def _apply_status(**kw):
    """Record the last apply's state so the portal can show live progress."""
    try:
        os.makedirs(os.path.join(BASE, "state"), exist_ok=True)
        with open(os.path.join(BASE, "state", "apply.json"), "w", encoding="utf-8") as f:
            json.dump(kw, f, ensure_ascii=False)
    except OSError:
        pass


def _provision_args(base, req):
    """Build the provision.sh argv + env for a request. Returns (args, env, err)."""
    script = os.path.join(base, "tools", "provision.sh")
    if not os.path.exists(script):
        return None, None, "tools/provision.sh not found"
    host = str(req.get("host", "")).strip()
    user = str(req.get("user", "")).strip() or "root"
    if not host:
        return None, None, "host required"
    args = ["bash", script, "--dir", base, "--host", host, "--user", user]
    env = dict(os.environ)
    if req.get("password"):
        env["PROVISION_PASSWORD"] = str(req["password"])
    elif req.get("key"):
        args += ["--key", str(req["key"])]
    # else: provision.sh falls back to the hub's provisioning key
    return args, env, ""


def handle_stt_check(base, req):
    """Check the target's resources for STT. Returns (ok, message, extra)."""
    args, env, err = _provision_args(base, req)
    if err:
        return False, err, {}
    args.append("--check")
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=120, env=env)
        out = ANSI.sub("", r.stdout or "")
        model = verdict = ""
        for ln in out.splitlines():
            if "recommendation:" in ln and "model=" in ln and "->" in ln:
                model = ln.split("model=", 1)[1].split()[0]
                verdict = ln.split("->", 1)[1].strip()
        if not verdict:
            tail = [x for x in out.strip().splitlines() if x.strip()]
            return False, (tail[-1] if tail else "resource check failed")[:200], {}
        safe = verdict.startswith("recommended") or verdict.startswith("strongly")
        print(f"[apply] stt-check: {model} -> {verdict}")
        return True, f"{model} · {verdict}", {"stt_model": model, "stt_verdict": verdict,
                                              "stt_safe": safe}
    except Exception as e:
        print("[apply] stt-check error:", e)
        return False, str(e)[:200], {}


def handle_provision(base, req, on_progress=None):
    """Provision a reachable machine over SSH. Returns (ok, short_message).

    `on_progress(text)` is called for each meaningful stage line so the portal
    can show live progress while the (long) provisioning runs.
    """
    args, env, err = _provision_args(base, req)
    if err:
        return False, err
    if req.get("name"):
        args += ["--name", str(req["name"])]
    if req.get("engine"):
        args += ["--engine", str(req["engine"])]
    if req.get("stt"):
        args.append("--stt")
    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, env=env, bufsize=1)
        tail = []
        for raw in proc.stdout:
            line = ANSI.sub("", raw).strip()
            if not line:
                continue
            tail.append(line)
            if on_progress and line.startswith("[") and "] " in line:
                on_progress(line.split("]", 1)[1].strip()[:200])
        proc.wait()
        for line in tail[-6:]:
            print("[apply] provision:", line)
        if proc.returncode != 0:
            msg = (tail[-1] if tail else "") or "provisioning failed"
            print("[apply] provision failed:", msg[:200])
            return False, msg[:300]
        reg = next((ln for ln in reversed(tail) if "->" in ln), "done")
        return True, reg[:300]
    except Exception as e:
        print("[apply] provision error:", e)
        return False, str(e)[:300]


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
        env = dict(req["env"])
        # An edit may rename the node: `original_name` is the name it had before.
        # Drop the old record too (otherwise the rename appends a duplicate card).
        original = str(req.get("original_name") or "").strip()
        names = {env["name"]}
        if original:
            names.add(original)
        prev = next((e for e in envs if original and e.get("name") == original), None)
        if prev is None:
            prev = next((e for e in envs if e.get("name") == env["name"]), None)
        # Keep the engine when an older edit form did not send one.
        if "engine" not in env and prev and prev.get("engine"):
            env["engine"] = prev["engine"]
        if not env.get("engine"):
            env.pop("engine", None)
        kept = [e for e in envs if e.get("name") not in names]
        return [*kept, env], True
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
        action = req.get("action", "add")
        label = ((req.get("env") or {}).get("name") or req.get("name")
                 or req.get("host") or "")
        started = time.time()
        _apply_status(status="running", action=action, name=label, started=started)
        ok, msg, extra = True, "", {}
        if action == "invite":
            handle_invite(BASE, REQ)
        elif action == "provision":
            def _progress(text, _label=label, _started=started):
                _apply_status(status="running", action="provision", name=_label,
                              message=text, started=_started)

            ok, msg = handle_provision(BASE, req, _progress)
        elif action == "stt-check":
            ok, msg, extra = handle_stt_check(BASE, req)
        else:
            envs, ch = apply_one(envs, req)
            if ch:
                changed = True
                print(f"[apply] {action} {label}")
            if action == "delete" and label:
                delete_from_mesh(label)
        os.remove(fn)
        final_name = label
        if action == "provision" and ok and "nodes.yaml:" in msg:
            # the provision registers under the machine's hostname — show that name
            final_name = msg.split("nodes.yaml:", 1)[1].split("->", 1)[0].strip() or label
        _apply_status(status=("ok" if ok else "error"), action=action, name=final_name,
                      message=msg, finished=time.time(), **extra)
    if changed:
        data["envs"] = envs
        save(data)
        subprocess.run([sys.executable, os.path.join(BASE, "generate_caddy.py")], check=False)
        subprocess.run(["docker", "restart", "caddy"], check=False)
        print("[apply] regenerated + reloaded caddy")

if __name__ == "__main__":
    main()
