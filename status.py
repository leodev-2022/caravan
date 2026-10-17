#!/usr/bin/env python3
# CodeNomad hub portal (stdlib only). Serves /, /status.json, /favicon.ico on :8090.
# Neo-brutalist theme (blue / white / orange) with a touch of depth.
import base64
import contextlib
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NODES_JSON = os.environ.get("NODES_JSON", "/data/nodes.json")
REQUESTS_DIR = os.environ.get("REQUESTS_DIR", "/data/requests")
STATE_FILE = os.environ.get("STATE_FILE", "/data/state/status.json")
REFRESH = int(os.environ.get("PORTAL_REFRESH", "10"))
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT", "")
DOCS_URL = os.environ.get("DOCS_URL", "https://github.com/leodev-2022/caravan#quick-start")
# engine update policy: off = never check, notify = show "update available",
# auto = the hub rolls out (canary) — mirrors CodeNomad's own semantics
ENGINE_UPDATE = os.environ.get("ENGINE_UPDATE", "notify")
# above this many nodes the dashboard opens as a list instead of tiles
LIST_AT = int(os.environ.get("LIST_AT", "8"))
ENGINE_FILE = os.environ.get("ENGINE_FILE", "/data/state/engine.json")
HANDOFF_FILE = os.environ.get(
    "HANDOFF_FILE", os.path.join(os.path.dirname(STATE_FILE), "handoff.jsonl"))
HANDOFF_SEEN_FILE = os.environ.get(
    "HANDOFF_SEEN_FILE", os.path.join(os.path.dirname(STATE_FILE), "handoff-seen.json"))
# Ping the admin's Telegram on a new board note from an agent (disable: HANDOFF_NOTIFY=0)
HANDOFF_NOTIFY = os.environ.get("HANDOFF_NOTIFY", "1") != "0"
TG_OFFSET_FILE = os.environ.get(
    "TG_OFFSET_FILE", os.path.join(os.path.dirname(STATE_FILE), "tg-offset.json"))

LOGO_SVG = ('<svg width="44" height="44" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">'
            '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
            '<stop offset="0" stop-color="#ffb26b"/><stop offset="1" stop-color="#d97b23"/></linearGradient></defs>'
            '<rect x="2" y="2" width="60" height="60" rx="16" fill="url(#g)"/>'
            '<path d="M43 21a16 16 0 1 0 0 22" stroke="#20160a" stroke-width="7" stroke-linecap="round" fill="none"/></svg>')
FAVICON = "data:image/svg+xml;base64," + base64.b64encode(LOGO_SVG.encode()).decode()
ICON_192_PNG = "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"
ICON_512_PNG = "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"

MANIFEST_JSON = json.dumps({
    "name": "Caravan",
    "short_name": "Caravan",
    "description": "Self-hosted AI coding cockpit",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#0b0f14",
    "theme_color": "#0b0f14",
    "icons": [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
    ],
})

SW_JS = """
const C='caravan-v2';
self.addEventListener('install',function(){self.skipWaiting();});
self.addEventListener('activate',function(e){e.waitUntil(
  caches.keys().then(function(ks){return Promise.all(ks.filter(function(k){return k!==C;}).map(function(k){return caches.delete(k);}));})
    .then(function(){return self.clients.claim();}));});
self.addEventListener('fetch',function(e){
  var u=new URL(e.request.url);
  if(e.request.method!=='GET'||e.request.mode==='navigate'||u.pathname==='/'||u.pathname.indexOf('/status.json')===0||u.pathname.indexOf('/api/')===0)return;
  e.respondWith(fetch(e.request).then(function(r){var c=r.clone();caches.open(C).then(function(x){x.put(e.request,c);});return r;})
    .catch(function(){return caches.match(e.request);}));
});
"""

_cache = {"html": "<body>loading</body>", "statuses": {}, "ts": 0, "nodes": None}
_lock = threading.Lock()
_last_status = {}
_initialized = [False]
_ever_online = set()
_since = {}
_since_status = {}
_last_metrics = {}
# per-node engine state ("ok" | "busy" | "down") — see track_engine()
_eng_state = {}
_engine = {"target": None, "checked": 0.0}  # latest compatible pair from npm
PALETTE = ["#f2994a", "#5b9dff", "#34d399", "#c084fc", "#f472b6", "#22d3ee"]

def load_data():
    with open(NODES_JSON, encoding="utf-8") as f:
        return json.load(f)

def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            st = json.load(f)
        return st.get("since", {}) or {}, st.get("status", {}) or {}
    except Exception:
        return {}, {}

def save_state():
    try:
        d = os.path.dirname(STATE_FILE)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"since": _since, "status": _since_status}, f)
    except Exception:
        pass

def load_apply():
    try:
        with open(os.path.join(os.path.dirname(STATE_FILE), "apply.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def load_engine_desired():
    try:
        with open(ENGINE_FILE, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}

def save_engine_desired(d):
    try:
        os.makedirs(os.path.dirname(ENGINE_FILE), exist_ok=True)
        with open(ENGINE_FILE, "w", encoding="utf-8") as f:
            json.dump(d or {}, f)
        os.chmod(ENGINE_FILE, 0o600)
    except Exception:
        pass

def engine_json():
    """The engine pair nodes should run (pulled over the mesh at /engine.json)."""
    if ENGINE_UPDATE == "off":
        return {"roll": False}
    d = load_engine_desired()
    if not d and ENGINE_UPDATE == "auto" and _engine.get("target"):
        d = {"codenomad": _engine["target"][0], "opencode": _engine["target"][1]}
    if not d or not d.get("codenomad"):
        return {"roll": False}
    return {"roll": True, "codenomad": d.get("codenomad"), "opencode": d.get("opencode")}

def check(ip, port):
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(f"http://{ip}:{port}/", method="GET"), timeout=4) as r:
            return "online", int((time.time() - t0) * 1000), r.status
    except Exception:
        return "offline", int((time.time() - t0) * 1000), None

def check_metrics(ip, port):
    try:
        with urllib.request.urlopen(f"http://{ip}:{port}/metrics", timeout=4) as r:
            return json.load(r)
    except Exception:
        return {}

# A failed engine probe means one of two very different things: a *fast* refusal
# (nothing is listening — the engine is down) or a *slow* timeout (it is up but
# busy/hung). Only the first is an incident, so the wording and the alert differ.
ENGINE_REFUSED_MS = 1500


def classify_engine(engine_online, ms):
    """'ok' | 'down' (refused — nothing listening) | 'busy' (slow / timed out)."""
    if engine_online:
        return "ok"
    return "down" if (ms or 0) < ENGINE_REFUSED_MS else "busy"

def _newer(a, b):
    """True when version a is newer than b (numeric dotted compare)."""
    def norm(v):
        parts = [int(p) if p.isdigit() else 0 for p in (v or "").split(".")[:3]]
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts)
    return bool(a) and norm(a) > norm(b)


def plural_ru(n, one, few, many):
    """Russian plural form: 1 узел / 2 узла / 5 узлов."""
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return few
    return many


def node_flags(env, st, tgt=None):
    """How much attention one node needs, and why.

    Severity order (0 is the worst): offline -> engine down -> hot -> engine busy
    -> warm -> engine update -> fine. The dashboard uses it to put problems first
    and to count them; keep it in sync with the JS mirror in `applyOne`.
    """
    st = st or {}
    online = st.get("status") == "online"
    ev = st.get("engine_versions") or {}
    behind = bool(tgt and ev and (_newer(tgt[0], ev.get("codenomad"))
                                  or _newer(tgt[1], ev.get("opencode"))))
    cpu, mem = st.get("cpu"), st.get("mem")
    hot = (cpu is not None and cpu >= 90) or (mem is not None and mem >= 90)
    warm = (cpu is not None and cpu >= 75) or (mem is not None and mem >= 75)
    engine = st.get("engine") or ""
    if not online:
        sev = 0
    elif engine == "down":
        sev = 1
    elif hot:
        sev = 2
    elif engine == "busy":
        sev = 3
    elif warm:
        sev = 4
    elif behind:
        sev = 5
    else:
        sev = 6
    return {"online": online, "engine": engine, "hot": hot, "warm": warm,
            "behind": behind, "sev": sev}

def engine_target():
    """Newest compatible engine pair (codenomad, opencode) on npm, or None.
    The opencode version is CodeNomad's exact `@opencode/client` dependency."""
    try:
        with urllib.request.urlopen("https://registry.npmjs.org/@neuralnomads/codenomad/latest", timeout=6) as r:
            cn = json.load(r)
        oc = ((cn.get("dependencies") or {}).get("@opencode/client") or "").lstrip("^~>=< ")
        return (cn.get("version"), oc or None)
    except Exception:
        return None

def release_notes(version):
    """Release notes for a CodeNomad version from GitHub, or ''."""
    if not version:
        return ""
    for tag in (f"v{version}", version):
        try:
            with urllib.request.urlopen(
                    f"https://api.github.com/repos/NeuralNomadsAI/CodeNomad/releases/tags/{tag}",
                    timeout=6) as r:
                return (json.load(r).get("body") or "").strip()
        except Exception:
            continue
    return ""

def notify(text, buttons=None):
    if not (TG_TOKEN and TG_CHAT):
        return False
    try:
        data = {"chat_id": TG_CHAT, "text": text}
        if buttons:
            data["reply_markup"] = json.dumps({"inline_keyboard": buttons}, ensure_ascii=False)
        payload = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=8):
            print(f"[tg] sent: {text.splitlines()[0][:120]}", flush=True)
        return True
    except Exception as e:
        print(f"[tg] FAIL: {str(e)[:120]}", flush=True)
        return False

_started = time.time()
# after a restart the first checks can read "offline" briefly — don't alert on
# transitions during this warm-up window (avoids a burst of "back online" spam)
WARMUP = int(os.environ.get("PORTAL_WARMUP", "60"))


def track_transitions(envs, cur):
    if not _initialized[0]:
        for name, (st, _ms) in cur.items():
            if st == "online":
                _ever_online.add(name)
        _last_status.update(cur)
        _initialized[0] = True
        return
    for e in envs:
        name = e["name"]
        st, _ms = cur.get(name, ("offline", 0))
        prev = _last_status.get(name)
        if prev is not None and prev != st:
            warm = time.time() - _started < WARMUP
            if st == "online" and prev == "offline":
                if name in _ever_online and not warm:
                    notify(f"\U0001F7E2 {name} ({e.get('label', name)}) is back online")
            elif st == "offline" and name in _ever_online and not warm:
                notify(f"\U0001F534 {name} ({e.get('label', name)}) is DOWN")
            _ever_online.add(name)
        _last_status[name] = st

def track_engine(envs, engines):
    """Warn when a node's engine stops answering while the host itself is fine.

    The metrics agent is independent of the engine on purpose, so a node can look
    "online" (its CPU/RAM are live) while the engine is dead or bound to loopback
    — exactly the "stuck node" we got after a reboot. Alert on the transition,
    once, and note the recovery. `engines` maps a node name to ok | busy | down.
    """
    if not _initialized[0]:
        for name in engines:
            _eng_state[name] = engines[name]
        return
    for e in envs:
        name = e["name"]
        st = engines.get(name)
        prev = _eng_state.get(name)
        _eng_state[name] = st
        if prev is None or st is None or prev == st:
            continue
        if st == "down":
            notify(f"\u26A0\uFE0F {name} ({e.get('label', name)}): engine is not answering "
                   f"(port {e.get('port', 9898)} is not listening) while the host is up \u2014 "
                   f"looks like a stuck node; start the engine task on the node.")
        elif prev == "down" and st == "ok":
            notify(f"\u2705 {name}: engine answers again")


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def humanize(seconds):
    s = int(max(0, seconds))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"

def mcls(v):
    try:
        v = float(v)
    except Exception:
        return ""
    if v >= 90:
        return "hot"
    if v >= 75:
        return "warm"
    return ""

def loc_color(loc):
    h = 0
    for ch in (loc or "?"):
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return PALETTE[h % len(PALETTE)]

