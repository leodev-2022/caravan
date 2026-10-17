#!/usr/bin/env python3
"""Caravan node metrics — a tiny stdlib HTTP server (mesh-only).

Serves GET /metrics -> {"uptime": s, "cpu": pct, "mem": pct, "mem_total_mb",
"mem_used_mb", "load": 1m}. Reads /proc; no dependencies. Bind it to the mesh IP.
"""
import glob
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Fail safe: bind loopback unless told otherwise, so a missing override can never
# expose the agent on a public interface.
HOST = os.environ.get("METRICS_HOST", "127.0.0.1")
PORT = int(os.environ.get("METRICS_PORT", "9101"))


def uptime_seconds():
    try:
        with open("/proc/uptime", encoding="ascii") as fh:
            return int(float(fh.read().split()[0]))
    except Exception:
        return 0


def cpu_percent():
    def snap():
        with open("/proc/stat", encoding="ascii") as fh:
            return [int(x) for x in fh.readline().split()[1:]]

    a = snap()
    time.sleep(0.15)
    b = snap()
    idle = (b[3] + (b[4] if len(b) > 4 else 0)) - (a[3] + (a[4] if len(a) > 4 else 0))
    total = sum(b) - sum(a)
    return round(100.0 * (total - idle) / total, 1) if total > 0 else 0.0


def memory():
    info = {}
    with open("/proc/meminfo", encoding="ascii") as fh:
        for line in fh:
            key, val = line.split(":", 1)
            info[key] = int(val.split()[0])
    total = info.get("MemTotal", 1) or 1
    avail = info.get("MemAvailable", info.get("MemFree", 0))
    used = total - avail
    return round(100.0 * used / total, 1), total // 1024, used // 1024


def load1():
    try:
        with open("/proc/loadavg", encoding="ascii") as fh:
            return float(fh.read().split()[0])
    except Exception:
        return 0.0


def _pkg_version(*segments):
    """Version of an installed npm package (the engine), read from its
    package.json. Handles a custom Node prefix (e.g. /opt/node-*)."""
    roots = ["/usr/lib/node_modules", "/usr/local/lib/node_modules"]
    roots += sorted(glob.glob("/opt/node-*/lib/node_modules"))
    for root in roots:
        try:
            with open(os.path.join(root, *segments, "package.json"), encoding="utf-8") as fh:
                return json.load(fh).get("version")
        except Exception:
            continue
    return None


# the installed engine pair, resolved once at import time
ENGINE_VERSIONS = {
    "codenomad": _pkg_version("@neuralnomads", "codenomad"),
    "opencode": _pkg_version("@opencode", "cli") or _pkg_version("opencode-ai"),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?", 1)[0] not in ("/metrics", "/"):
            self.send_response(404)
            self.end_headers()
            return
        mem_pct, mem_total, mem_used = memory()
        payload = {
            "uptime": uptime_seconds(),
            "cpu": cpu_percent(),
            "mem": mem_pct,
            "mem_total_mb": mem_total,
            "mem_used_mb": mem_used,
            "load": load1(),
            "engine_versions": ENGINE_VERSIONS,
        }
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
