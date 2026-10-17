#!/usr/bin/env python3
"""Generate the README screenshots from status.py (dev/marketing tool).

Renders the portal with anonymized sample data and captures PNGs with a headless
Chromium/Chrome/Edge binary (auto-detected).

    python3 scripts/screenshots.py [--out docs/img]
"""
import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env(name, ip, label, location, tags, aliases=None, engine=None):
    hosts = [name] + (aliases or [])
    env = {"name": name, "aliases": aliases or [], "hosts": hosts, "ip": ip,
           "port": 9898, "label": label, "location": location, "tags": tags}
    if engine:
        env["engine"] = engine
    return env


SAMPLE = {
    "domain": "example.com",
    "auth_url": "https://auth.example.com",
    "envs": [
        _env("web1", "100.64.0.10", "Web server", "Hetzner · Falkenstein", ["dev", "ai"], ["w1"]),
        _env("api", "100.64.0.11", "API service", "Hetzner · Falkenstein", ["prod"]),
        _env("worker", "100.64.0.12", "Build worker", "Hetzner · Falkenstein", ["ci"]),
        _env("workstation", "100.64.0.13", "Workstation", "Office", ["work"]),
        _env("laptop", "100.64.0.14", "Laptop", "Office", ["work"], engine="opencode"),
        _env("nas", "100.64.0.15", "Home NAS", "Home", ["storage"]),
    ],
}
STATUSES = {
    "web1": {"status": "online", "ms": 12, "since": -3600, "cpu": 4.2, "mem": 38.0, "uptime": 1036800},
    "api": {"status": "online", "ms": 9, "since": -90000, "cpu": 12.5, "mem": 55.0, "uptime": 2592000},
    "worker": {"status": "online", "ms": 27, "since": -7200, "cpu": 91.0, "mem": 82.0, "uptime": 432000},
    "workstation": {"status": "online", "ms": 34, "since": -259200, "cpu": 2.0, "mem": 40.0, "uptime": 7776000},
    "laptop": {"status": "online", "ms": 41, "since": -600, "cpu": 8.0, "mem": 60.0, "uptime": 10800},
    "nas": {"status": "offline", "ms": 0, "since": -120},
}
# show the engine version pair on online cards
for _s in STATUSES.values():
    if _s["status"] == "online":
        _s["engine_versions"] = {"codenomad": "0.20.1", "opencode": "2.0.22"}

# a bigger fleet: the dashboard switches to the list view above 8 nodes
SAMPLE10 = {
    "domain": "example.com",
    "auth_url": "https://auth.example.com",
    "envs": [
        _env("web1", "100.64.0.10", "Web server", "Hetzner · Falkenstein", ["dev", "ai"], ["w1"]),
        _env("api", "100.64.0.11", "API service", "Hetzner · Falkenstein", ["prod"]),
        _env("worker", "100.64.0.12", "Build worker", "Hetzner · Falkenstein", ["ci"]),
        _env("cache", "100.64.0.16", "Cache", "Hetzner · Falkenstein", ["prod"]),
        _env("workstation", "100.64.0.13", "Workstation", "Office", ["work"]),
        _env("laptop", "100.64.0.14", "Laptop", "Office", ["work"], engine="opencode"),
        _env("build", "100.64.0.17", "Build box", "Office", ["ci"]),
        _env("nas", "100.64.0.15", "Home NAS", "Home", ["storage"]),
        _env("media", "100.64.0.18", "Media server", "Home", ["media", "gpu"]),
        _env("edge", "100.64.0.19", "Edge proxy", "Helsinki", ["edge"]),
    ],
}
STATUSES10 = {
    "web1": {"status": "online", "ms": 14, "since": -86400 * 3, "cpu": 6.0, "mem": 41.0, "uptime": 86400 * 3},
    "api": {"status": "online", "ms": 11, "since": -86400 * 20, "cpu": 18.0, "mem": 62.0, "uptime": 86400 * 20},
    "worker": {"status": "online", "ms": 22, "since": -86400 * 2, "cpu": 93.0, "mem": 88.0, "uptime": 86400 * 2},
    "cache": {"status": "online", "ms": 8, "since": -86400 * 40, "cpu": 3.0, "mem": 22.0, "uptime": 86400 * 40},
    "workstation": {"status": "online", "ms": 31, "since": -86400 * 9, "cpu": 4.0, "mem": 37.0, "uptime": 86400 * 9},
    "laptop": {"status": "online", "ms": 41, "since": -600, "cpu": 8.0, "mem": 60.0, "uptime": 10800},
    "build": {"status": "online", "ms": 19, "since": -86400 * 5, "cpu": 12.0, "mem": 45.0, "uptime": 86400 * 5,
              "engine": "down"},
    "nas": {"status": "offline", "ms": 0, "since": -3600 * 5},
    "media": {"status": "online", "ms": 26, "since": -86400 * 12, "cpu": 47.0, "mem": 71.0, "uptime": 86400 * 12},
    "edge": {"status": "online", "ms": 63, "since": -86400 * 30, "cpu": 1.0, "mem": 12.0, "uptime": 86400 * 30},
}
for _s in STATUSES10.values():
    if _s["status"] == "online":
        _s.setdefault("engine_versions", {"codenomad": "0.20.1", "opencode": "2.0.22"})