CSS = """
:root{--accent:#f2994a;--accent2:#ffb26b;--accent-ink:#20160a;
  --bg:#0b0f14;--panel:#131922;--panel2:#0f151d;--line:#222c38;--line2:#303c4a;
  --ink:#e9eff7;--muted:#8a99ad;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --ok:#34d399;--down:#f87171;--warn:#fbbf24;--radius:12px;--radius-sm:8px;--ctl:32px;
  /* one type scale: micro / secondary / UI / prose / emphasized / title / brand */
  --f1:11px;--f2:12px;--f3:13px;--f4:15px;--f5:18px;--f6:22px;
  --tb:73px;   /* taller than it looks: keep sticky things just below the header */
  --shadow:0 10px 30px -14px rgba(0,0,0,.7);--topbar:#0b0f14}
[data-theme="light"]{--bg:#f6f8fb;--panel:#ffffff;--panel2:#fbfcfe;--line:#e3e8ef;--line2:#d4dae3;
  --ink:#0f1b2a;--muted:#5b6b7f;--shadow:0 10px 30px -14px rgba(15,27,42,.22);--topbar:#f6f8fb}
*{box-sizing:border-box}
select{font:inherit}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:4px}
body{margin:0;font-family:Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;font-size:14px;line-height:1.45;color:var(--ink);
  background-color:var(--bg);background-image:radial-gradient(900px 480px at 50% -12%,rgba(242,153,74,.08),transparent 70%);
  min-height:100vh;display:flex;flex-direction:column;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{width:100%;max-width:1320px;margin:0 auto;padding:24px 24px 48px;flex:1 0 auto;display:flex;flex-direction:column}
/* left rail: places + view controls, stable like a session tree; collapses to a
   chip strip on narrow screens */
.shell{width:100%;max-width:1440px;margin:0 auto;padding:20px 24px 48px;display:grid;
  grid-template-columns:208px minmax(0,1fr);gap:28px;align-items:start;flex:1 0 auto}
.shell.lone{grid-template-columns:minmax(0,1fr)}
.shell.lone .rail{display:none}
.shell>.wrap{max-width:none;margin:0;padding:0;min-width:0}
.rail{position:sticky;top:calc(var(--tb) + 10px);display:flex;flex-direction:column;gap:10px;min-width:0}
.rl-title{font-size:var(--f1);text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:700;padding-left:10px}
.rl-chips{display:flex;flex-direction:column;gap:2px}
.rl-chips .chipf{width:100%;justify-content:flex-start;border-color:transparent;background:none;padding:0 10px;color:var(--muted)}
.rl-chips .chipf:hover{background:var(--panel);border-color:var(--line);color:var(--ink)}
.rl-chips .chipf.active{background:var(--accent);border-color:transparent;color:var(--accent-ink)}
.rl-chips .chipf .cnt{margin-left:auto}
.rl-actions{display:flex;flex-direction:column;gap:6px;margin-top:2px}
.rl-actions .seg{width:100%}
.rl-actions .segbtn{flex:1;justify-content:center}
.rl-meta{font-size:var(--f2);line-height:1.55;color:var(--muted);padding-left:10px}
/* sortable column header for the list view */
.lhead{position:sticky;top:var(--tb);z-index:9;display:grid;
  grid-template-columns:118px minmax(200px,1.8fr) 210px 215px 240px;
  gap:14px;align-items:center;height:32px;padding:0 14px;background:var(--bg);
  border-bottom:1px solid var(--line);margin:0 0 2px}
.lh{border:0;background:none;color:var(--muted);font-weight:700;font-size:var(--f1);line-height:1;text-transform:uppercase;
  letter-spacing:.07em;display:inline-flex;align-items:center;gap:5px;padding:0;cursor:pointer;text-align:left}
.lh:hover{color:var(--ink)}
.lh.on{color:var(--ink)}
.lh.static{cursor:default}
.lh.rhs{justify-content:flex-end}
.lh .ar{font-size:var(--f1);color:var(--accent);min-width:8px}
/* command palette (Ctrl+K) */
.palet{position:fixed;inset:0;z-index:70;background:rgba(5,9,14,.6);display:flex;align-items:flex-start;
  justify-content:center;padding:10vh 16px 16px}
.palet[hidden]{display:none}
.paletbox{width:min(560px,100%);background:var(--panel);border:1px solid var(--line2);border-radius:12px;
  box-shadow:0 30px 60px -30px rgba(0,0,0,.85);overflow:hidden}
#paletq{width:100%;height:46px;border:0;border-bottom:1px solid var(--line);background:none;color:var(--ink);
  font-weight:500;font-size:var(--f4);line-height:1.2;padding:0 16px;outline:none}
.paletlist{max-height:min(52vh,420px);overflow:auto;padding:6px}
.pi{display:flex;gap:10px;align-items:center;padding:9px 10px;border-radius:var(--radius-sm);cursor:pointer;
  font-size:var(--f3);color:var(--ink2)}
.pi:hover,.pi.sel{background:var(--panel2);color:var(--ink)}
.pi .pk{font-weight:500;font-size:var(--f1);line-height:1;font-family:var(--mono);color:var(--muted);margin-left:auto;max-width:45%;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.pi .pdot{width:7px;height:7px;border-radius:50%;background:var(--muted);flex:0 0 auto}
.pi .pdot.ok{background:var(--ok)}
.pi .pdot.bad{background:var(--down)}
.paletfoot{border-top:1px solid var(--line);padding:8px 12px;font-size:var(--f2);color:var(--muted)}
.paletfoot b{color:var(--ink2);font-family:var(--mono);font-weight:600}
.pempty{padding:16px;text-align:center;color:var(--muted);font-size:var(--f3)}
.topbar{position:sticky;top:0;z-index:30;background:var(--topbar);border-bottom:1px solid var(--line);
  box-shadow:0 8px 18px -16px rgba(0,0,0,.7)}
.topbar-in{max-width:1440px;margin:0 auto;padding:14px 24px;display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:12px}
.brand .name{font-size:var(--f6);font-weight:800;letter-spacing:-.01em;line-height:1}
.brand .name span{color:var(--accent)}
.brand .sub{font-size:var(--f2);color:var(--muted);margin-top:5px}
.ctrls{margin-left:auto;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.search{position:relative}
.search input{width:280px;max-width:56vw;height:var(--ctl);padding:0 12px 0 34px;border:1px solid var(--line);
  border-radius:var(--radius-sm);background:var(--panel);font-size:var(--f3);color:var(--ink);outline:none;
  transition:border-color .15s,box-shadow .15s}
.search input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(242,153,74,.15)}
.search svg{position:absolute;left:11px;top:8px;color:var(--muted)}
/* one control scale: every clickable thing shares height, radius and type —
   hierarchy comes from colour, never from size or a different corner */
.iconbtn2,.addbtn,.open,.mini,.chipf,.segbtn,.stat{
  height:var(--ctl);border-radius:var(--radius-sm);font-weight:600;font-size:var(--f3);line-height:1;
  font-family:inherit;
  display:inline-flex;align-items:center;justify-content:center;gap:7px;white-space:nowrap;
  text-decoration:none;cursor:pointer}
.iconbtn2{border:1px solid var(--line);background:var(--panel);color:var(--ink);padding:0 12px;
  transition:border-color .15s,background .15s}
.iconbtn2:hover{border-color:var(--line2);background:var(--panel2);text-decoration:none}
.addbtn{border:1px solid transparent;background:var(--accent);color:var(--accent-ink);padding:0 14px;font-weight:700;
  transition:background .15s}
.addbtn:hover{background:var(--accent2)}
.filters{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding-top:0;padding-bottom:12px}
.chipf{border:1px solid var(--line);background:var(--panel);color:var(--muted);padding:0 12px;transition:all .15s}
.chipf:hover{color:var(--ink);border-color:var(--line2)}
.chipf.active{background:var(--accent);color:var(--accent-ink);border-color:transparent}
.chipf .cnt{font-family:var(--mono);font-size:var(--f1);font-weight:700;opacity:.72}
.chipf.active .cnt{opacity:.85}
.fright{margin-left:auto;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:var(--radius-sm);overflow:hidden;background:var(--panel);
  height:var(--ctl)}
.segbtn{border:0;background:none;color:var(--muted);padding:0 12px;border-radius:0}
.segbtn:hover{color:var(--ink);text-decoration:none}
.segbtn.on{background:var(--panel2);color:var(--ink)}
#probtn.on{border-color:var(--accent);color:var(--ink);background:rgba(242,153,74,.10)}
/* list view: one line per node — scans better than tiles once the fleet grows */
.rows{display:grid;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius)}
.nrow{display:grid;grid-template-columns:118px minmax(200px,1.8fr) 210px 215px 240px;gap:14px;align-items:center;
  padding:9px 14px;border-bottom:1px solid var(--line);min-width:0}
.nrow:last-child{border-bottom:0}
.nrow:hover{background:var(--panel2)}
.nrow .pill{margin-left:0}
.nrow .nmain{min-width:0}
.nrow .ntitle{font-size:var(--f3);font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nrow .ntags{font-weight:600;font-size:var(--f1);line-height:1;font-family:var(--mono);color:var(--muted);margin-left:8px;letter-spacing:.02em}
.nrow .nsub{color:var(--muted);font-size:var(--f2);margin-top:2px;white-space:normal;overflow-wrap:anywhere}
.nrow .nsub b{color:var(--ink2);font-family:var(--mono);font-weight:600}
.nrow .nload{font-size:var(--f2);color:var(--muted);font-family:var(--mono);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nrow .nload b{color:var(--ink);font-weight:600}
.nrow .neng{font-size:var(--f2);color:var(--muted);font-family:var(--mono);display:flex;gap:9px;align-items:center;
  flex-wrap:wrap;min-width:0}
.nrow .neng b{color:var(--ink2);font-weight:600}
.nrow .actions{margin-top:0;flex-wrap:nowrap;justify-content:flex-end}
/* attention summary: the first thing the eye should answer — “is anything wrong?” */
.stats{display:flex;align-items:stretch;gap:8px;flex-wrap:wrap;margin:0 0 10px}
.stat{border:1px solid var(--line);background:var(--panel);padding:0 11px;font-size:var(--f3);color:var(--muted);
  font-family:inherit;transition:border-color .15s,background .15s}
.stat:hover{border-color:var(--line2)}
.stat b{font-family:var(--mono);font-size:var(--f4);font-weight:700;color:var(--ink);line-height:1}
.stat.good b{color:var(--ok)}
.stat.bad b{color:var(--down)}
.stat.warn b{color:var(--warn)}
.stat.on{border-color:var(--accent);background:rgba(242,153,74,.10);color:var(--ink)}
.stat.static{cursor:default}
.stat[hidden]{display:none}
.updbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 12px;padding:8px 12px;
  border:1px solid rgba(251,191,36,.35);border-radius:var(--radius-sm);background:rgba(251,191,36,.06);
  font-size:var(--f3);color:var(--ink2)}
.updbar b{font-family:var(--mono);color:var(--ink);font-weight:700}
.updbar .mini{font-weight:700}
.updbar .updl{margin-left:auto}
/* quick access: pinned nodes + recently opened — the person's shortlist */
.quick{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin:0 0 12px}
.qlabel{font-size:var(--f1);text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:700;margin-right:2px}
.qchip{height:var(--ctl);padding:0 10px;border:1px solid var(--line);border-radius:var(--radius-sm);
  background:var(--panel);color:var(--ink2);font-weight:600;font-size:var(--f3);line-height:1;display:inline-flex;align-items:center;gap:7px;cursor:pointer}
.qchip:hover{border-color:var(--line2);background:var(--panel2)}
.qchip.pin{border-color:rgba(242,153,74,.45)}
.qdot{width:7px;height:7px;border-radius:50%;background:var(--muted);flex:0 0 auto}
.qdot.ok{background:var(--ok)}
.qdot.bad{background:var(--down)}
.qpin{font-size:var(--f1);opacity:.85}
@keyframes flash{from{box-shadow:0 0 0 2px var(--accent)}to{box-shadow:0 0 0 2px transparent}}
.node.flash{animation:flash 1.2s ease-out}
.pinrow{display:flex;gap:9px;align-items:center;font-size:var(--f3);margin:2px 0 10px;cursor:pointer;color:var(--ink2)}
.pinrow input{width:16px;height:16px;accent-color:var(--accent)}
.pinrow input:disabled{opacity:.45}
.gcnt{font-family:var(--mono);font-size:var(--f1);color:var(--warn);border:1px solid rgba(251,191,36,.45);
  border-radius:999px;padding:1px 7px;margin-left:4px}
.gcnt.bad{color:var(--down);border-color:rgba(248,113,113,.45)}
.gcnt[hidden]{display:none}
.meta-line{color:var(--muted);font-size:var(--f2);margin-left:auto;font-weight:500}
h2.group{font-size:var(--f2);text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:600;
  margin:20px 0 10px;display:flex;align-items:center;gap:9px;cursor:pointer;user-select:none}
h2.group .dot{width:8px;height:8px;border-radius:50%;background:var(--rc,var(--accent))}
h2.group .chev{font-size:var(--f1);opacity:.75;transition:transform .15s;order:-1}
h2.group.collapsed .chev{transform:rotate(-90deg)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(300px,100%),1fr));gap:12px;align-items:stretch}
.grid.collapsed{display:none}
.rows.collapsed{display:none}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  padding:14px;transition:border-color .15s;position:relative;min-width:0;
  display:flex;flex-direction:column}
.card:hover{border-color:var(--line2)}
.top{display:flex;align-items:center;gap:8px;margin-bottom:12px;min-width:0}
.chip{color:var(--muted);font-size:var(--f1);font-weight:600;padding:3px 9px;border-radius:999px;border:1px solid var(--line);
  background:var(--panel2);display:inline-flex;align-items:center;gap:6px}
.chip::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--rc,var(--accent))}
/* inside a location group the place is already named by the heading: a colour dot
   keeps the cue without repeating the word on every card */
.chip.dotonly{padding:0;border:0;background:none;width:9px;height:9px;flex:0 0 auto}
.chip.dotonly::before{width:9px;height:9px}
.engine{font-size:var(--f1);font-weight:600;color:var(--accent);border:1px solid var(--line);border-radius:999px;padding:2px 8px;background:var(--panel2)}
.pill{margin-left:auto;display:inline-flex;align-items:center;gap:6px;font-size:var(--f1);font-weight:700;white-space:nowrap;
  padding:4px 10px;border-radius:999px;background:rgba(52,211,153,.14);color:var(--ok)}
.pill.offline{background:rgba(248,113,113,.14);color:var(--down)}
.pill .dot{width:7px;height:7px;border-radius:50%;background:currentColor}
.pill.online .dot{animation:pulse 2s infinite}
.pill .ms{color:var(--muted);font-weight:500}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(52,211,153,.5)}70%{box-shadow:0 0 0 5px rgba(52,211,153,0)}100%{box-shadow:0 0 0 0 rgba(52,211,153,0)}}
.title{font-size:var(--f4);font-weight:700;letter-spacing:-.01em;overflow-wrap:anywhere}
.aliaschip{font-size:var(--f1);font-weight:600;color:var(--accent);border:1px solid var(--line);border-radius:999px;padding:1px 8px;margin-left:6px;vertical-align:middle}
.aliaschip:hover{text-decoration:none;border-color:var(--accent)}
.label{color:var(--muted);font-size:var(--f3);margin:2px 0 10px}
.kv{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:var(--f2);color:var(--muted);margin-bottom:10px}
.kv b{color:var(--ink);font-weight:600;font-family:var(--mono)}
.metrics{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:var(--f2);color:var(--muted);margin:-4px 0 10px;font-family:var(--mono);
  overflow-wrap:anywhere}
.metrics>span{min-width:0}
.metrics b{color:var(--ink);font-weight:600}
.metrics b.warm{color:var(--warn)}
.metrics b.hot{color:var(--down)}
.upd{color:var(--warn);font-weight:700;font-size:var(--f1);line-height:1;font-family:var(--mono);white-space:nowrap;letter-spacing:.01em}
.updl{color:var(--muted);font-size:var(--f1);text-decoration:none;border-bottom:1px dotted var(--line)}
.engbusy{color:var(--warn);font-weight:600}
.engbusy[hidden]{display:none}
.actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:auto}
.open{border:1px solid transparent;background:var(--accent);color:var(--accent-ink);font-weight:700;padding:0 14px;
  transition:background .15s}
.open:hover{background:var(--accent2)}
.mini{border:1px solid var(--line);background:transparent;color:var(--muted);padding:0 10px;transition:all .15s}
.mini:hover{color:var(--ink);border-color:var(--line2);background:var(--panel2)}
.mini.del:hover{color:#fff;background:var(--down);border-color:var(--down)}
.mini svg{width:15px;height:15px;display:block}
.aliases{margin-top:12px;font-size:var(--f2);color:var(--muted)}
.aliases a{margin-right:12px}
.foot{color:var(--muted);font-size:var(--f2);margin-top:auto;padding-top:36px;text-align:center}
.empty{color:var(--muted);padding:24px;text-align:center}
.applybar{padding:10px 14px;border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--panel);
  font-size:var(--f3);font-weight:600;margin-bottom:14px;display:flex;gap:10px;align-items:center;line-height:1.4}
.applybar.run{border-color:var(--accent)}
.applybar.ok{border-color:var(--ok)}
.applybar.err{border-color:var(--down);color:var(--down)}
.applybar[hidden]{display:none}
.onboard{max-width:720px;margin:7vh auto 0;text-align:center;padding:8px 4px}
.ob-logo{display:inline-flex;align-items:center;justify-content:center;width:76px;height:76px;border-radius:20px;
  background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--line);box-shadow:var(--shadow)}
.onboard h2{font-size:26px;margin:20px 0 8px;letter-spacing:-.01em}
.ob-sub{color:var(--muted);font-size:var(--f4);line-height:1.55;margin:0 auto;max-width:520px}
.ob-steps{display:grid;gap:12px;margin:28px 0;text-align:left}
.ob-step{display:flex;gap:14px;align-items:flex-start;background:linear-gradient(180deg,var(--panel),var(--panel2));
  border:1px solid var(--line);border-radius:var(--radius);padding:14px 16px}
.ob-n{flex:0 0 28px;width:28px;height:28px;border-radius:999px;background:var(--accent);color:var(--accent-ink);
  font-weight:800;font-size:14px;display:flex;align-items:center;justify-content:center}
.ob-txt b{display:block;font-size:var(--f4);margin-bottom:3px}
.ob-txt span{color:var(--muted);font-size:var(--f3);line-height:1.5}
.ob-actions{display:flex;gap:10px;justify-content:center;align-items:center;flex-wrap:wrap}
.ob-docs{color:var(--muted);font-size:var(--f3)}
.ob-docs:hover{color:var(--accent)}
.ob-cmdbox{max-width:680px;margin:22px auto 20px;text-align:left}
.ob-cmdbox .joincmd{max-height:160px;margin-bottom:10px}
.ob-cmdactions{display:flex;gap:8px;justify-content:flex-end;margin-bottom:8px}
.obempty{color:var(--muted)}
.magic{margin-top:16px;padding-top:14px;border-top:1px solid var(--line)}
.magic-h{font-size:var(--f4);margin-bottom:4px}
.magic-h .spark{color:var(--accent)}
.sttbox{padding:9px 12px;border:1px solid var(--line);border-radius:var(--radius-sm);font-size:var(--f3);margin:2px 0 10px;line-height:1.45}
.sttbox.ok{border-color:var(--ok)}
.sttbox.warn{border-color:var(--warn)}
.sttbox.risk{border-color:var(--down);color:var(--down)}
.sttopt{display:flex;gap:8px;align-items:center;font-size:var(--f3);margin:2px 0 10px;cursor:pointer}
details.adv{margin-top:12px;border-top:1px dashed var(--line);padding-top:10px}
details.adv>summary{cursor:pointer;font-size:var(--f3);color:var(--muted);font-weight:600;list-style:none}
details.adv>summary:hover{color:var(--accent)}
details.adv[open]>summary{margin-bottom:10px}
.modal{position:fixed;inset:0;background:rgba(5,9,14,.65);display:flex;align-items:center;justify-content:center;z-index:50;padding:16px}
.modal[hidden]{display:none}
/* editing a node is a side panel, not a centred dialog: the fleet stays in view */
#modal{align-items:stretch;justify-content:flex-end;padding:0}
#modal .box{width:min(480px,100vw);height:100%;max-height:100vh;border-radius:0;border-top:0;border-bottom:0;border-right:0;
  box-shadow:-24px 0 48px -28px rgba(0,0,0,.85);animation:drawerin .16s ease-out}
@keyframes drawerin{from{transform:translateX(28px);opacity:.7}to{transform:none;opacity:1}}
.boxhead{display:flex;align-items:center;gap:10px;margin:0 0 14px}
.boxhead h3{margin:0;flex:1}
#fx{flex:0 0 auto}
@media (max-width:480px){#modal .box{width:100vw;border-left:0}}
.box{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:20px;width:min(600px,96vw);box-shadow:var(--shadow);max-height:92vh;overflow:auto}
.box h3{margin:0 0 12px;font-weight:700;font-size:var(--f5)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:0 12px}
@media (max-width:480px){.grid2{grid-template-columns:1fr}}
.row{display:flex;flex-direction:column;gap:4px;margin-bottom:9px}
.row label{font-size:var(--f2);color:var(--muted);font-weight:600}
.row input,.row select{height:var(--ctl);padding:0 10px;border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--panel2);color:var(--ink);font-size:var(--f3);width:100%}
.row input:focus,.row select:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(242,153,74,.15)}
.hint{font-size:var(--f2);color:var(--muted);margin:4px 0 10px;line-height:1.45}
.joincmd{background:var(--panel2);border:1px solid var(--line);border-radius:var(--radius-sm);padding:10px;font-family:var(--mono);
  font-size:var(--f2);line-height:1.45;white-space:pre-wrap;overflow-wrap:anywhere;color:var(--ink);max-height:120px;overflow:auto;margin:0 0 10px}
.keyline{display:flex;gap:8px;align-items:stretch;margin-bottom:10px}
.keycmd{flex:1;margin:0;max-height:52px;font-size:var(--f2);padding:8px}
.prov{margin-top:14px;padding-top:12px;border-top:1px solid var(--line)}
.prov .hint{margin-top:0}
.modalactions{display:flex;gap:8px;justify-content:flex-end}
.engnotes{max-height:46vh;overflow:auto;white-space:pre-wrap;word-break:break-word;font-family:var(--mono);font-size:var(--f2);color:var(--muted);background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:10px;margin:8px 0}
.toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:var(--panel);color:var(--ink);border:1px solid var(--line);
  padding:12px 20px;border-radius:var(--radius-sm);font-size:var(--f3);font-weight:600;z-index:60;box-shadow:var(--shadow)}
.totop{position:fixed;right:22px;bottom:22px;z-index:40;width:44px;height:44px;border-radius:50%;border:1px solid var(--line);
  background:var(--panel);color:var(--ink);box-shadow:var(--shadow);cursor:pointer;font-size:18px;line-height:1;
  display:grid;place-items:center;transition:border-color .15s,transform .1s}
.totop:hover{border-color:var(--accent);transform:translateY(-1px)}
.totop[hidden]{display:none}
@media (max-width:1240px){
  /* the rail needs ~236px; below this it becomes the familiar chip strip */
  .shell{display:block;padding:12px}
  .shell>.wrap{padding:0}
  .rail{position:static;flex-direction:row;flex-wrap:wrap;align-items:center;gap:6px;margin:0 0 12px}
  .rl-title{display:none}
  .rl-chips{flex-direction:row;flex-wrap:wrap;gap:6px}
  .rl-chips .chipf{width:auto;border-color:var(--line);background:var(--panel);color:var(--muted)}
  .rl-chips .chipf.active{background:var(--accent);color:var(--accent-ink);border-color:transparent}
  .rl-actions{flex-direction:row;gap:6px;margin:0}
  .rl-actions .seg{width:auto}
  .rl-meta{display:none}
}
@media (max-width:1360px){
  /* with the rail on screen the rows get less width: tighten the columns */
  .nrow{grid-template-columns:104px minmax(165px,1.8fr) minmax(150px,200px) minmax(120px,165px) 235px;gap:10px}
  .lhead{grid-template-columns:104px minmax(165px,1.8fr) minmax(150px,200px) minmax(120px,165px) 235px;gap:10px}
}
@media (max-width:720px){
  /* a five-row sticky header would eat a third of a phone screen: let it scroll away */
  .topbar{position:static}
  .topbar-in{padding:9px 12px;gap:8px}
  .brand .name{font-size:var(--f5)}
  .ctrls{gap:6px}
  .iconbtn2{padding:8px 10px;font-size:var(--f3)}
  .addbtn{padding:9px 13px;font-size:var(--f3)}
  .search{order:20;width:100%}
  .search input{width:100%;max-width:none;padding:9px 12px 9px 36px}
  .wrap{padding:12px 12px 40px}
  .filters{gap:6px;padding-bottom:8px}
  .chipf{padding:5px 11px;font-size:var(--f3)}
  .iconbtn2,.addbtn,.open,.mini,.chipf,.segbtn,.stat{height:36px}
  .row input,.row select,.hform input,.hform select,.hbtn{height:36px}
  .upd{height:22px}
  .stats{gap:6px;flex-wrap:nowrap;overflow-x:auto;padding-bottom:2px;scrollbar-width:none}
  .stats::-webkit-scrollbar{display:none}
  .stat{padding:6px 9px;font-size:var(--f2);flex:0 0 auto}
  .stat b{font-size:var(--f4)}
  .rows{border:0;background:none;gap:8px}
  .nrow{grid-template-columns:1fr auto;grid-template-areas:"pill acts" "main main" "load load" "eng eng";
    gap:8px 10px;padding:12px;border:1px solid var(--line);border-radius:var(--radius);background:var(--panel)}
  .nrow .pill{grid-area:pill}
  .lhead{display:none}
  .nrow .actions{grid-area:acts}
  .nrow .nmain{grid-area:main}
  .nrow .nload{grid-area:load;white-space:normal}
  .nrow .neng{grid-area:eng}
  .nrow .nsub,.nrow .ntitle{white-space:normal}
  .nrow .actions{gap:4px}
  .nrow .open{padding:0 10px}
  .card{padding:13px}
  .label{margin:2px 0 9px}
  .meta-line{margin-left:0}
}
@media (max-width:480px){
  .brand .sub{display:none}   /* the count lives in the “Все N” chip right below */
  .meta-line{display:none}    /* “updated 04:00” is the least useful line on a phone */
  /* the whole control row cannot fit 390px: keep the three actions + theme,
     drop the RU/EN toggle (a desktop preference, persisted per device) */
  #langtoggle{display:none}
}
"""

