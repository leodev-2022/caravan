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
    "web1": {"status": "online", "ms": 12, "since": -3600},
    "api": {"status": "online", "ms": 9, "since": -90000},
    "worker": {"status": "online", "ms": 27, "since": -7200},
    "workstation": {"status": "online", "ms": 34, "since": -259200},
    "laptop": {"status": "online", "ms": 41, "since": -600},
    "nas": {"status": "offline", "ms": 0, "since": -120},
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


def build(status, dark, modal):
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
            ("dashboard.png", True, False, "1400,860"),
            ("dashboard-light.png", False, False, "1400,860"),
            ("add-node.png", True, True, "1000,780"),
        ]
        for name, dark, modal, size in jobs:
            html = build(status, dark, modal)
            html_path = os.path.join(tmp, name + ".html")
            with open(html_path, "w", encoding="utf-8") as fh:
                fh.write(html)
            shot(browser, html_path, os.path.join(args.out, name), size)
            print("wrote", name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