INVITE_CMD = ("curl -fsSL https://raw.githubusercontent.com/leodev-2022/caravan/main/"
              "tools/node-join.sh | sudo bash -s -- --hub https://mesh.example.com "
              "--token hskey-auth-DEMO-XXXX")
ONBOARD = {
    "domain": "example.com",
    "auth_url": "https://auth.example.com",
    "provision_pubkey": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEXAMPLEKEY caravan-provision",
    "envs": [],
}


def load_status():
    spec = importlib.util.spec_from_file_location("status", os.path.join(ROOT, "status.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def find_browser():
    for name in ("chrome", "chromium", "chromium-browser", "google-chrome", "msedge"):
        path = shutil.which(name)
        if path:
            return path
    for path in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                 r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                 "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe",
                 "/mnt/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"):
        if os.path.exists(path):
            return path
    return None


def build(status, dark, modal, magic=False, engine=False, sample=None, statuses=None,
          view=None, quick=False, palette=False):
    html = status.render(sample or SAMPLE, statuses or STATUSES, 0, view=view)
    html = html.replace("localStorage.getItem('cn_lang')||'ru'",
                        "localStorage.getItem('cn_lang')||'en'")
    if not dark:
        html = html.replace("localStorage.getItem('cn_theme')||'dark'",
                            "localStorage.getItem('cn_theme')||'light'")
    if quick:
        # pin one node and leave two in "recently opened"
        seed = ("<script>localStorage.setItem('cn_pins','[\"web1\"]');"
                "localStorage.setItem('cn_recent','[\"api\",\"media\"]');</script>")
        html = html.replace("<body>", "<body>" + seed, 1)
    if palette:
        inject = ("<script>window.addEventListener('load',function(){"
                  "document.dispatchEvent(new KeyboardEvent('keydown',{key:'k',ctrlKey:true,bubbles:true}));"
                  "var q=document.getElementById('paletq'); if(q){q.value='web';"
                  "q.dispatchEvent(new Event('input',{bubbles:true}));}});</script>")
        html = html.replace("</body>", inject + "</body>")
    if modal:
        inject = (
            "<script>window.addEventListener('load',function(){"
            "var m=document.getElementById('modal');m.hidden=false;"
            "document.querySelector('#modal h3').textContent='Add environment';"
            "document.getElementById('f-name').value='web2';"
            "document.getElementById('f-ip').value='100.64.0.16';"
            "document.getElementById('f-label').value='Web server';"
            "document.getElementById('f-location').value='Hetzner · Falkenstein';"
            "document.getElementById('f-tags').value='dev, ai';});</script>")
        html = html.replace("</body>", inject + "</body>")
    if magic:
        inject = (
            "<script>window.addEventListener('load',function(){"
            "var b=document.getElementById('applybar');b.hidden=false;"
            "b.className='applybar run';"
            "b.textContent='\u23f3 laptop \u2014 installing Node.js 22 (NodeSource) \u00b7 1m';"
            "});</script>")
        html = html.replace("</body>", inject + "</body>")
    if engine:
        inject = (
            "<script>window.addEventListener('load',function(){"
            "document.getElementById('engtitle').textContent='Update engine to codenomad 0.21.0 / opencode 2.1.0';"
            "document.getElementById('engnotes').textContent="
            "'## Highlights\\n\\n- **Faster workspace startup**\\n- New diff viewer with inline comments\\n"
            "- Windows: more reliable process handling\\n- Bug fixes and stability';"
            "document.getElementById('engmodal').hidden=false;});</script>")
        html = html.replace("</body>", inject + "</body>")
    return html


def build_onboard(status, modal=False):
    tmpd = tempfile.mkdtemp()
    with open(os.path.join(tmpd, "invite.txt"), "w", encoding="utf-8") as fh:
        fh.write(INVITE_CMD)
    old = status.REQUESTS_DIR
    status.REQUESTS_DIR = tmpd
    try:
        html = status.render(ONBOARD, {}, 0)
    finally:
        status.REQUESTS_DIR = old
        shutil.rmtree(tmpd, ignore_errors=True)
    html = html.replace("localStorage.getItem('cn_lang')||'ru'",
                        "localStorage.getItem('cn_lang')||'en'")
    if modal:
        inject = ("<script>window.addEventListener('load',function(){"
                  "document.getElementById('joinmodal').hidden=false;});</script>")
        html = html.replace("</body>", inject + "</body>")
    return html


def shot(browser, html_path, png_path, size):
    subprocess.run(
        [browser, "--headless", "--disable-gpu", "--hide-scrollbars",
         f"--window-size={size}", f"--screenshot={png_path}",
         "file://" + html_path.replace("\\", "/")],
        check=True, capture_output=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.join(ROOT, "docs", "img"))
    args = parser.parse_args()
    args.out = os.path.abspath(args.out)  # Chrome needs an absolute --screenshot path

    browser = find_browser() or sys.exit("no Chromium/Chrome/Edge found")
    status = load_status()
    os.makedirs(args.out, exist_ok=True)
    tmp = tempfile.mkdtemp()
    try:
        jobs = [
            # name, kind, dark, modal, magic, engine, size, (extra render opts)
            ("dashboard.png", "dash", True, False, False, False, "1400,860"),
            ("dashboard-light.png", "dash", False, False, False, False, "1400,860"),
            ("onboarding.png", "onboard", True, False, False, False, "1400,900"),
            ("join.png", "onboard", True, True, False, False, "1400,900"),
            ("magic.png", "dash", True, False, True, False, "1400,860"),
            ("engine.png", "dash", True, False, False, True, "1400,860"),
            ("dashboard-list.png", "dash", True, False, False, False, "1400,900",
             dict(sample=SAMPLE10, statuses=STATUSES10, view="list", quick=True)),
            ("palette.png", "dash", True, False, False, False, "1400,900",
             dict(sample=SAMPLE10, statuses=STATUSES10, view="list", palette=True)),
        ]
        for job in jobs:
            name, kind, dark, modal, magic, engine, size = job[:7]
            opts = job[7] if len(job) > 7 else {}
            html = (build_onboard(status, modal) if kind == "onboard"
                    else build(status, dark, modal, magic, engine, **opts))
            html_path = os.path.join(tmp, name + ".html")
            with open(html_path, "w", encoding="utf-8") as fh:
                fh.write(html)
            shot(browser, html_path, os.path.join(args.out, name), size)
            print("wrote", name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