JS = """
(function(){
  var REFRESH=__REFRESH__*1000;
  var I18N={
    ru:{filter:"Поиск: имя, тег, status:… (клавиша /)",updated:"обновлено",autorefresh:"автообновление",
        envs:"окружений",s_online:"в сети",s_offline:"не в сети",s_engdown:"движок не отвечает",        s_engbusy:"движок занят",s_load:"под нагрузкой",
        s_total1:"узел",s_total2:"узла",s_total3:"узлов",
        s_update1:"обновление",s_update2:"обновления",s_update3:"обновлений",
        nores:"Ничего не найдено — измените фильтр.",v_problems:"Проблемы",v_cards:"Плитки",v_list:"Список",
        quick:"Быстрый доступ",pinlabel:"Закрепить в быстром доступе",show:"показать в списке",
        pinned:"закреплён — снять можно в карточке узла",places:"Места",board:"Переписка",
        sort_sev:"проблемы сначала",sort_name:"имя А→Я",sort_cpu:"cpu: больше сверху",sort_ram:"ram: больше сверху",
        h_status:"статус",h_node:"узел",h_load:"нагрузка",h_engine:"движок",h_actions:"действия",
        p_pin:"Закрепить",p_unpin:"Открепить",
        reset_filters:"Сбросить фильтры",p_theme:"Сменить тему",p_board:"Переписка с агентами",
        p_hint:"Узел или действие…",p_empty:"Ничего не найдено",p_pick:"выбрать",p_run:"выполнить",p_close:"закрыть",
        updbar:"Доступна пара",updbehind:"отстают",updall:"Обновить все",updwhat:"что нового",
        open:"Открыть",copyurl:"копировать URL",copyip:"копировать IP",copied:"скопировано",
        tags:"теги",online_for:"в сети",offline_for:"недоступен",os_up:"аптайм ОС",all:"Все",add:"Добавить",addtitle:"Добавить окружение",edittitle:"Изменить окружение",flabel:"Метка",flocation:"Место",
        ftags:"Теги (через запятую)",faliases:"Алиасы (через запятую)",fhint:"Сначала поднимите узел на машине (node-join.sh), затем введите его mesh-IP.",
        save:"Сохранить",cancel:"Отмена",delete:"Удалить",edit:"Изменить",delconfirm:"Удалить окружение",applying:"Применяю… страница обновится",empty:"Ничего не найдено",
        fname:"имя",fport:"порт",fengine:"движок",
        nosub:"подключите первую машину",noloc:"Без локации",engbusy:"движок занят",engdown:"движок не отвечает",more:"Ещё",recheck:"Проверить",rechecked:"обновлено",obtitle:"Подключите первую машину",
        obsub:"Скопируйте команду и выполните её на новой машине — она появится здесь сама, с живым статусом и метриками.",
        obs1:"Выполните одну команду на машине",obs1d:"Кнопка «Подключить машину» выдаст одну строку — она сама поставит агент и введёт машину в защищённую сеть.",
        obs2:"Зарегистрируйте машину в портале",obs2d:"В конце установки машина покажет свой mesh-IP — нажмите «Добавить» и вставьте его.",
        obs3:"Открывайте агента одним щелчком",obs3d:"CodeNomad или OpenCode прямо в браузере, откуда угодно.",
        objoinbtn:"Подключить машину",obaddman:"Добавить по mesh-IP",obdocs:"Как это работает →",
        bar_run:"идёт",bar_ok:"готово",bar_err:"ошибка",errssh:"нет SSH-доступа к машине — проще скопировать команду выше и выполнить её в консоли машины",
        join:"Пригласить",jointitle:"Подключить машину",joinhint:"Скопируйте команду и выполните её на новой машине — она появится здесь сама.",jgenerate:"Новая команда",jcopy:"Копировать",joinempty:"Сначала сгенерируйте приглашение",jwhere:"Linux/VM — вставьте в терминале. Proxmox LXC — на хосте pct enter <VMID>, затем вставьте.",advsum:"Дополнительно: пользователь и имя",obcopy:"Скопировать команду",
        provhint:"…или поднимите узел по SSH (машина достижима с хаба; root или passwordless-sudo; пароль можно оставить пустым — тогда используется ключ хаба):",provpass:"Пароль root",provbtn:"Подключить",provname:"Имя узла",magictitle:"Магия: подключить по SSH",magichint:"Хаб сам всё поставит и зарегистрирует, если у машины есть пароль root (обычные VPS/VM). Для Proxmox LXC — используйте команду выше.",magicbtn:"Подключить",sttcheck:"Проверить машину",sttinstall:"Установить голос (STT)",sttsafe:"рекомендуется",sttrisk:"на свой страх и риск (может тормозить машину)",sttneed:"сначала нажмите «Проверить машину»",sttchecking:"проверяю ресурсы",
        keyhint:"…или добавьте публичный ключ хаба на новую машину (authorized_keys, либо поле «SSH public key» при создании LXC/VM):",keycopy:"Копировать ключ"},
    en:{filter:"Search: name, tag, status:… (press /)",updated:"updated",autorefresh:"auto-refresh",
        envs:"environments",s_online:"online",s_offline:"offline",s_engdown:"engine down",
        s_engbusy:"engine busy",s_load:"under load",
        s_total1:"node",s_total2:"nodes",s_total3:"nodes",
        s_update1:"update",s_update2:"updates",s_update3:"updates",
        nores:"Nothing found — change the filter.",v_problems:"Problems",v_cards:"Tiles",v_list:"List",
        quick:"Quick access",pinlabel:"Pin to quick access",show:"show in the list",
        pinned:"pinned — unpin it in the node panel",places:"Places",board:"Board",
        sort_sev:"problems first",sort_name:"name A→Z",sort_cpu:"cpu: high first",sort_ram:"ram: high first",
        h_status:"status",h_node:"node",h_load:"load",h_engine:"engine",h_actions:"actions",
        p_pin:"Pin",p_unpin:"Unpin",
        reset_filters:"Reset filters",p_theme:"Toggle theme",p_board:"Agent board",
        p_hint:"Node or action…",p_empty:"Nothing found",p_pick:"select",p_run:"run",p_close:"close",
        updbar:"Pair available",updbehind:"behind",updall:"Update all",updwhat:"what's new",
        open:"Open",copyurl:"copy URL",copyip:"copy IP",copied:"copied",
        tags:"tags",online_for:"online for",offline_for:"down for",os_up:"os uptime",all:"All",add:"Add",addtitle:"Add environment",edittitle:"Edit environment",flabel:"Label",flocation:"Location",
        ftags:"Tags (comma-separated)",faliases:"Aliases (comma-separated)",fhint:"First onboard the machine (node-join.sh), then enter its mesh IP.",
        save:"Save",cancel:"Cancel",delete:"Delete",edit:"Edit",delconfirm:"Delete environment",applying:"Applying… page will refresh",empty:"Nothing found",
        fname:"name",fport:"port",fengine:"engine",
        nosub:"connect your first machine",noloc:"Other",engbusy:"engine busy",engdown:"engine down",more:"More",recheck:"Check",rechecked:"updated",obtitle:"Connect your first machine",
        obsub:"Copy the command and run it on the new machine — it will appear here by itself, with live status and metrics.",
        obs1:"Run one command on the machine",obs1d:"The “Connect a machine” button gives you one line — it installs the agent and joins the secure network for you.",
        obs2:"Register the machine in the portal",obs2d:"At the end the machine prints its mesh IP — click Add and paste it.",
        obs3:"Launch the agent in one click",obs3d:"CodeNomad or OpenCode right in your browser, from anywhere.",
        objoinbtn:"Connect a machine",obaddman:"Add by mesh IP",obdocs:"How it works →",
        bar_run:"in progress",bar_ok:"done",bar_err:"error",errssh:"no SSH access to the machine — easier to copy the command above and run it in the machine's console",
        join:"Invite",jointitle:"Join a machine",joinhint:"Copy the command and run it on the new machine — it will show up here by itself.",jgenerate:"New command",jcopy:"Copy",joinempty:"Generate an invite first",jwhere:"Linux/VM — paste it in a terminal. Proxmox LXC — on the host run pct enter <VMID>, then paste.",advsum:"Advanced: user and name",obcopy:"Copy command",
        provhint:"…or provision a node over SSH (reachable from the hub; root or passwordless-sudo; leave the password blank to use the hub key):",provpass:"root password",provbtn:"Connect",provname:"Node name",magictitle:"Magic: connect over SSH",magichint:"The hub installs and registers everything if the machine has a root password (typical VPS/VM). For a Proxmox LXC use the command above.",magicbtn:"Connect",sttcheck:"Check the machine",sttinstall:"Install voice (STT)",sttsafe:"recommended",sttrisk:"at your own risk (may slow the machine)",sttneed:"click “Check the machine” first",sttchecking:"checking resources",
        keyhint:"…or add the hub public key to the new machine (authorized_keys, or the «SSH public key» field when creating a LXC/VM):",keycopy:"Copy key"}
  };
  function cur(){return localStorage.getItem('cn_lang')||'ru';}
  function humanize(sec){sec=Math.max(0,sec|0);if(sec<60)return sec+'s';if(sec<3600)return Math.floor(sec/60)+'m';if(sec<86400)return Math.floor(sec/3600)+'h';return Math.floor(sec/86400)+'d';}
  var locFilter='all';
  var statFilter='';
  function apply(l){
    localStorage.setItem('cn_lang',l); document.documentElement.lang=l;
    document.querySelectorAll('[data-i18n]').forEach(function(el){var k=el.getAttribute('data-i18n'); if(I18N[l][k]!=null) el.textContent=I18N[l][k];});
    document.querySelectorAll('[data-i18n-ph]').forEach(function(el){var k=el.getAttribute('data-i18n-ph'); if(I18N[l][k]!=null) el.placeholder=I18N[l][k];});
    document.querySelectorAll('[data-i18n-title]').forEach(function(el){var k=el.getAttribute('data-i18n-title'); if(I18N[l][k]!=null) el.title=I18N[l][k];});
    var t=document.getElementById('langtoggle'); if(t) t.textContent=(l==='ru'?'EN':'RU');
    refreshStats();
  }
  function setTheme(t){document.documentElement.setAttribute('data-theme',t);localStorage.setItem('cn_theme',t);
    var b=document.getElementById('themebtn'); if(b) b.textContent=(t==='dark'?'\\u2600':'\\u263E');}
  function statOk(c){
    if(!statFilter) return true;
    if(statFilter==='problems') return c.getAttribute('data-state')==='offline'
      || c.getAttribute('data-eng')==='down' || c.getAttribute('data-eng')==='busy'
      || (c.getAttribute('data-load')||'0')!=='0' || c.getAttribute('data-behind')==='1';
    if(statFilter==='online') return c.getAttribute('data-state')==='online';
    if(statFilter==='offline') return c.getAttribute('data-state')==='offline';
    if(statFilter==='engdown') return c.getAttribute('data-eng')==='down';
    if(statFilter==='engbusy') return c.getAttribute('data-eng')==='busy';
    if(statFilter==='load') return (c.getAttribute('data-load')||'0')!=='0';
    if(statFilter==='update') return c.getAttribute('data-behind')==='1';
    return true;
  }
  function plural(n,one,few,many){
    if(cur()==='en') return n===1?one:many;
    n=Math.abs(n|0);
    if(n%10===1&&n%100!==11) return one;
    if(n%10>=2&&n%10<=4&&!(n%100>=12&&n%100<=14)) return few;
    return many;
  }
  /* Keep the summary honest as statuses change (the cards update every poll).
     Mirrors node_flags() in status.py — change both together. */
  function refreshStats(){
    var t={total:0,online:0,offline:0,engdown:0,engbusy:0,load:0,update:0};
    document.querySelectorAll('.node').forEach(function(c){
      var online=c.getAttribute('data-state')==='online';
      t.total++; if(online) t.online++; else t.offline++;
      if(online&&c.getAttribute('data-eng')==='down') t.engdown++;
      if(online&&c.getAttribute('data-eng')==='busy') t.engbusy++;
      if(online&&(c.getAttribute('data-load')||'0')!=='0') t.load++;
      if(c.getAttribute('data-behind')==='1') t.update++;
    });
    for(var k in t){
      var n=document.getElementById('s-'+k); if(!n) continue;
      n.textContent=t[k];
      var box=n.parentNode;
      if(box&&box.classList&&box.classList.contains('stat')){
        box.hidden=(k!=='total'&&k!=='online'&&t[k]===0);
        var lbl=box.querySelector('[data-plural]');
        if(lbl){
          var pr=lbl.getAttribute('data-plural');
          if(pr==='total') lbl.textContent=plural(t[k],I18N[cur()].s_total1,I18N[cur()].s_total2,I18N[cur()].s_total3);
          if(pr==='update') lbl.textContent=plural(t[k],I18N[cur()].s_update1,I18N[cur()].s_update2,I18N[cur()].s_update3);
        }
      }
    }
  }
  /* ---- quick access: pinned nodes + recently opened (browser-local) ---- */
  function lsArr(key){
    try{var v=JSON.parse(localStorage.getItem(key)||'[]');return Object.prototype.toString.call(v)==='[object Array]'?v:[];}
    catch(e){return [];}
  }
  function setLs(key,arr){try{localStorage.setItem(key,JSON.stringify(arr));}catch(e){}}
  function nodeEl(name){
    var out=null;
    document.querySelectorAll('.node').forEach(function(n){if(n.getAttribute('data-node')===name) out=n;});
    return out;
  }
  function buildQuick(){
    var q=document.getElementById('quick'); if(!q) return;
    var pins=lsArr('cn_pins'), rec=lsArr('cn_recent');
    var list=pins.concat(rec.filter(function(n){return pins.indexOf(n)<0;}))
                  .filter(function(n){return !!nodeEl(n);});
    if(!list.length){q.hidden=true;q.innerHTML='';return;}
    q.hidden=false;
    var html='<span class="qlabel">'+I18N[cur()].quick+'</span>';
    list.forEach(function(n){
      var el=nodeEl(n), on=el.getAttribute('data-state')==='online', pin=pins.indexOf(n)>=0;
      html+='<button class="qchip'+(pin?' pin':'')+'" data-q="'+n+'" title="'+
        (pin?I18N[cur()].pinned:I18N[cur()].show)+'"><span class="qdot '+(on?'ok':'bad')+'"></span>'+
        n+(pin?'<span class="qpin">&#x1F4CC;</span>':'')+'</button>';
    });
    q.innerHTML=html;
  }
  function syncQuickDots(){
    document.querySelectorAll('#quick .qchip').forEach(function(c){
      var el=nodeEl(c.getAttribute('data-q')); if(!el) return;
      var d=c.querySelector('.qdot'); if(d) d.className='qdot '+(el.getAttribute('data-state')==='online'?'ok':'bad');
    });
  }
  function showNode(name){
    var el=nodeEl(name); if(!el) return;
    if(el.style.display==='none'){
      locFilter='all'; statFilter=''; var q=document.getElementById('q'); if(q) q.value='';
      syncFilterUI(); filters();
    }
    el.scrollIntoView({block:'center',behavior:'smooth'});
    el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash');
    setTimeout(function(){el.classList.remove('flash');},1400);
  }
  /* ---- explicit ordering: the server order is “problems first” ---- */
  function sortDefDir(k){return k==='name'?1:-1;}
  function sortState(){
    var k=localStorage.getItem('cn_sort')||'sev';
    var d=parseInt(localStorage.getItem('cn_dir')||'0',10)||sortDefDir(k);
    if(k==='sev') d=-1;
    return {k:k,d:d};
  }
  function paintSort(){
    var st=sortState();
    document.querySelectorAll('.lh[data-sort]').forEach(function(b){
      var on=b.getAttribute('data-sort')===st.k;
      b.classList.toggle('on',on);
      var a=b.querySelector('.ar');
      if(a) a.textContent=on?(st.d>0?'\u2191':'\u2193'):'';
    });
  }
  function sortGroups(){
    var st=sortState();
    document.querySelectorAll('.groupwrap').forEach(function(g){
      var box=g.querySelector('.grid, .rows'); if(!box) return;
      var nodes=[].slice.call(box.querySelectorAll('.node'));
      if(nodes.length<2) return;
      nodes.sort(function(a,b){
        if(st.k==='sev') return (+a.getAttribute('data-ord')||0)-(+b.getAttribute('data-ord')||0);
        if(st.k==='name'){
          var x=(a.getAttribute('data-node')||'').toLowerCase();
          var y=(b.getAttribute('data-node')||'').toLowerCase();
          return (x<y?-1:x>y?1:0)*st.d;
        }
        var p=parseFloat(a.getAttribute('data-'+st.k))||0;
        var q2=parseFloat(b.getAttribute('data-'+st.k))||0;
        return (p-q2)*st.d;
      });
      nodes.forEach(function(n){box.appendChild(n);});
    });
    paintSort();
  }
  function setSort(k,d){
    try{ localStorage.setItem('cn_sort',k); localStorage.setItem('cn_dir',String(d)); }catch(e){}
    sortGroups();
  }
  function escHtml(s){
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }
  /* ---- command palette (Ctrl+K) ---- */
  var palSel=0, palItems=[];
  function palActions(){
    return [
      {t:I18N[cur()].v_problems,k:'problems'},
      {t:I18N[cur()].reset_filters,k:'reset'},
      {t:I18N[cur()].v_list,k:'view-list'},
      {t:I18N[cur()].v_cards,k:'view-cards'},
      {t:I18N[cur()].p_theme,k:'theme'},
      {t:I18N[cur()].add,k:'add'},
      {t:I18N[cur()].join,k:'join'},
      {t:I18N[cur()].p_board,k:'board'}
    ];
  }
  function palBuild(q){
    q=(q||'').trim().toLowerCase();
    var nodes=[];
    document.querySelectorAll('.node').forEach(function(n){
      nodes.push({t:n.getAttribute('data-node'),
        s:(n.getAttribute('data-label')||'')+' '+(n.getAttribute('data-tags')||''),
        k:'node', n:n.getAttribute('data-node'), on:n.getAttribute('data-state')==='online'});
    });
    var matched=nodes.filter(function(i){
      return !q || ((i.t||'')+' '+(i.s||'')).toLowerCase().indexOf(q)>=0;});
    var acts=palActions().filter(function(i){
      return !q || (i.t||'').toLowerCase().indexOf(q)>=0;});
    if(!q) return matched.slice(0,5).concat(acts).slice(0,13);
    var verbs=[];
    if(matched.length){
      var top=matched[0].n, pinned=lsArr('cn_pins').indexOf(top)>=0;
      verbs=[
        {t:I18N[cur()].open+' · '+top, k:'v-open', n:top},
        {t:I18N[cur()].recheck+' · '+top, k:'v-check', n:top},
        {t:(pinned?I18N[cur()].p_unpin:I18N[cur()].p_pin)+' · '+top, k:'v-pin', n:top},
        {t:I18N[cur()].edit+' · '+top, k:'v-edit', n:top}
      ];
    }
    return matched.slice(0,4).concat(verbs, acts).slice(0,14);
  }
  function palRender(){
    var box=document.getElementById('paletlist'); if(!box) return;
    if(!palItems.length){box.innerHTML='<div class="pempty">'+escHtml(I18N[cur()].p_empty)+'</div>';return;}
    box.innerHTML=palItems.map(function(i,ix){
      var dot=i.k==='node'?'<span class="pdot '+(i.on?'ok':'bad')+'"></span>':'';
      var meta=i.s?'<span class="pk">'+escHtml(i.s.slice(0,40))+'</span>':'';
      return '<div class="pi'+(ix===palSel?' sel':'')+'" data-ix="'+ix+'">'+dot+
        '<span>'+escHtml(i.t)+'</span>'+meta+'</div>';
    }).join('');
  }
  function palOpen(){
    var p=document.getElementById('palet'); if(!p) return;
    p.hidden=false; palSel=0;
    var q=document.getElementById('paletq');
    if(q){q.value='';}
    palItems=palBuild(''); palRender();
    if(q) q.focus();
  }
  function palClose(){var p=document.getElementById('palet'); if(p) p.hidden=true;}
  function palRun(i){
    if(!i) return;
    palClose();
    if(i.k==='node'){showNode(i.n);return;}
    if(i.k==='v-open'){
      var el=nodeEl(i.n), a=el?el.querySelector('.actions a.open'):null;
      if(a) window.open(a.getAttribute('href'),'_blank','noopener'); return;}
    if(i.k==='v-check'){
      fetch('check?name='+encodeURIComponent(i.n),{cache:'no-store'}).then(function(r){return r.json();})
        .then(function(s){applyOne(i.n,s);toast(I18N[cur()].rechecked);})
        .catch(function(){toast('error');}); return;}
    if(i.k==='v-pin'){
      var pins=lsArr('cn_pins'), ix=pins.indexOf(i.n);
      if(ix>=0) pins.splice(ix,1); else pins.push(i.n);
      setLs('cn_pins',pins); buildQuick(); return;}
    if(i.k==='v-edit'){
      var en=nodeEl(i.n), eb=en?en.querySelector('[data-edit]'):null;
      if(eb) eb.click(); return;}
    if(i.k==='problems'){var pb=document.getElementById('probtn'); if(pb) pb.click(); return;}
    if(i.k==='reset'){locFilter='all'; statFilter=''; var q=document.getElementById('q'); if(q) q.value='';
      syncFilterUI(); filters(); return;}
    if(i.k==='view-list'||i.k==='view-cards'){
      var v=(i.k==='view-list')?'list':'cards';
      try{document.cookie='cn_view='+v+'; path=/; max-age=31536000; SameSite=Lax';}catch(e){}
      location.href='?view='+v; return;}
    if(i.k==='theme'){var tb=document.getElementById('themebtn'); if(tb) tb.click(); return;}
    if(i.k==='add'){var ab=document.getElementById('addbtn'); if(ab) ab.click(); return;}
    if(i.k==='join'){var jb=document.getElementById('joinbtn'); if(jb) jb.click(); return;}
    if(i.k==='board'){location.href='/handoff'; return;}
  }
  function filters(){
    var v=(document.getElementById('q').value||'').toLowerCase().trim();
    var toks=v?v.split(/\\s+/):[];
    var shown=0;
    document.querySelectorAll('.node').forEach(function(c){
      var okText=toks.every(function(t){
        if(t==='status:online') return c.getAttribute('data-state')==='online';
        if(t==='status:offline') return c.getAttribute('data-state')==='offline';
        if(t==='status:busy') return c.getAttribute('data-eng')==='busy';
        if(t==='status:down') return c.getAttribute('data-eng')==='down';
        if(t==='status:update') return c.getAttribute('data-behind')==='1';
        if(t==='status:load') return (c.getAttribute('data-load')||'0')!=='0';
        if(t.indexOf('tag:')===0) return (c.getAttribute('data-tags')||'').toLowerCase()
          .split(',').map(function(x){return x.trim();}).indexOf(t.slice(4))>=0;
        if(t.indexOf('loc:')===0) return (c.getAttribute('data-location')||'').toLowerCase().indexOf(t.slice(4))>=0;
        return (c.getAttribute('data-search')||'').indexOf(t)>=0;
      });
      var okLoc=(locFilter==='all'||c.getAttribute('data-location')===locFilter);
      var vis=okText&&okLoc&&statOk(c);
      c.style.display=vis?'':'none'; if(vis) shown++;
    });
    document.querySelectorAll('.groupwrap').forEach(function(g){
      var any=Array.prototype.some.call(g.querySelectorAll('.node'),function(c){return c.style.display!=='none';});
      g.style.display=any?'':'none';
    });
    var nr=document.getElementById('nores');
    if(nr){ nr.hidden=shown>0; if(!shown) nr.textContent=I18N[cur()].nores; }
    // a group counter describes the whole group; while a filter is on it would
    // contradict the visible cards, so hide it (the stat row already says the count)
    var filtering=!!(v||statFilter);
    document.querySelectorAll('.gcnt').forEach(function(g){ g.hidden=filtering; });
    try{ sessionStorage.setItem('cn_filters',JSON.stringify(
      {loc:locFilter,stat:statFilter,q:(document.getElementById('q').value||'')})); }catch(e){}
  }
  function restoreFilters(){
    try{
      var f=JSON.parse(sessionStorage.getItem('cn_filters')||'{}');
      if(f.loc) locFilter=f.loc;
      if(f.stat) statFilter=f.stat;
      var q=document.getElementById('q');
      if(q&&f.q) q.value=f.q;
    }catch(e){}
    syncFilterUI();
  }
  function syncFilterUI(){
    document.querySelectorAll('.chipf[data-location]').forEach(function(x){
      x.classList.toggle('active',x.getAttribute('data-location')===locFilter);});
    document.querySelectorAll('.stat').forEach(function(x){
      x.classList.toggle('on',x.getAttribute('data-s')===statFilter);});
    var pb=document.getElementById('probtn');
    if(pb) pb.classList.toggle('on',statFilter==='problems');
  }
  function toast(msg){var t=document.createElement('div');t.className='toast';t.textContent=msg;document.body.appendChild(t);}
  function post(payload,after){
    fetch('api/env',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})
      .then(function(r){return r.json()}).then(function(){ if(after) after(); })
      .catch(function(){ toast('error'); });
  }
  function openModal(env){
    document.getElementById('f-name').value=env.name||'';
    document.getElementById('f-ip').value=env.ip||'';
    document.getElementById('f-port').value=env.port||9898;
    document.getElementById('f-label').value=env.label||'';
    document.getElementById('f-location').value=env.location||'';
    document.getElementById('f-tags').value=(env.tags||[]).join(', ');
    document.getElementById('f-aliases').value=(env.aliases||[]).join(', ');
    document.getElementById('f-engine').value=env.engine||'';
    var pin=document.getElementById('f-pin');
    if(pin){ pin.checked=lsArr('cn_pins').indexOf(env.name||'')>=0; pin.disabled=!env.name; }
    document.getElementById('modal').setAttribute('data-original',env.name||'');
    document.querySelector('#modal h3').textContent=(env.name?I18N[cur()].edittitle:I18N[cur()].addtitle);
    document.getElementById('modal').hidden=false;
  }
  function applyOne(n,s){
    var p=document.getElementById('st-'+n); if(!p) return;
    var eg=document.getElementById('eng-'+n);
    if(eg){
      eg.hidden=!s.engine;
      var el=eg.querySelector('[data-i18n]');
      if(el){ var ek=(s.engine==='down')?'engdown':'engbusy';
        el.setAttribute('data-i18n',ek); el.textContent=I18N[cur()][ek]; }
    }
    p.className='pill '+(s.status==='online'?'online':'offline');
    var t=p.querySelector('.txt'); if(t) t.textContent=s.status;
    var m=p.querySelector('.ms'); if(m) m.textContent=(s.status==='online'?(s.ms+' ms'):humanize(Date.now()/1000-(s.since||Date.now()/1000)));
    var up=document.getElementById('up-'+n); if(up&&s.since) up.textContent=humanize(Date.now()/1000-s.since);
    if(s.since) p.title=(I18N[cur()][s.status==='online'?'online_for':'offline_for'])+' '+humanize(Date.now()/1000-s.since);
    var mc=document.getElementById('mc-'+n); if(mc&&s.cpu!=null){mc.textContent=s.cpu+'%';mc.className=s.cpu>=90?'hot':(s.cpu>=75?'warm':'');}
    var mm=document.getElementById('mm-'+n); if(mm&&s.mem!=null){mm.textContent=s.mem+'%';mm.className=s.mem>=90?'hot':(s.mem>=75?'warm':'');}
    var mt=document.getElementById('mt-'+n); if(mt&&s.uptime!=null) mt.textContent=humanize(s.uptime);
    var card=p.closest('.node');
    if(card){
      card.setAttribute('data-state',s.status==='online'?'online':'offline');
      card.setAttribute('data-eng',s.engine||'');
      card.setAttribute('data-cpu',s.cpu!=null?s.cpu:'');
      card.setAttribute('data-mem',s.mem!=null?s.mem:'');
      var hot=(s.cpu!=null&&s.cpu>=90)||(s.mem!=null&&s.mem>=90);
      var warm=(s.cpu!=null&&s.cpu>=75)||(s.mem!=null&&s.mem>=75);
      card.setAttribute('data-load',hot?'2':(warm?'1':'0'));
    }
  }
  function upd(d){
    var known=Object.keys(d.envs||{}).length;
    var cards=document.querySelectorAll('.node').length;
    var onboarding=!!document.getElementById('onboardwrap');
    if((onboarding&&known>0)||(!onboarding&&known!==cards)){location.reload();return;}
    var ab=document.getElementById('applybar');
    if(ab){var ap=d.apply||{};var as=ap.status||'';
      var fin=ap.finished||0;var age=fin?(Date.now()/1000-fin):0;
      var aact=ap.action||'';
      ab.setAttribute('data-fin',String(fin));
      if(aact==='stt-check'){ab.hidden=true;}
      else if(fin&&localStorage.getItem('cn_apply_ack')===String(fin)){ab.hidden=true;}
      else if(as==='running'){ab.hidden=false;ab.className='applybar run';ab.textContent='\u23f3 '+(ap.name||'')+' \u2014 '+(ap.message||I18N[cur()].bar_run)+' \u00b7 '+humanize(Date.now()/1000-(ap.started||Date.now()/1000));}
      else if(as==='error'&&age<600){ab.hidden=false;ab.className='applybar err';var m=ap.message||I18N[cur()].bar_err;if(/denied|\u043e\u0442\u043a\u0430\u0437/i.test(m))m=m+' \u2014 '+I18N[cur()].errssh;ab.textContent='\u26a0 '+(ap.name?ap.name+': ':'')+m+'  (\u00d7)';}
      else if(as==='ok'&&age<180){ab.hidden=false;ab.className='applybar ok';ab.textContent='\u2713 '+(ap.name||'')+' \u2014 '+I18N[cur()].bar_ok;}
      else{ab.hidden=true;}
      if(aact==='stt-check'&&fin&&age<300){var rb=document.getElementById('sttresult');
        if(rb){rb.hidden=false;var safe=ap.stt_safe===true;rb.className='sttbox '+(safe?'ok':'risk');
          rb.textContent=(safe?'\u2713 ':'\u26a0 ')+(ap.stt_model||'')+' \u2014 '+(ap.stt_verdict||'')+(safe?'':'. '+I18N[cur()].sttrisk);
          var cb=document.getElementById('p-stt');if(cb){cb.disabled=false;if(safe)cb.checked=true;}}}
    }
    var el=document.getElementById('utime');
    if(el) el.textContent=new Date((d.ts||Date.now()/1000)*1000).toLocaleTimeString();
    for(var n in d.envs){ applyOne(n,d.envs[n]); }
    refreshStats();
    syncQuickDots();
  }
  function poll(){fetch('status.json',{cache:'no-store'}).then(function(r){return r.json()}).then(upd).catch(function(){});}
  document.addEventListener('input',function(e){ if(e.target&&e.target.id==='q') filters(); });
  document.addEventListener('change',function(e){
    if(e.target&&e.target.id==='f-pin'){
      var name=(document.getElementById('modal').getAttribute('data-original')||'');
      if(!name) return;
      var a=lsArr('cn_pins');
      if(e.target.checked){ if(a.indexOf(name)<0) a.push(name); }
      else { a=a.filter(function(x){return x!==name;}); }
      setLs('cn_pins',a); buildQuick();
    }
  });
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape'){
      var pl=document.getElementById('palet'); if(pl&&!pl.hidden){pl.hidden=true;return;}
      ['modal','engmodal','joinmodal'].forEach(function(id){
        var m=document.getElementById(id); if(m) m.hidden=true;});
      return; }
    if((e.ctrlKey||e.metaKey)&&(e.key==='k'||e.key==='K')){e.preventDefault();palOpen();return;}
    var tag=(document.activeElement&&document.activeElement.tagName)||'';
    if(e.key==='/'&&tag!=='INPUT'&&tag!=='TEXTAREA'){e.preventDefault();
      var q=document.getElementById('q'); if(q) q.focus(); return;}
    if(tag==='INPUT'||tag==='TEXTAREA'||e.ctrlKey||e.metaKey||e.altKey) return;
    if(e.key==='p'){var pb=document.getElementById('probtn'); if(pb){pb.click();e.preventDefault();} return;}
    if(e.key==='v'){var o=document.querySelector('.segbtn:not(.on)'); if(o){o.click();e.preventDefault();} return;}
    if(e.key==='j'||e.key==='k'){
      var ns=[].slice.call(document.querySelectorAll('.node')).filter(function(n){return n.style.display!=='none';});
      if(!ns.length) return;
      var i=ns.indexOf(document.activeElement);
      i=i<0?(e.key==='j'?0:ns.length-1):Math.max(0,Math.min(ns.length-1,i+(e.key==='j'?1:-1)));
      ns[i].focus(); ns[i].scrollIntoView({block:'nearest'}); e.preventDefault(); return;
    }
    if(e.key==='Enter'){
      var a=document.activeElement&&document.activeElement.querySelector('.actions a.open');
      if(a){ window.open(a.getAttribute('href'),'_blank','noopener'); e.preventDefault(); }
    }
  });
  document.addEventListener('click',function(e){
    var gh=e.target.closest('h2.group'); if(gh){ var grid=gh.parentNode.querySelector('.grid, .rows');
      if(grid){ grid.classList.toggle('collapsed'); gh.classList.toggle('collapsed'); } return; }
    var ck=e.target.closest('[data-check]');
    if(ck){var nm=ck.getAttribute('data-check');ck.disabled=true;
      fetch('check?name='+encodeURIComponent(nm),{cache:'no-store'}).then(function(r){return r.json()})
        .then(function(s){applyOne(nm,s);toast(I18N[cur()].rechecked);})
        .catch(function(){toast('error');}).then(function(){ck.disabled=false;});return;}
    var cf=e.target.closest('.chipf'); if(cf&&cf.hasAttribute('data-location')){ locFilter=cf.getAttribute('data-location');
      document.querySelectorAll('.chipf').forEach(function(x){x.classList.toggle('active',x===cf);}); filters(); return; }
    var sb=e.target.closest('.stat[data-s]');
    if(sb){ var sk=sb.getAttribute('data-s');
      if(sk==='total'){ statFilter=''; }
      else { statFilter=(statFilter===sk?'':sk); }
      document.querySelectorAll('.stat').forEach(function(x){
        x.classList.toggle('on', x.getAttribute('data-s')===statFilter); });
      var pbtn=document.getElementById('probtn'); if(pbtn) pbtn.classList.remove('on');
      filters(); return; }
    var pbtn2=e.target.closest('#probtn');
    if(pbtn2){ statFilter=(statFilter==='problems'?'':'problems');
      document.querySelectorAll('.stat').forEach(function(x){x.classList.remove('on');});
      pbtn2.classList.toggle('on',statFilter==='problems'); filters(); return; }
    var vb=e.target.closest('.segbtn');
    if(vb){ try{ document.cookie='cn_view='+vb.getAttribute('data-view')+'; path=/; max-age=31536000; SameSite=Lax'; }catch(err){} return; }
    var b=e.target.closest('[data-copy]');
    if(b){navigator.clipboard.writeText(b.getAttribute('data-copy')).then(function(){toast(I18N[cur()].copied);}); return;}
    var qc=e.target.closest('.qchip');
    if(qc){ showNode(qc.getAttribute('data-q')); return; }
    var pci=e.target.closest('.pi');
    if(pci){ palRun(palItems[+pci.getAttribute('data-ix')]); return; }
    if(e.target.id==='palet'){ palClose(); return; }
    var hb=e.target.closest('.lh[data-sort]');
    if(hb){ var hk=hb.getAttribute('data-sort'), hs=sortState();
      setSort(hk, hs.k===hk ? -hs.d : sortDefDir(hk)); return; }
    var op=e.target.closest('.actions a.open');
    if(op){ var nd=op.closest('.node');
      if(nd){ var nm=nd.getAttribute('data-node');
        var r=lsArr('cn_recent').filter(function(x){return x!==nm;});
        r.unshift(nm); setLs('cn_recent',r.slice(0,5)); } }
    var t=e.target.closest('#langtoggle'); if(t){apply(cur()==='ru'?'en':'ru'); return;}
    var th=e.target.closest('#themebtn'); if(th){var c=document.documentElement.getAttribute('data-theme');setTheme(c==='dark'?'light':'dark');return;}
    var tt=e.target.closest('#totop'); if(tt){window.scrollTo({top:0,behavior:'smooth'});return;}
    var ad=e.target.closest('#addbtn'); if(ad){openModal({});return;}
    var abx=e.target.closest('#applybar'); if(abx&&!abx.hidden){localStorage.setItem('cn_apply_ack',abx.getAttribute('data-fin')||'');abx.hidden=true;return;}
    var oba=e.target.closest('#obadd'); if(oba){openModal({});return;}
    var obg=e.target.closest('#obgen'); if(obg){var os=!!(document.getElementById('j-stt')&&document.getElementById('j-stt').checked);post({action:'invite',stt:os},function(){toast(I18N[cur()].applying);setTimeout(function(){location.reload();},7000);});return;}
    var eu=e.target.closest('[data-engup]');
    if(eu){var pp=eu.getAttribute('data-engup').split('|');
      document.getElementById('engtitle').textContent='Обновить движок до codenomad '+pp[0]+' / opencode '+pp[1];
      document.getElementById('engversion').value=pp[0]+'|'+pp[1];
      var nb=document.getElementById('engnotes'); nb.textContent='загружаю заметки о релизе…';
      document.getElementById('engmodal').hidden=false;
      fetch('changelog',{cache:'no-store'}).then(function(r){return r.json()}).then(function(d){
        nb.textContent=(d&&d.notes)?d.notes:'(заметок о релизе нет)';
      }).catch(function(){nb.textContent='(не удалось загрузить)';});
      return;}
    var eg=e.target.closest('#enggo');
    if(eg){var ev=(document.getElementById('engversion').value||'').split('|');
      if(ev[0]){
        fetch('api/engine',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({codenomad:ev[0],opencode:ev[1]})})
          .then(function(r){return r.json()}).then(function(){toast('обновление запущено — узлы подтянут за \u2264 30 мин');})
          .catch(function(){toast('error');});}
      document.getElementById('engmodal').hidden=true; return;}
    var ec=e.target.closest('#engclose'); if(ec){document.getElementById('engmodal').hidden=true;return;}
    var obc=e.target.closest('#obcopy'); if(obc){var c=(document.getElementById('obcmd').textContent||'').trim();if(c.indexOf('curl')<0){toast(I18N[cur()].joinempty);return;}navigator.clipboard.writeText(c).then(function(){toast(I18N[cur()].copied);});return;}
    var jb=e.target.closest('#joinbtn'); if(jb){document.getElementById('joinmodal').hidden=false;return;}
    var obi=e.target.closest('#objoin'); if(obi){document.getElementById('joinmodal').hidden=false;return;}
    var jc=e.target.closest('#jclose'); if(jc){document.getElementById('joinmodal').hidden=true;return;}
    var jg=e.target.closest('#jgen'); if(jg){var js=!!(document.getElementById('j-stt')&&document.getElementById('j-stt').checked);post({action:'invite',stt:js},function(){toast(I18N[cur()].applying);setTimeout(function(){location.reload();},7000);});return;}
    var jcp=e.target.closest('#jcopy'); if(jcp){var t=(document.getElementById('joincmd').textContent||'').trim();if(!t){toast(I18N[cur()].joinempty);return;}navigator.clipboard.writeText(t).then(function(){toast(I18N[cur()].copied);});return;}
    var kc=e.target.closest('#keycopy'); if(kc){var k=(document.getElementById('hubkey').textContent||'').trim();navigator.clipboard.writeText(k).then(function(){toast(I18N[cur()].copied);});return;}
    var chk=e.target.closest('#pcheck'); if(chk){var ch=(document.getElementById('p-host').value||'').trim();var cu=(document.getElementById('p-user').value||'root').trim();var cpw=document.getElementById('p-pass').value||'';if(!ch){alert('host required');return;}var rb=document.getElementById('sttresult');rb.hidden=false;rb.className='sttbox';rb.textContent=I18N[cur()].sttchecking+'\u2026';post({action:'stt-check',host:ch,user:cu,password:cpw},function(){});return;}
    var pp=e.target.closest('#pprov'); if(pp){var ph=(document.getElementById('p-host').value||'').trim();var pu=(document.getElementById('p-user').value||'').trim();var pw=document.getElementById('p-pass').value||'';var pn=(document.getElementById('p-name').value||'').trim();var pe=document.getElementById('p-engine').value||'';var pstt=!!(document.getElementById('p-stt')&&document.getElementById('p-stt').checked);if(!ph||!pu){alert('host & user required');return;}post({action:'provision',host:ph,user:pu,password:pw,name:pn,engine:pe,stt:pstt},function(){toast(I18N[cur()].applying);});return;}
    var ed=e.target.closest('[data-edit]'); if(ed){ var c=ed.closest('.node');
      openModal({name:c.getAttribute('data-name'),ip:c.getAttribute('data-ip'),port:c.getAttribute('data-port'),
        label:c.getAttribute('data-label'),location:c.getAttribute('data-location'),engine:c.getAttribute('data-engine'),
        tags:(c.getAttribute('data-tags')||'').split(',').map(function(s){return s.trim();}).filter(Boolean),
        aliases:(c.getAttribute('data-aliases')||'').split(',').map(function(s){return s.trim();}).filter(Boolean)}); return;}
    var cx=e.target.closest('#fcancel'); if(cx){document.getElementById('modal').hidden=true;return;}
    var fx=e.target.closest('#fx'); if(fx){document.getElementById('modal').hidden=true;return;}
    if(e.target.id==='modal'||e.target.id==='joinmodal'||e.target.id==='engmodal'){ e.target.hidden=true; return; }
    var sv=e.target.closest('#fsave'); if(sv){
      var v=function(id){return (document.getElementById(id).value||'').trim();};
      var env={name:v('f-name'),ip:v('f-ip'),port:parseInt(v('f-port')||'9898',10)||9898,
        label:v('f-label'),location:v('f-location'),engine:v('f-engine'),
        tags:v('f-tags').split(',').map(function(s){return s.trim();}).filter(Boolean),
        aliases:v('f-aliases').split(',').map(function(s){return s.trim();}).filter(Boolean)};
      if(!env.name||!env.ip){alert('name & mesh IP required');return;}
      var orig=document.getElementById('modal').getAttribute('data-original')||'';
      post({action:'add',env:env,original_name:orig},function(){ toast(I18N[cur()].applying); setTimeout(function(){location.reload();},9000); });
      return;}
    var del=e.target.closest('[data-del]'); if(del){
      if(confirm(I18N[cur()].delconfirm+' '+del.getAttribute('data-del')+'?')){
        post({action:'delete',name:del.getAttribute('data-del')},function(){ toast(I18N[cur()].applying); setTimeout(function(){location.reload();},9000); });}
      return;}
  });
  document.addEventListener('keydown',function(e){
    if(e.key==='/'&&document.activeElement&&document.activeElement.id!=='q'){e.preventDefault();document.getElementById('q').focus();}
    if(e.key==='Escape'){['modal','joinmodal','engmodal'].forEach(function(id){var m=document.getElementById(id); if(m) m.hidden=true;});}
  });
  window.addEventListener('scroll',function(){var b=document.getElementById('totop'); if(b) b.hidden=window.scrollY<400;});
  (function(){var oc=document.getElementById('obcmd');
    if(oc&&(oc.textContent||'').indexOf('curl')<0&&!sessionStorage.getItem('cn_invite')){
      sessionStorage.setItem('cn_invite','1'); post({action:'invite'},function(){});
      setTimeout(function(){location.reload();},6000);}})();
  apply(cur()); setTheme(localStorage.getItem('cn_theme')||'dark'); restoreFilters(); filters(); refreshStats(); buildQuick(); sortGroups();
  (function(){
    var q=document.getElementById('paletq');
    if(q){
      q.addEventListener('input',function(){palSel=0;palItems=palBuild(q.value);palRender();});
      q.addEventListener('keydown',function(e){
        if(e.key==='ArrowDown'){e.preventDefault();palSel=Math.min(palItems.length-1,palSel+1);palRender();}
        else if(e.key==='ArrowUp'){e.preventDefault();palSel=Math.max(0,palSel-1);palRender();}
        else if(e.key==='Enter'){e.preventDefault();palRun(palItems[palSel]);}
        else if(e.key==='Escape'){e.preventDefault();palClose();}
      });
    }
  })();
  setInterval(poll,REFRESH); poll();
})();
"""

