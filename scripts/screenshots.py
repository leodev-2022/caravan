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
                 r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"):
        if os.path.exists(path):
            return path
    return None


def build(status, dark, modal, magic=False):
    html = status.render(SAMPLE, STATUSES, 0)
    html = html.replace("localStorage.getItem('cn_lang')||'ru'",
                        "localStorage.getItem('cn_lang')||'en'")
    if not dark:
        html = html.replace("localStorage.getItem('cn_theme')||'dark'",
                            "localStorage.getItem('cn_theme')||'light'")
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

    browser = find_browser() or sys.exit("no Chromium/Chrome/Edge found")
    status = load_status()
    os.makedirs(args.out, exist_ok=True)
    tmp = tempfile.mkdtemp()
    try:
        jobs = [
            # name, kind, dark, modal, magic, size
            ("dashboard.png", "dash", True, False, False, "1400,860"),
            ("dashboard-light.png", "dash", False, False, False, "1400,860"),
            ("onboarding.png", "onboard", True, False, False, "1400,900"),
            ("join.png", "onboard", True, True, False, "1400,900"),
            ("magic.png", "dash", True, False, True, "1400,860"),
        ]
        for name, kind, dark, modal, magic, size in jobs:
            html = (build_onboard(status, modal) if kind == "onboard"
                    else build(status, dark, modal, magic))
            html_path = os.path.join(tmp, name + ".html")
            with open(html_path, "w", encoding="utf-8") as fh:
                fh.write(html)
            shot(browser, html_path, os.path.join(args.out, name), size)
            print("wrote", name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