# ---------------------------------------------------------------------------
# Handoff board — a shared "mailbox" for the agents and the admin. Agents post
# and read it over the mesh (http://100.64.0.1:8090/handoff); humans view it at
# https://hub.<domain>/handoff (behind SSO). Append-only JSONL, no secrets.
# ---------------------------------------------------------------------------
HANDOFF_TOPICS = ("ask", "handoff", "done", "warn", "note")
# Board participants. The *public* default is the generic trio; a hub can extend it
# with its own agents via HANDOFF_ACTORS=dev,admin,user,<agent>,… — so private agent
# names never have to live in the published code.
HANDOFF_ACTORS = tuple(
    a.strip() for a in os.environ.get("HANDOFF_ACTORS", "dev,admin,user").split(",") if a.strip()
)


def handoff_targets(value):
    """Normalise a `to` field into a NON-EMPTY list of actors.

    Accepts a string ("admin", "dev,admin") and a JSON list (["admin"]), so both
    the board form and API/waker callers work. An unknown recipient raises: a
    message that silently lands in the wrong audience (we shipped that once — a
    list fell through to "all") is worse than one refused with a clear error.
    Omitted/empty -> everyone.
    """
    items = value if isinstance(value, (list, tuple, set)) else [value]
    parts = []
    for item in items:
        if item is None:
            continue
        for chunk in str(item).replace(";", ",").replace("\n", ",").split(","):
            parts.extend(chunk.split())
    parts = [p.lower() for p in parts]
    if not parts:
        return ["all"]
    bad = sorted({p for p in parts if p not in HANDOFF_ACTORS and p != "all"})
    if bad:
        raise ValueError(f"unknown recipient(s): {', '.join(bad)} "
                         f"(allowed: all, {', '.join(HANDOFF_ACTORS)})")
    out = []
    for p in parts:
        if p not in out:
            out.append(p)
    return ["all"] if "all" in out else out


def handoff_audience(to):
    """Human-readable name of a normalised `to` list (for the UI and pings)."""
    to = to or ["all"]
    if "all" in to:
        return "всем"
    return ", ".join("вам" if a == "user" else a for a in to)
HANDOFF_TOPIC_RU = {"ask": "вопрос", "handoff": "передача", "done": "готово",
                    "warn": "важно", "note": "заметка"}
HANDOFF_EXTRA_CSS = """
.hm{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--line2);
  border-radius:var(--radius);padding:12px 14px;margin:10px 0}
.hm.warn{border-left-color:var(--down)}
.hm.ask{border-left-color:var(--accent)}
.hm.done{border-left-color:var(--ok)}
.hmeta{display:flex;gap:10px;align-items:baseline;font-size:var(--f2);color:var(--muted);margin-bottom:6px;flex-wrap:wrap}
.hmeta b{color:var(--ink);font-size:var(--f3)}
.htag{background:var(--panel2);border:1px solid var(--line2);border-radius:999px;padding:1px 8px}
.hmeta time{margin-left:auto;font-family:var(--mono)}
.htext{line-height:1.55;overflow-wrap:anywhere}
.hform{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:14px;margin-bottom:8px}
.hform .row{display:flex;flex-direction:row;gap:8px;margin-bottom:10px;flex-wrap:wrap;align-items:center}
.hform .row input,.hform .row select{width:auto}
.hform input,.hform select,.hform textarea{background:var(--panel2);color:var(--ink);
  border:1px solid var(--line2);border-radius:var(--radius-sm);padding:9px 10px;font:inherit}
.hform input,.hform select{height:var(--ctl);padding:0 10px}
.hform textarea{width:100%;min-height:76px;resize:vertical}
.hempty,.hnote{color:var(--muted)}
.hnote{font-size:var(--f2);margin:4px 2px 0}
.hcount{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--line2);
  border-radius:var(--radius);padding:9px 14px;margin:0 0 12px;color:var(--muted);
  display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.hcount b{color:var(--ink)}
.hcount.hot{border-left-color:var(--accent);color:var(--ink)}
.hbtn{background:var(--accent);color:#101418;border:0;border-radius:var(--radius-sm);height:var(--ctl);
  padding:0 12px;font:inherit;font-weight:600;cursor:pointer;margin-left:auto;display:inline-flex;align-items:center}
.hbtn[disabled]{opacity:.55;cursor:default}
.hstate{border-radius:999px;padding:1px 9px;font-size:var(--f2);border:1px solid var(--line2);white-space:nowrap}
.hstate.new{background:var(--accent);border-color:var(--accent);color:#101418;font-weight:700}
.hstate.read{color:var(--muted)}
.hto{background:var(--panel2);border:1px solid var(--accent);color:var(--accent);
  border-radius:999px;padding:1px 8px}
.hown{opacity:.85}
"""
HANDOFF_SCRIPT = """
(function(){
  document.documentElement.setAttribute('data-theme', localStorage.getItem('cn_theme')||'dark');
  function send(){
    var from=(document.getElementById('hf-from').value||'user').trim();
    var topic=document.getElementById('hf-topic').value;
    var to=document.getElementById('hf-to').value;
    var text=document.getElementById('hf-text').value.trim();
    if(!text) return;
    fetch('/handoff',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({from:from,topic:topic,to:to,text:text})})
      .then(function(r){return r.json();}).then(function(){location.reload();});
  }
  document.getElementById('hf-send').addEventListener('click',send);
  document.getElementById('hf-text').addEventListener('keydown',function(e){
    if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)) send();
  });
  var ab=document.getElementById('hf-ack');
  if(ab) ab.addEventListener('click',function(){
    ab.disabled=true;
    fetch('/handoff/ack',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({as:'user'})}).then(function(){location.reload();});
  });
})();
"""


def handoff_load(limit=200):
    out = []
    try:
        with open(HANDOFF_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    m = json.loads(line)
                except ValueError:
                    continue
                ts = m.get("ts")
                if isinstance(ts, (int, float)):
                    # Render in the hub's *current* timezone, so old entries follow a
                    # timezone change (the stored `at` is just a fallback for readers).
                    m["at"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
                out.append(m)
    except OSError:
        pass
    return out[-limit:]


def handoff_ping_reason(entry):
    """Why the human's Telegram should (not) buzz for this entry.

    Telegram is the human's phone, so it only rings for mail that concerns him:
    addressed to `user` (or `all`, which includes him) or marked `warn`. Agent
    mail (`dev` <-> `admin`) stays on the board — the wakers read it and the
    counters show it; pinging the human for every note is just noise. Returns
    one of: ping | muted | agents-only | off.
    """
    if not (HANDOFF_NOTIFY and entry.get("from") != "user"):
        return "off"
    targets = entry.get("to") or ["all"]
    if entry.get("topic") != "warn" and not ({"user", "all"} & set(targets)):
        return "agents-only"
    if entry.get("topic") != "warn" and time.time() < handoff_mute_until():
        return "muted"
    return "ping"


def handoff_add(frm, topic, text, to="", owner=""):
    topic = (topic or "note").strip().lower()
    if topic and topic not in HANDOFF_TOPICS:
        raise ValueError(f"unknown topic: {topic} (allowed: {', '.join(HANDOFF_TOPICS)})")
    topic = topic or "note"
    text = (text or "").strip()
    if not text:
        raise ValueError("empty message")
    targets = handoff_targets(to)
    author = (frm or "anon").strip()[:32]
    entry = {"ts": time.time(),
             "at": time.strftime("%Y-%m-%d %H:%M", time.localtime()),
             "from": author,
             "to": targets,
             "owner": (owner or "").strip().lower() if (owner or "").strip().lower() in HANDOFF_ACTORS else author,
             "topic": topic,
             "text": text[:8000]}
    d = os.path.dirname(HANDOFF_FILE)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(HANDOFF_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + chr(10))
    with contextlib.suppress(OSError):
        os.chmod(HANDOFF_FILE, 0o600)
    reason = handoff_ping_reason(entry)
    aud = handoff_audience(targets)
    if reason != "off":
        # ASCII only: this line is printed on Windows dev boxes too (cp1251 console)
        print(f"[board] {author} -> {aud} | {topic}: {reason}", flush=True)
    if reason == "ping":
        tag = HANDOFF_TOPIC_RU.get(entry["topic"], entry["topic"])
        head = (f"🔔 ВАЖНО · от {author}" if entry["topic"] == "warn"
                else f"📬 {author} · {tag}")
        try:
            dom = load_data().get("domain", "")
        except Exception:
            dom = ""
        lower = [{"text": "🔕 не беспокоить 2 ч", "callback_data": "mute"}]
        if dom:
            lower.append({"text": "📖 открыть доску", "url": f"https://hub.{dom}/handoff"})
        kb = [[{"text": "✅ передал dev", "callback_data": "ack:dev"},
               {"text": "✅ передал admin", "callback_data": "ack:admin"}],
              [{"text": "✅ прочитал сам", "callback_data": "ack:user"}, *lower]]
        threading.Thread(target=notify, daemon=True, args=(
            f"{head} → {aud}\n{entry['text'][:300]}", kb)).start()
    return entry


def _seen_raw():
    try:
        with open(HANDOFF_SEEN_FILE, encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def _seen_write(d):
    p = os.path.dirname(HANDOFF_SEEN_FILE)
    if p:
        os.makedirs(p, exist_ok=True)
    with open(HANDOFF_SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f)
    with contextlib.suppress(OSError):
        os.chmod(HANDOFF_SEEN_FILE, 0o600)


def handoff_seen():
    """Last-seen timestamp per actor (who has read the board up to when)."""
    d = _seen_raw()
    return {a: float(d.get(a, 0) or 0) for a in HANDOFF_ACTORS}


def handoff_mute_until():
    """Board pings are silenced for entries up to this timestamp."""
    return float(_seen_raw().get("mute", 0) or 0)


def handoff_mute(hours=2):
    """Silence board pings for the next `hours` (a `warn` still gets through)."""
    d = _seen_raw()
    d["mute"] = time.time() + float(hours) * 3600
    _seen_write(d)
    return d["mute"]


def handoff_unread(actor="dev", msgs=None):
    """(new since the actor's marker, of those from others, of those addressed to
    the actor)."""
    msgs = handoff_load(500) if msgs is None else msgs
    since = handoff_seen().get(actor, 0.0)
    new = [m for m in msgs if float(m.get("ts") or 0) > since]
    others = sum(1 for m in new if m.get("from") != actor)
    addressed = sum(1 for m in new
                    if actor in (m.get("to") or ["all"]) or "all" in (m.get("to") or ["all"]))
    return len(new), others, addressed


def handoff_ack(actor="dev", upto=None):
    """Advance an actor's marker (default: up to the newest entry)."""
    if actor not in HANDOFF_ACTORS:
        raise ValueError(f"unknown actor: {actor} (allowed: {', '.join(HANDOFF_ACTORS)})")
    if upto is None:
        upto = max((float(m.get("ts") or 0) for m in handoff_load(500)), default=time.time())
    d = _seen_raw()
    d[actor] = float(upto)
    _seen_write(d)
    return d[actor]


def _tg_api(method, payload):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TG_TOKEN}/{method}",
        data=urllib.parse.urlencode(payload).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read() or b"{}")


def tg_poll_loop():
    """Long-poll Telegram so the board buttons work (ack / mute)."""
    if not (TG_TOKEN and TG_CHAT):
        return
    offset = None
    try:
        with open(TG_OFFSET_FILE, encoding="utf-8") as f:
            offset = (json.load(f) or {}).get("offset")
    except (OSError, ValueError):
        pass
    while True:
        try:
            q = {"timeout": 25, "allowed_updates": json.dumps(["callback_query"])}
            if offset is not None:
                q["offset"] = offset
            url = (f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates?"
                   + urllib.parse.urlencode(q))
            with urllib.request.urlopen(url, timeout=35) as r:
                data = json.loads(r.read() or b"{}")
            if not data.get("ok"):
                time.sleep(5)
                continue
            for upd in data.get("result", []):
                offset = int(upd.get("update_id", 0)) + 1
                with contextlib.suppress(OSError), open(TG_OFFSET_FILE, "w", encoding="utf-8") as f:
                    json.dump({"offset": offset}, f)
                cq = upd.get("callback_query")
                if not cq:
                    continue
                chat = str(((cq.get("message") or {}).get("chat") or {}).get("id", ""))
                if chat != str(TG_CHAT):
                    continue
                val = str(cq.get("data", ""))
                if val.startswith("ack:"):
                    who = val.split(":", 1)[1]
                    if who in HANDOFF_ACTORS:
                        handoff_ack(who)
                        note = "✅ отмечено: " + {"user": "вы прочитали",
                                                 "dev": "dev", "admin": "admin"}.get(who, who)
                    else:
                        note = "…"
                elif val == "mute":
                    handoff_mute()
                    note = "🔕 не беспокою 2 ч (кроме «важно»)"
                else:
                    note = "…"
                with contextlib.suppress(Exception):
                    _tg_api("answerCallbackQuery",
                            {"callback_query_id": cq.get("id"), "text": note})
        except Exception as e:
            print(f"[tg] poll: {str(e)[:120]}", flush=True)
            time.sleep(5)


def render_handoff():
    msgs = handoff_load(200)
    opts = "".join(f'<option value="{t}">{HANDOFF_TOPIC_RU[t]}</option>' for t in HANDOFF_TOPICS)
    # "Прочитано" is per PERSON, not per actor: everything newer than the viewer's
    # own marker is marked "новое" on the post itself. No accounting of who owes whom.
    since_user = float(handoff_seen().get("user", 0.0) or 0.0)
    rows = []
    new_count = 0
    for m in reversed(msgs):
        topic = m.get("topic", "note")
        to = m.get("to") or ["all"]
        to_chip = "→ " + handoff_audience(to)
        own = str(m.get("owner") or "")
        own_chip = f'<span class="htag hown">владелец: {esc(own)}</span>' if own and own != m.get("from") else ""
        is_new = float(m.get("ts") or 0) > since_user and m.get("from") != "user"
        if is_new:
            new_count += 1
        state = ('<span class="hstate new" title="новое для вас">● новое</span>' if is_new
                 else '<span class="hstate read" title="прочитано">✓ прочитано</span>')
        rows.append(
            f'<article class="hm {esc(topic)}">'
            f'<div class="hmeta"><b>{esc(m.get("from", ""))}</b>'
            f'<span class="htag">{esc(HANDOFF_TOPIC_RU.get(topic, topic))}</span>{state}'
            f'<span class="hto">{esc(to_chip)}</span>{own_chip}'
            f'<time>{esc(m.get("at", ""))}</time></div>'
            f'<div class="htext">{esc(m.get("text", "")).replace(chr(10), "<br>")}</div></article>')
    empty = '<p class="hempty">Пока пусто. Оставьте первую запись.</p>' if not rows else ""
    if new_count:
        summary = (f'<div class="hcount hot"><span>Новых для вас: <b>{new_count}</b></span>'
                   f'<button class="hbtn" id="hf-ack">✓ отметить всё прочитанным</button></div>')
    else:
        summary = '<div class="hcount"><span>У вас всё прочитано ✓</span></div>'
    return (
        f'<!doctype html><html lang="ru" data-theme="dark"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<link rel="icon" type="image/svg+xml" href="{FAVICON}">'
        f'<title>Caravan · переписка</title><style>{CSS}{HANDOFF_EXTRA_CSS}</style></head><body>'
        f'<header class="topbar"><div class="topbar-in"><div class="brand">{LOGO_SVG}'
        f'<div><div class="name">Cara<span>van</span></div>'
        f'<div class="sub">переписка агентов и админа</div></div></div>'
        f'<div class="ctrls"><a class="iconbtn2" href="/" style="text-decoration:none">&larr; на дашборд</a>'
        f'</div></div></header><div class="wrap">'
        f'<div class="hform"><div class="row">'
        f'<input id="hf-from" placeholder="кто" value="user" style="width:170px">'
        f'<select id="hf-topic">{opts}</select>'
        f'<select id="hf-to" title="кому"><option value="all">всем</option>'
        + "".join(f'<option value="{esc(a)}">{"user (вам)" if a == "user" else esc(a)}</option>'
                  for a in HANDOFF_ACTORS) +
        f'</select>'
        f'<button class="open" id="hf-send">Отправить</button></div>'
        f'<textarea id="hf-text" placeholder="сообщение…"></textarea>'
        f'<p class="hnote">Доска общая: пишут и агенты (по мешу), и вы. На каждой записи есть отметка '
        f'<b>«новое / прочитано»</b> — считается по вашему последнему визиту; кнопка сверху отмечает всё '
        f'прочитанным. В Telegram уходит только адресованное <b>вам</b> («user»/«всем») или помеченное '
        f'«важно». Секреты не пишем — только факты и ссылки. Ctrl+Enter — отправить.</p></div>'
        f'{summary}{empty}{"".join(rows)}</div><script>{HANDOFF_SCRIPT}</script></body></html>')


def _icon_buttons(url, name):
    """The three secondary actions (copy / edit / delete) — shared by card and row."""
    return (
        f'<button class="mini" data-copy="{url}" data-i18n-title="copyurl" title="копировать URL">'
        f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg></button>'
        f'<button class="mini" data-edit="1" data-i18n-title="edit" title="Изменить">'
        f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg></button>'
        f'<button class="mini del" data-del="{esc(name)}" data-i18n-title="delete" title="Удалить">'
        f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        f'stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M6 6l1 14h10l1-14"/></svg></button>')


def _eng_state_chip(name, eng):
    """Hidden by default; the live poll unhides it when the engine stops answering."""
    if eng:
        return (f'<span id="eng-{esc(name)}" class="engbusy">'
                f'<span data-i18n="{"engdown" if eng == "down" else "engbusy"}">'
                f'{"движок не отвечает" if eng == "down" else "движок занят"}</span></span>')
    return (f'<span id="eng-{esc(name)}" class="engbusy" hidden>'
            f'<span data-i18n="engbusy">движок занят</span></span>')


def node_row(e, st, fl, loc, domain, tgt, ts, idx=0):
    """One compact line per node — the “Список” view.

    It carries the same element ids as the card (st-, mc-, mm-, mt-, eng-), so the
    10-second poll paints whichever view is on screen without knowing which one it is.
    """
    name = e["name"]
    onl = st.get("status") == "online"
    canon = e.get("hosts", [name])[0]
    url = f"https://{canon}.{domain}/"
    aliases = "".join(
        f'<a class="aliaschip" target="_blank" rel="noopener" title="https://{esc(a)}.{esc(domain)}/" '
        f'href="https://{esc(a)}.{esc(domain)}/">{esc(a)}</a>'
        for a in e.get("hosts", []) if a != canon)
    ev = st.get("engine_versions") or {}
    evparts = " · ".join(f'<b>{esc(ev[k])}</b>' for k in ("codenomad", "opencode") if ev.get(k))
    badge = ""
    if fl["behind"]:
        badge = (f' <span class="upd" title="доступна пара {esc(tgt[0])} / {esc(tgt[1])}">'
                 f'&#x2191; {esc(tgt[0])} / {esc(tgt[1])}</span>')
    cpu = (f'cpu <b id="mc-{esc(name)}" class="{mcls(st["cpu"])}">{st["cpu"]}%</b>'
           if st.get("cpu") is not None else "")
    mem = (f'ram <b id="mm-{esc(name)}" class="{mcls(st["mem"])}">{st["mem"]}%</b>'
           if st.get("mem") is not None else "")
    up = (f'<span title="аптайм ОС">up <b id="mt-{esc(name)}">'
          f'{humanize(st["uptime"])}</b></span>' if st.get("uptime") else "")
    load = " · ".join(p for p in (cpu, mem, up) if p)
    eng_bits = []
    if st.get("engine"):
        eng_bits.append(_eng_state_chip(name, st.get("engine")))
    if evparts:
        eng_bits.append(f'<span>{evparts}</span>')
    if badge:
        eng_bits.append(badge)
    neng = "".join(eng_bits)
    tags = ", ".join(esc(t) for t in e.get("tags", []))
    search = f"{name} {e.get('label','')} {loc} {' '.join(e.get('tags',[]))}".lower()
    alias_names = ",".join(h for h in e.get("hosts", []) if h != canon)
    return f"""
        <div class="nrow node" data-node="{esc(name)}" data-search="{esc(search)}" data-location="{esc(loc)}"
             data-name="{esc(name)}" data-ip="{esc(e['ip'])}" data-port="{esc(e['port'])}" data-label="{esc(e.get('label',''))}"
             data-tags="{esc(','.join(e.get('tags',[])))}" data-aliases="{esc(alias_names)}" data-engine="{esc(e.get('engine',''))}"
             data-state="{'online' if onl else 'offline'}" data-eng="{esc(fl['engine'])}"
             data-load="{'2' if fl['hot'] else ('1' if fl['warm'] else '0')}" data-behind="{'1' if fl['behind'] else '0'}"
             data-ord="{idx}" data-cpu="{st.get('cpu') if st.get('cpu') is not None else ''}"
             data-mem="{st.get('mem') if st.get('mem') is not None else ''}"
             tabindex="0">
          <span class="pill {'online' if onl else 'offline'}" id="st-{esc(name)}"
                title="{'в сети' if onl else 'недоступен'} {humanize(ts - st.get('since', ts))}">
            <span class="dot"></span><span class="txt">{st['status']}</span>
            <span class="ms">{(str(st['ms']) + ' ms') if onl else humanize(ts - st.get('since', ts))}</span>
          </span>
          <div class="nmain">
            <div class="ntitle">{esc(name)} {aliases}{f'<span class="ntags">{tags}</span>' if tags else ''}</div>
            <div class="nsub">{esc(e.get('label', name))} · <b title="mesh {esc(e['ip'])}:{esc(e['port'])}">{esc(e['ip'])}:{esc(e['port'])}</b></div>
          </div>
          <div class="nload">{load}</div>
          <div class="neng">{neng}</div>
          <div class="actions">
            <a class="open" target="_blank" rel="noopener" href="{url}"><span data-i18n="open">Открыть</span> &rarr;</a>
            {_icon_buttons(url, name)}
          </div>
        </div>"""


def render(data, statuses, ts, view=None):
    domain = data.get("domain", "")
    envs = data.get("envs", [])
    # A fleet outgrows tiles somewhere around here: cards read nicer, a list scans
    # better. The choice is the person's (cookie) — this is only the first guess.
    view = view if view in ("cards", "list") else ("list" if len(envs) > LIST_AT else "cards")
    # the engine *type* badge is only useful when it differs from the fleet's norm;
    # a uniform fleet would repeat the same word on every card
    engines_seen = [e.get("engine") for e in envs if e.get("engine")]
    major_engine = None
    if engines_seen:
        counts = {}
        for en in engines_seen:
            counts[en] = counts.get(en, 0) + 1
        major_engine = max(counts, key=counts.get)
    # the badge on the dashboard is for the PERSON looking at it: how many board
    # posts from others arrived since they last checked (never their own notes)
    unread_new = handoff_unread("user")[1]
    per_label = ('<span data-i18n="board">Переписка</span>'
                 + (f" ({unread_new})" if unread_new else ""))
    try:
        with open(os.path.join(REQUESTS_DIR, "invite.txt"), encoding="utf-8") as fh:
            invite_cmd = fh.read().strip()
    except Exception:
        invite_cmd = ""
    provision_pubkey = data.get("provision_pubkey", "")
    locs = []
    for e in envs:
        loc = e.get("location", "") or "—"
        if loc not in locs:
            locs.append(loc)
    chips = ([f'<button class="chipf active" data-location="all"><span data-i18n="all">Все</span>'
              f'<b class="cnt">{len(envs)}</b></button>'] if envs else [])
    for loc in locs:
        n_loc = sum(1 for e in envs if (e.get("location", "") or "—") == loc)
        chips.append(f'<button class="chipf" data-location="{esc(loc)}"><span>{esc(loc)}</span>'
                     f'<b class="cnt">{n_loc}</b></button>')
    groups = {}
    for e in envs:
        groups.setdefault(e.get("location", "") or "—", []).append(e)
    tgt = _engine.get("target") if ENGINE_UPDATE != "off" else None
    flags = {e["name"]: node_flags(e, statuses.get(e["name"]), tgt) for e in envs}
    tally = {
        "total": len(envs),
        "online": sum(1 for f in flags.values() if f["online"]),
        "offline": sum(1 for f in flags.values() if not f["online"]),
        "engdown": sum(1 for f in flags.values() if f["online"] and f["engine"] == "down"),
        "engbusy": sum(1 for f in flags.values() if f["online"] and f["engine"] == "busy"),
        "load": sum(1 for f in flags.values() if f["online"] and (f["hot"] or f["warm"])),
        "update": sum(1 for f in flags.values() if f["behind"]),
    }
    # the page opens with one question: is anything wrong? Counts answer it, and
    # each count is also a filter. Zero-count problems stay hidden (no noise).
    stat_items = [
        ("total", "s_total", ("узел", "узла", "узлов"), "", False, "всего узлов"),
        ("online", "s_online", "в сети", "good", True, "показать только онлайн"),
        ("offline", "s_offline", "не в сети", "bad", True, "показать только недоступные"),
        ("engdown", "s_engdown", "движок не отвечает", "bad", True, "хост жив, движок молчит"),
        ("engbusy", "s_engbusy", "движок занят", "warn", True, "движок не ответил вовремя"),
        ("load", "s_load", "под нагрузкой", "warn", True, "cpu или ram ≥ 75%"),
        ("update", "s_update", ("обновление", "обновления", "обновлений"), "warn", True,
         "доступна пара новее"),
    ]
    stat_html = ""
    if envs:
        parts = []
        for key, i18n, label, cls, clickable, title in stat_items:
            n = tally[key]
            hidden = " hidden" if key not in ("total", "online") and not n else ""
            if isinstance(label, tuple):
                lbl = f'<span class="lbl" data-plural="{key}">{plural_ru(n, *label)}</span>'
            else:
                lbl = f'<span data-i18n="{i18n}">{label}</span>'
            parts.append(
                f'<button class="stat {cls}{"" if clickable else " static"}" data-s="{key}" '
                f'title="{esc(title)}"{hidden}><b id="s-{key}">{n}</b>{lbl}</button>')
        stat_html = '<div class="stats" id="stats">' + "".join(parts) + "</div>"
    # one fleet-level action instead of hunting per-node badges: the same confirm
    # dialog (with release notes) opens, so a roll is never a silent click
    upd_html = ""
    if tgt and tally["update"]:
        upd_html = (
            f'<div class="updbar"><span><span data-i18n="updbar">Доступна пара</span> '
            f'<b>{esc(tgt[0])}</b> / <b>{esc(tgt[1])}</b> · '
            f'<span data-i18n="updbehind">отстают</span>: <b>{tally["update"]}</b></span>'
            f'<button class="mini" data-engup="{esc(tgt[0])}|{esc(tgt[1])}">'
            f'<span data-i18n="updall">Обновить все</span></button>'
            f'<a class="updl" target="_blank" rel="noopener" '
            f'href="https://github.com/NeuralNomadsAI/CodeNomad/releases">'
            f'<span data-i18n="updwhat">что нового</span></a></div>')
    sections = []
    quick_html = ""
    if envs:
        # filled by the browser from localStorage: pinned nodes + recently opened.
        # the hub cannot know them — they are the person's, not the fleet's.
        quick_html = '<div class="quick" id="quick" hidden></div>'
    head_html = ""
    if envs and view == "list":
        head_html = (
            '<div class="lhead" id="lhead">'
            '<button class="lh" data-sort="sev" title="проблемы первыми">'
            '<span data-i18n="h_status">статус</span><span class="ar"></span></button>'
            '<button class="lh" data-sort="name" title="по имени">'
            '<span data-i18n="h_node">узел</span><span class="ar"></span></button>'
            '<button class="lh" data-sort="cpu" title="по загрузке cpu">'
            '<span data-i18n="h_load">нагрузка</span><span class="ar"></span></button>'
            '<span class="lh static"><span data-i18n="h_engine">движок</span></span>'
            '<span class="lh static rhs"><span data-i18n="h_actions">действия</span></span>'
            '</div>')
    for loc, items in groups.items():
        lcol = loc_color(loc)
        # problems first inside each place: the eye lands on what needs action
        items = sorted(items, key=lambda e: (flags[e["name"]]["sev"], e["name"]))
        cards = []
        rows = []
        for idx, e in enumerate(items):
            name = e["name"]
            fl = flags[name]
            loc_chip = (f'<span class="chip dotonly" title="{esc(loc)}" aria-label="{esc(loc)}"></span>'
                        if loc != "—" else "")
            st = statuses.get(name, {"status": "offline", "ms": 0})
            onl = st["status"] == "online"
            canon = e.get("hosts", [name])[0]
            url = f"https://{canon}.{domain}/"
            aliases = [h for h in e.get("hosts", []) if h != canon]
            alias_chips = "".join(
                f'<a class="aliaschip" target="_blank" rel="noopener" title="https://{esc(a)}.{esc(domain)}/" '
                f'href="https://{esc(a)}.{esc(domain)}/">{esc(a)}</a>' for a in aliases)
            search = f"{name} {e.get('label','')} {loc} {' '.join(e.get('tags',[]))}".lower()
            tags = ", ".join(esc(t) for t in e.get("tags", []))
            mparts = []
            if st.get("cpu") is not None:
                mparts.append(f'<span>cpu <b id="mc-{esc(name)}" class="{mcls(st["cpu"])}">{st["cpu"]}%</b></span>')
            if st.get("mem") is not None:
                mparts.append(f'<span>ram <b id="mm-{esc(name)}" class="{mcls(st["mem"])}">{st["mem"]}%</b></span>')
            if st.get("uptime"):
                mparts.append(f'<span><span data-i18n="os_up">os up</span> <b id="mt-{esc(name)}">{humanize(st["uptime"])}</b></span>')
            metrics_html = '<div class="metrics">' + " · ".join(mparts) + "</div>" if mparts else ""
            ev = st.get("engine_versions") or {}
            evparts = [f'{k} <b>{esc(ev[k])}</b>' for k in ("codenomad", "opencode") if ev.get(k)]
            badge = ""
            if fl["behind"]:
                badge = (f' <span class="upd" title="доступна пара {esc(tgt[0])} / {esc(tgt[1])}">'
                         f'&#x2191; {esc(tgt[0])} / {esc(tgt[1])}</span>')
            engine_html = '<div class="metrics"><span>engine ' + " · ".join(evparts) + badge + "</span></div>" if evparts else ""
            eng = st.get("engine")
            eng_chip = _eng_state_chip(name, eng)
            cards.append(f"""
        <div class="card node" data-node="{esc(name)}" data-search="{esc(search)}" data-location="{esc(loc)}" style="--rc:{lcol}"
             data-name="{esc(name)}" data-ip="{esc(e['ip'])}" data-port="{esc(e['port'])}" data-label="{esc(e.get('label',''))}"
             data-tags="{esc(','.join(e.get('tags',[])))}" data-aliases="{esc(','.join(aliases))}" data-engine="{esc(e.get('engine',''))}"
             data-state="{'online' if onl else 'offline'}" data-eng="{esc(fl['engine'])}"
             data-load="{'2' if fl['hot'] else ('1' if fl['warm'] else '0')}" data-behind="{'1' if fl['behind'] else '0'}"
             data-ord="{idx}" data-cpu="{st.get('cpu') if st.get('cpu') is not None else ''}"
             data-mem="{st.get('mem') if st.get('mem') is not None else ''}"
             tabindex="0">
          <div class="top">
            {loc_chip}
            {f'<span class="engine">{esc(e["engine"])}</span>' if e.get('engine') and e.get('engine') != major_engine else ''}
            <span class="pill {'online' if onl else 'offline'}" id="st-{esc(name)}"
                  title="{'в сети' if onl else 'недоступен'} {humanize(ts - st.get('since', ts))}">
              <span class="dot"></span><span class="txt">{st['status']}</span>
              <span class="ms">{(str(st['ms']) + ' ms') if onl else humanize(ts - st.get('since', ts))}</span>
            </span>
            <button class="mini" data-check="{esc(name)}" data-i18n-title="recheck" title="Проверить">&#x21bb;</button>
          </div>
          <div class="title">{esc(name)} {alias_chips}</div>
          <div class="label">{esc(e.get('label', name))}</div>
          <div class="kv">
            <span>mesh <b>{esc(e['ip'])}:{esc(e['port'])}</b></span>
            {'<span><span data-i18n="tags">теги</span> <b>'+esc(tags)+'</b></span>' if tags else ''}
            {eng_chip}
          </div>
          {metrics_html}
          {engine_html}
          <div class="actions">
            <a class="open" target="_blank" rel="noopener" href="{url}"><span data-i18n="open">Открыть</span> &rarr;</a>
            {_icon_buttons(url, name)}
          </div>
        </div>""")
            rows.append(node_row(e, st, fl, loc, domain, tgt, ts, idx))
        label = (esc(loc) if loc != "—"
                 else '<span data-i18n="noloc">Без локации</span>')
        gprobs = sum(1 for e in items if flags[e["name"]]["sev"] <= 5)
        worst = min((flags[e["name"]]["sev"] for e in items), default=6)
        gcnt = (f'<span class="gcnt{" bad" if worst <= 1 else ""}" '
                f'title="требуют внимания: {gprobs}">&#x26A0; {gprobs}</span>' if gprobs else "")
        header = (f'<h2 class="group" style="--rc:{lcol}"><span class="dot"></span>{label}'
                  f'{gcnt}<span class="chev">▾</span></h2>')
        box = (f'<div class="rows">{"".join(rows)}</div>' if view == "list"
               else f'<div class="grid">{"".join(cards)}</div>')
        sections.append(f'<div class="groupwrap">{header}{box}</div>')
    if invite_cmd:
        cmd_html = f'<pre id="obcmd" class="joincmd">{esc(invite_cmd)}</pre>'
    else:
        cmd_html = ('<pre id="obcmd" class="joincmd obempty" data-i18n="joinempty">'
                    'Сначала сгенерируйте приглашение</pre>')
    if sections:
        body = stat_html + quick_html + upd_html + head_html + "".join(sections)
    else:
        body = f"""<section class="onboard" id="onboardwrap">
    <div class="ob-logo">{LOGO_SVG}</div>
    <h2 data-i18n="obtitle">Подключите первую машину</h2>
    <p class="ob-sub" data-i18n="obsub">Скопируйте команду и выполните её на новой машине — она появится здесь сама, с живым статусом и метриками.</p>
    <div class="ob-cmdbox">
      {cmd_html}
      <div class="ob-cmdactions">
        <button id="obgen" class="mini" data-i18n="jgenerate">Новая команда</button>
        <button id="obcopy" class="addbtn" data-i18n="obcopy">Скопировать команду</button>
      </div>
      <p class="hint" data-i18n="jwhere">Linux/VM — вставьте в терминале. Proxmox LXC — на хосте <code>pct enter &lt;VMID&gt;</code>, затем вставьте.</p>
    </div>
    <div class="ob-actions">
      <button id="obadd" class="iconbtn2" data-i18n="obaddman">Добавить по mesh-IP</button>
      <a class="ob-docs" href="{DOCS_URL}" target="_blank" rel="noopener" data-i18n="obdocs">Как это работает →</a>
    </div>
  </section>"""
    sub_html = (f'{len(envs)} <span data-i18n="envs">{plural_ru(len(envs), "окружение", "окружения", "окружений")}</span>' if envs
                else '<span data-i18n="nosub">подключите первую машину</span>')
    search_html = ("""<div class="search">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/></svg>
        <input id="q" type="text" data-i18n-ph="filter" placeholder="Поиск: имя, тег, status:… (/)" title="status:online|offline|busy|down|update|load · tag:win · loc:Дом">
      </div>""" if envs else '')
    key_block = (f"""<p class="hint" data-i18n="keyhint">…или добавьте публичный ключ хаба на новую машину (authorized_keys, либо поле «SSH public key» при создании LXC/VM):</p>
    <div class="keyline"><pre id="hubkey" class="joincmd keycmd">{esc(provision_pubkey)}</pre><button id="keycopy" class="mini" data-i18n="keycopy">Копировать ключ</button></div>""" if provision_pubkey else '')
    rail = f"""<aside class="rail">
      <div class="rl-title" data-i18n="places">Места</div>
      <div class="rl-chips">{''.join(chips)}</div>
      <div class="rl-actions">
        <button class="chipf" id="probtn" title="только узлы, требующие внимания"><span data-i18n="v_problems">Проблемы</span></button>
        <span class="seg" id="viewseg">
          <a class="segbtn{' on' if view == 'cards' else ''}" href="?view=cards" data-view="cards"><span data-i18n="v_cards">Плитки</span></a>
          <a class="segbtn{' on' if view == 'list' else ''}" href="?view=list" data-view="list"><span data-i18n="v_list">Список</span></a>
        </span>
      </div>
      <div class="rl-meta"><span data-i18n="updated">обновлено</span> <span id="utime">{time.strftime('%H:%M:%S', time.localtime(ts))}</span><br><span data-i18n="autorefresh">автообновление</span> {REFRESH}s</div>
    </aside>"""
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" type="image/svg+xml" href="{FAVICON}">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/icon-192.png">
<meta name="theme-color" content="#0b0f14">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>Caravan</title><style>{CSS}</style></head><body>
<header class="topbar"><div class="topbar-in">
    <div class="brand">{LOGO_SVG}
      <div><div class="name">Cara<span>van</span></div>
      <div class="sub">{sub_html}</div></div>
    </div>
    <div class="ctrls">
      <a class="iconbtn2" href="/handoff" style="text-decoration:none" title="Переписка агентов">{per_label}</a>
      <button id="joinbtn" class="iconbtn2" data-i18n="join">Пригласить</button>
      <button id="addbtn" class="addbtn">+ <span data-i18n="add">Добавить</span></button>
      {search_html}
      <button id="langtoggle" class="iconbtn2" title="RU / EN">EN</button>
      <button id="themebtn" class="iconbtn2" title="theme">☾</button>
    </div>
  </div>
</header>
<div class="shell{' lone' if not envs else ''}">{rail if envs else ''}
  <div class="wrap">
    <div id="applybar" class="applybar" hidden></div>
    {body}
    <div class="empty" id="nores" hidden>Ничего не найдено — измените фильтр.</div>
    <div class="foot"><a href="https://{esc(domain)}/">{esc(domain)}</a></div>
  </div>
</div>
<div id="palet" class="palet" hidden><div class="paletbox">
  <input id="paletq" type="text" autocomplete="off" data-i18n-ph="p_hint" placeholder="Узел или действие…">
  <div id="paletlist" class="paletlist"></div>
  <div class="paletfoot"><b>&uarr;&darr;</b> <span data-i18n="p_pick">выбрать</span> · <b>Enter</b> <span data-i18n="p_run">выполнить</span> · <b>Esc</b> <span data-i18n="p_close">закрыть</span></div>
</div></div>
<div id="modal" class="modal" hidden><div class="box">
  <div class="boxhead"><h3 data-i18n="addtitle">Добавить окружение</h3>
    <button id="fx" class="mini" title="Закрыть">&#x2715;</button></div>
  <div class="row"><label data-i18n="fname">имя</label><input id="f-name" placeholder="web1"></div>
  <div class="row"><label>mesh IP</label><input id="f-ip" placeholder="100.64.0.10"></div>
  <div class="row"><label data-i18n="fport">порт</label><input id="f-port" value="9898"></div>
  <div class="row"><label data-i18n="flabel">Метка</label><input id="f-label"></div>
  <div class="row"><label data-i18n="flocation">Место</label><input id="f-location" placeholder="My server · Hetzner"></div>
  <div class="row"><label data-i18n="ftags">Теги (через запятую)</label><input id="f-tags"></div>
  <div class="row"><label data-i18n="faliases">Алиасы (через запятую)</label><input id="f-aliases"></div>
  <div class="row"><label data-i18n="fengine">движок</label><select id="f-engine"><option value="">codenomad</option><option value="opencode">opencode</option></select></div>
  <label class="pinrow"><input type="checkbox" id="f-pin"> <span data-i18n="pinlabel">Закрепить в быстром доступе</span></label>
  <div class="hint" data-i18n="fhint">Сначала поднимите узел на машине (node-join.sh), затем введите его mesh-IP.</div>
  <div class="modalactions">
    <button id="fcancel" class="mini" data-i18n="cancel">Отмена</button>
    <button id="fsave" class="open" data-i18n="save">Сохранить</button>
  </div>
</div></div>
<div id="engmodal" class="modal" hidden><div class="box">
  <h3 id="engtitle">Обновить движок</h3>
  <p class="hint">Применится на <b>всех</b> узлах; они подтянут пару в течение ~30 минут.</p>
  <input type="hidden" id="engversion">
  <pre id="engnotes" class="engnotes"></pre>
  <div class="modalactions">
    <button id="engclose" class="mini" data-i18n="cancel">Отмена</button>
    <button id="enggo" class="open">Обновить</button>
  </div>
</div></div>
<div id="joinmodal" class="modal" hidden><div class="box">
  <h3 data-i18n="jointitle">Подключить машину</h3>
  <p class="hint" data-i18n="joinhint">Скопируйте команду и выполните её на новой машине — она появится здесь сама.</p>
  <pre id="joincmd" class="joincmd">{esc(invite_cmd)}</pre>
  <label class="sttopt"><input type="checkbox" id="j-stt"> <span data-i18n="sttinstall">Установить голос (STT)</span></label>
  <div class="modalactions">
    <button id="jgen" class="mini" data-i18n="jgenerate">Новая команда</button>
    <button id="jcopy" class="open" data-i18n="jcopy">Копировать</button>
    <button id="jclose" class="mini" data-i18n="cancel">Закрыть</button>
  </div>
  <p class="hint" data-i18n="jwhere">Linux/VM — вставьте в терминале. Proxmox LXC — на хосте <code>pct enter &lt;VMID&gt;</code>, затем вставьте.</p>
  <div class="magic">
    <div class="magic-h"><span class="spark">&#10022;</span> <b data-i18n="magictitle">Магия: подключить по SSH</b></div>
    <p class="hint" data-i18n="magichint">Хаб сам всё поставит и зарегистрирует, если у машины есть пароль root (обычные VPS/VM). Для Proxmox LXC — используйте команду выше.</p>
    <div class="grid2">
      <div class="row"><label>host</label><input id="p-host" placeholder="203.0.113.10" autocomplete="off"></div>
      <div class="row"><label data-i18n="provpass">Пароль root</label><input id="p-pass" type="password" autocomplete="new-password"></div>
    </div>
    <div class="grid2">
      <div class="row"><label>engine</label><select id="p-engine"><option value="">codenomad</option><option value="opencode">opencode</option></select></div>
      <div class="row" style="justify-content:flex-end"><button id="pcheck" class="mini" data-i18n="sttcheck">Проверить машину</button></div>
    </div>
    <div id="sttresult" class="sttbox" hidden></div>
    <label class="sttopt" title="Сначала нажмите «Проверить машину»"><input type="checkbox" id="p-stt" disabled> <span data-i18n="sttinstall">Установить голос (STT)</span></label>
    <div class="row" style="justify-content:flex-end"><button id="pprov" class="open" data-i18n="magicbtn">Подключить</button></div>
    <details class="adv">
      <summary data-i18n="advsum">Дополнительно: пользователь и имя</summary>
      {key_block}
      <div class="grid2">
        <div class="row"><label>ssh user</label><input id="p-user" value="root" autocomplete="off"></div>
        <div class="row"><label data-i18n="provname">Имя узла</label><input id="p-name" placeholder="node1" autocomplete="off"></div>
      </div>
    </details>
  </div>
</div></div>
<button id="totop" class="totop" hidden title="↑">↑</button>
<script>{JS.replace('__REFRESH__', str(REFRESH))}</script>
<script>if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js');</script>
</body></html>"""

def refresh_loop():
    _s_since, _s_status = load_state()
    _since.update(_s_since)
    _since_status.update(_s_status)
    while True:
        try:
            data = load_data()
            if ENGINE_UPDATE != "off" and time.time() - _engine["checked"] > 3600:
                _engine["target"] = engine_target()
                _engine["notes"] = release_notes(_engine["target"][0]) if _engine["target"] else ""
                _engine["checked"] = time.time()
            statuses = {}
            cur = {}
            engines = {}
            changed = False
            for e in data.get("envs", []):
                name = e["name"]
                est, ms, _ = check(e["ip"], e["port"])
                # the metrics agent is light and independent of the engine: a busy
                # engine (:9898) must not hide a live host's CPU/RAM/uptime
                m = check_metrics(e["ip"], e.get("metrics_port", 9101))
                if m:
                    _last_metrics[name] = m
                live = "online" if (est == "online" or m) else "offline"
                if _since_status.get(name) != live:
                    _since_status[name] = live
                    _since[name] = time.time()
                    changed = True
                entry = {"status": live, "ms": ms if est == "online" else 0,
                         "since": _since.get(name, time.time())}
                eng = classify_engine(est == "online", ms) if live == "online" else "ok"
                if eng != "ok":
                    entry["engine"] = eng
                engines[name] = eng
                if live == "online":
                    # reuse the last good reading when a check intermittently misses
                    for k in ("uptime", "cpu", "mem", "engine_versions"):
                        if k in (m or _last_metrics.get(name, {})):
                            entry[k] = (m or _last_metrics[name])[k]
                statuses[name] = entry
                cur[name] = (live, ms)
            # prune state for nodes that no longer exist (removed or renamed)
            live = {e["name"] for e in data.get("envs", [])}
            for stale in [n for n in list(_since_status) if n not in live]:
                _since_status.pop(stale, None)
                _since.pop(stale, None)
                _last_metrics.pop(stale, None)
                changed = True
            for stale in [n for n in list(_last_status) if n not in live]:
                _last_status.pop(stale, None)
                _eng_state.pop(stale, None)
            if changed:
                save_state()
            track_transitions(data.get("envs", []), cur)
            track_engine(data.get("envs", []), engines)
            html = render(data, statuses, time.time())
            with _lock:
                _cache["html"] = html
                _cache["statuses"] = statuses
                _cache["nodes"] = data
                _cache["apply"] = load_apply()
                _cache["ts"] = time.time()
        except Exception as e:
            with _lock:
                _cache["html"] = f"<body><pre>render error: {esc(e)}</pre></body>"
        time.sleep(REFRESH)

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, ctype, body):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def _check_node(self):
        """Live re-check of one node (the card's 'check' button)."""
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        name = q.get("name", [""])[0]
        try:
            envs = load_data().get("envs", [])
        except Exception:
            envs = []
        e = next((x for x in envs if x.get("name") == name), None)
        if e is None:
            self._send(404, "application/json", '{"error":"unknown node"}')
            return
        est, ms, _ = check(e["ip"], e["port"])
        m = check_metrics(e["ip"], e.get("metrics_port", 9101))
        if m:
            _last_metrics[name] = m
        m = m or _last_metrics.get(name, {})
        live = "online" if (est == "online" or m) else "offline"
        out = {"status": live, "ms": ms if est == "online" else 0,
               "since": _since.get(name, time.time())}
        eng = classify_engine(est == "online", ms) if live == "online" else "ok"
        if eng != "ok":
            out["engine"] = eng
        for k in ("uptime", "cpu", "mem"):
            if k in m:
                out[k] = m[k]
        self._send(200, "application/json", json.dumps(out))

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/status.json":
            with _lock:
                payload = {"ts": _cache["ts"], "envs": _cache["statuses"],
                           "apply": _cache.get("apply", {})}
            self._send(200, "application/json", json.dumps(payload))
        elif path == "/engine.json":
            self._send(200, "application/json", json.dumps(engine_json()))
        elif path == "/changelog":
            t = _engine.get("target") or (None, None)
            self._send(200, "application/json",
                       json.dumps({"codenomad": t[0], "opencode": t[1],
                                   "notes": _engine.get("notes", "")}))
        elif path == "/check":
            self._check_node()
        elif path == "/handoff":
            self._send(200, "text/html; charset=utf-8", render_handoff())
        elif path == "/handoff.json":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            as_ = (q.get("as", ["dev"])[0] or "dev")
            msgs = handoff_load(200)
            addr_ts = [float(m.get("ts") or 0) for m in msgs
                       if as_ in (m.get("to") or ["all"]) or "all" in (m.get("to") or ["all"])]
            self._send(200, "application/json", json.dumps(
                {"messages": msgs,
                 "unread": {a: handoff_unread(a, msgs)[0] for a in HANDOFF_ACTORS},
                 "new_for": handoff_unread(as_, msgs)[1],
                 "addressed_for": handoff_unread(as_, msgs)[2],
                 "newest_for": max(addr_ts, default=0),
                 "as": as_}, ensure_ascii=False))
        elif path == "/favicon.ico":
            self._send(200, "image/svg+xml", LOGO_SVG)
        elif path == "/manifest.webmanifest":
            self._send(200, "application/manifest+json", MANIFEST_JSON)
        elif path == "/sw.js":
            self._send(200, "application/javascript", SW_JS)
        elif path == "/icon-192.png":
            self._send(200, "image/png", base64.b64decode(ICON_192_PNG))
        elif path == "/icon-512.png":
            self._send(200, "image/png", base64.b64decode(ICON_512_PNG))
        else:
            # view choice: explicit ?view= wins, then the remembered cookie; the
            # cached HTML is the auto choice, so only re-render when they differ
            view = None
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("view", [None])[0] in ("cards", "list"):
                view = q["view"][0]
            else:
                for part in (self.headers.get("Cookie") or "").split(";"):
                    k, _, val = part.strip().partition("=")
                    if k == "cn_view" and val in ("cards", "list"):
                        view = val
            html = _cache["html"]
            if view:
                with _lock:
                    data, statuses, ts = _cache.get("nodes"), _cache["statuses"], _cache["ts"]
                if data:
                    html = render(data, statuses, ts or time.time(), view=view)
            self._send(200, "text/html; charset=utf-8", html)
    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/engine":
            try:
                n = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(n) or b"{}")
                save_engine_desired({"codenomad": body.get("codenomad", ""),
                                     "opencode": body.get("opencode", "")})
                self._send(200, "application/json", '{"ok":true}')
            except Exception as e:
                self._send(400, "application/json", json.dumps({"error": str(e)}))
            return
        if path == "/handoff/ack":
            try:
                n = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(n)
                if "application/json" in self.headers.get("Content-Type", ""):
                    body = json.loads(raw or b"{}")
                else:
                    q = urllib.parse.parse_qs(raw.decode("utf-8", "replace"))
                    body = {k: v[0] for k, v in q.items()}
                seen = handoff_ack(str(body.get("as", "dev")), body.get("upto"))
                self._send(200, "application/json",
                           json.dumps({"ok": True, "as": body.get("as", "dev"), "seen": seen}))
            except Exception as e:
                self._send(400, "application/json", json.dumps({"error": str(e)}))
            return
        if path == "/handoff":
            try:
                n = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(n)
                if "application/json" in self.headers.get("Content-Type", ""):
                    body = json.loads(raw or b"{}")
                else:
                    q = urllib.parse.parse_qs(raw.decode("utf-8", "replace"))
                    body = {k: v[0] for k, v in q.items()}
                entry = handoff_add(body.get("from", ""), body.get("topic", ""),
                                    body.get("text", ""), body.get("to", ""),
                                    body.get("owner", ""))
                self._send(200, "application/json",
                           json.dumps({"ok": True, "entry": entry}, ensure_ascii=False))
            except Exception as e:
                self._send(400, "application/json", json.dumps({"error": str(e)}))
            return
        if path != "/api/env":
            self._send(404, "application/json", '{"error":"not found"}')
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(n) or b"{}")
            os.makedirs(REQUESTS_DIR, exist_ok=True)
            fn = os.path.join(REQUESTS_DIR, f"{int(time.time()*1000)}-{os.getpid()}.json")
            with open(fn, "w", encoding="utf-8") as f:
                json.dump(body, f, ensure_ascii=False)
            os.chmod(fn, 0o600)
            self._send(200, "application/json", '{"ok":true}')
        except Exception as e:
            self._send(400, "application/json", json.dumps({"error": str(e)}))
    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    threading.Thread(target=refresh_loop, daemon=True).start()
    threading.Thread(target=tg_poll_loop, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
