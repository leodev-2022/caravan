#!/usr/bin/env python3
# CodeNomad hub portal (stdlib only). Serves /, /status.json, /favicon.ico on :8090.
# Neo-brutalist theme (blue / white / orange) with a touch of depth.
import base64
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

LOGO_SVG = ('<svg width="44" height="44" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">'
            '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
            '<stop offset="0" stop-color="#ffb26b"/><stop offset="1" stop-color="#d97b23"/></linearGradient></defs>'
            '<rect x="2" y="2" width="60" height="60" rx="16" fill="url(#g)"/>'
            '<path d="M43 21a16 16 0 1 0 0 22" stroke="#20160a" stroke-width="7" stroke-linecap="round" fill="none"/></svg>')
FAVICON = "data:image/svg+xml;base64," + base64.b64encode(LOGO_SVG.encode()).decode()
ICON_192_PNG = "iVBORw0KGgoAAAANSUhEUgAAAMAAAADACAMAAABlApw1AAAAYFBMVEX8rWT5qV/3plv1pFn0olbzn1LxnlDwnE7vm0zumUvtmEnul0fslkfrlUXqlETqk0PpkkHokT/nkD7mjz3ljTrkizfjiTbhiDTghTDdgi2bXCEhFgogFgogFgkfFgoXEAf/j1RXAAAMV0lEQVR42tWd2ZajNhBAbYzMDmIxNOC4//8vowWwDNpB40bzlD6dTF3VRWgpkcvFsF0vV27zOO32bv7NXzXgA6bdlxbgP7SFQTi3aG7x1JI4SZM0TS8XdwS3N4G/beAj/jdBwDRx/FP4FgBX7QTc2ATIep/t/w+AVfQx/jOFT6M3BhD3/lXqj+/IH/MMuPDnbuPP1LL03P4ggnP7Y6jQX/PHVKE/50+WZlnm1h/f2fuLAGACt/7c3PqTmWTAxh/ftT+6AH/THwOAP+uPdgb+qj95np3bn0wH4C/7g1JwZn9Q+EqAP+2PDsAf90cjA3/bHwXA3/cnL/Jz+1MUhXN/fIf+FLkE4AT+kBQ49we49Eem0EH++E79EQIc5Q9w6Y80A2cYf0iD5/angIVTf4BrfyCETv3x3foDIR/gPP7wAM7lDy8Dp/KHl4HD5j93fjvUH1jC4/0hfe7f6G/Rfw/9EAd+vD+I4GB/UOge+nU/qvt+mFvf1ZGPMACK+lh/NhnY5w8J3q9RyOM4/jLtNY6YI/U9xBAe5g8KvywP8wdHf8tx7HPMTHvRHw1Dd0cMUXiMPyVuB/kD/Os1p8FPoT/ZRn+CMFAqeuDfo+gIf+AnwA5/gHcNUN9PwT9FjaYCJSL3AUHY7c8bYI8/KPx4jv6paPhXUB5QGgjCPn8+MmDvzw27g+VQRr9AoDxghDgKd/rDZMDaHyTPiDv/adDwIPUaOhDEO/2ZAHb4c/XMw6cMz9/nUIE43uVPWZX7/Ll2RJ6nTUMI4wCCdI8/iGCPP54/vGzDJwiv36EGsb0/VVlV1v6g7q/H36d9+ORZwEmI7P2pKkkGVP5ckf27wp+TEIapnT8Vbrbn795tQA/vc3fDSajvWWznjxBA6Y8Hhj32fyD8jj3IUit/qrqy8+caHaAPQzBgAgt/6rq+2Iw/1/zA+PGD8BxAbuMPH0Dpz8HxY4LXlAMjf4QZUPjjxQfHTwejIDf3hwug8scLtOL/WNDo5KAPc2N/OAAa448y/mUNxiwpVRDoP1okxv7wMqB6f3mDIn4a/EiWwaSNy0JNToAkMvVnC6CsH77K4yfR49i7HOB04b0IENb9vF6TpoAMQUb+rAHU8+dr/ytdM5Loa4B3goJ5zRiGd7RNl/eDYuaKnwJDfzYZUPojG0BJ+EMDvI/9n3nlHgBQSxGwQ4WhPysA9frrJosfTa2H1PPJ1tt9u38YxwEICYIMwMyfumEAdNZf4geAzIwj1Pls8Mz2W0hWXhGI8Bx2VAHo+tM0zcVg/YUEEk1AydoEhT9toIv2D9G0GWQDPwkIICwM/WEBdNbvgzj943Dzg+UEYBU+s/8TpxHo+SK++qQw8gfHPwPo7P9I4++8IBBsn6/331IAORrhYdTQHxZAZ//nLnqC0c9jb9P9ovjjOAvDYbMYxY8ANPVnAdDwBwgTgP7q+6wPx59wu3+YpmBNgDqhzApTfyYArf3nm2gOh+L3QXAX+hNx9g/TDHyuSMfXf/MTYOLPnAGN/WdhAkj8d31/pvs7iOC9JYPG4OcQQnN/MICnd34hSgD66fsET8ufaf8nx4PRL511o3G1J/Gb+kMBdM4vRAnAz69v6M+0/5OHaFP4Sabb41Al0MYfAqB5/sVNADq06GXjTyQ7v8iTICEHaX0ZZHb+8AF4519e9xK8PT3Z+BPKzy/yLAzQ5CPMYGHnDxeAd34qMAhlBdyt/JmXvzRoi/eXGIDrD/8RRgJ10wPA9+eA8wu5PxwA/vmpKAGDF5iPP3b7P/z4H4+Lzvk7HwBNTXOwx5/MfP3VrAFWGRDVb/ANmhPwPX8eqwwI6jeA18kTcJeUDzj0B8f/ASCq3xAYNCVA5U/k0J9PAGH9D/C4Br16P/iyPx8Awvof4KecpeT8DviqPyyAuH4MeL3QoC/7wwBI6sdEgyh6iX3bnzeArH7szgNABkX34Nv+LADy+kOPC4AM0np/xQ79mQFU9fMjHyDU8Sdx6c8EoKhf9WPuINT7oYY/sVN/Hi0GUNWv3uotAPpJDdT+pI79ebTtZVNBsKlf9ToOAH2Glf7EzPX9w/1pcbuo65/Raoy7llf6kzAPgBN/PgFE9c933nsMv4fV8+fEqT/tOgOC+ue7YBQF4Wr/Z/P+SmORP/kB40+7AhDWz4sA/Ej//cXtf4j/TOFDJn4JwDb+BYBz/wuoAcJAvP3GGX8+9S/WvT/1f6Uz/LcrAF9cPy94BpBC7/A161dz/gP84Y/0+W1EALLrF8KHONyu37nv37U/qwJ6YfyNfgbE/hAA/jC6PYBZps//zJ+u6y5yfzCAz3+RpYGOP5lTfyiA6vqOz59KNCD6uj8tPwOr+ztAMJmjAF/1B2fAV3zACK97R8E4+nV/uADb+1OiV3Gk9id16I8AYBt/wAcYY87y/R/7wwVY+8MHwNtCIPq2P1sA3v27wBdsq/ix1J80c+7PBoB/fxDk/I2tUMefzKU/WwCfd/8x8AVbiyBW+5O59GcFILy/6Q1Ch+T+5I79+QQQxo8fAl6FzVgH8Xf9WQH4/Pu/aP8tFhxwgPS7/nQ/bwDh9zfwussXHDFV4Xf9+fn5uaj8wQR8AJoClT+5S386BkDoD6nh4xaboZ/1wRf9YQAk/hCESJSCMVD6U8j9wbFa+oMNogBSf8jmCehFpQZIIpk/ucSfuq4KtHeUwHXsev78/LwBpP7Q+9f8Yg8kEboAI/SnyCX+1FVS0mKPJqks/FkAVP7g+AUOYYlgmCY2409d1FO5Dbrf2kErfzgAHH/I/lWQCwuekki0/Sb1J1kKnvD91r54WPiDAYDaHwwgSgGpV40zvj+FxJ+EKeEld0PfBPr+UAClP6QOPRCV7WKCJOP4k4vHnxrFvyr6G/vyYezPGkDgD9k/iX1J2WW2XB/R8ofEvym7bM39WQEI/QmnFIgLX+vl9sXKH8jxp4aQW/hatKb+fAKI/SEtBrLS4x7kuZ4/qPtbfumxuT8fADJ/6P6P+PrP+PvfkKDac8ECnvWnLhNh8Xdp6g8LIPWH7P/E905Wfo/mRUmRK/xBL68GV7zyHyXYGvrDACj8oUtHIL0A8RzqIIWFcP5Awq9kFyAQgJk/bwC1PxRBdQWlRlmA3Pkbch8mpfwKyhtAs/sXALU/NP5ALBG9goW+GJGECXP4RQDwtA0mSae6BGQNoOMP2f9JgfQaGUFAExs8xczhNGVGB2DoH7NuUF/DqlpDfyYATX8icvtC8yJc35CZMg69aHv6zRjVRbjWuPspgKY/0/5JqLhKOa6vItLZms5VxLI1Bug/AeT+0LPfKNO7DMrcBn09tS6Ddo2xP33fX9jqf7k/E0FYGV/H1bsSTRNg5M8PBjDxh1zhCRonF6IngewBNPyh6/cMDabHX0mHrYU//RtAzx+6fj+aAH8UAJr7swLQ84eufrOwPvizDLB77APQ9me+PZId+mGM0tKfGcDEn5kgOe7TJH1p688CYOIPXb/nWSCcVxoOP03TPvYBGPozrd8L/Cgf8Hme8mHvzyYDev5M63c02dn1gSQ85xj6ck/3UwBzf5bVe9jv/ERV2bSPnQDvB9jEn2n9jibK9h8JG4efsm0fe/whAHb+TNsnRRHWtp9p6/d3/wrArP5n2v+B2bzSMvlQHg6/slh/iQEs/Jn3f2AStrqfKnzSu6vDUL7t2eEPD8DAn3n/BJZZUut9LPJJNtN7yIS/p/tZACt/lv0TfNTSsZ/rfAo/1zk0sGF6/xCAHf4s2ydVWdCVO/lg6uvFrmieZHn2xB8bbeDy6B7gzwbAwh9mAwsz0FOjzzXl60VWyH1XFlrR63f/ArDPn/cGFtoAwhAJ7JhvBqPQUccXRVmjSYPF/rMaYL8/JVN/Ts58SxRwRrdV8K+UNQ7b5vxCHj0BOMYfCNfl/w23HesPBgiDo/xhDsD2nb8bAhzpz/b6guX5u2b0DMCR/lQa5f/HdP8CcFZ/3gBO/Gmc+zMDnNYfCnBifzBAdGZ/pgyc1x+SgTP781bopP4wGTinPx8AZ/RnAnDrz8OhP3MGTuvPG8CdP41Lf2aFzjn+TABx5NCfxrE/NANOxx/3AEv/O/Dn4dofAuDQn8Z197MAp/RnATirPzPAaf1ZAM7qDwU4sT9TBs7rDwZIzuwPH+BE/mCANDmxPwTAnT9t+wWAI/0RABzoDwNg60/zVX8WgCxV/P83hd//0en/fwCQSu/frb5fVO0aP48Nv+//B2rbQ704Qn8MAAAAAElFTkSuQmCC"
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
const C='caravan-v1';
self.addEventListener('install',function(){self.skipWaiting();});
self.addEventListener('activate',function(e){e.waitUntil(self.clients.claim());});
self.addEventListener('fetch',function(e){
  var u=new URL(e.request.url);
  if(e.request.method!=='GET'||u.pathname.indexOf('/status.json')===0||u.pathname.indexOf('/api/')===0)return;
  e.respondWith(fetch(e.request).then(function(r){var c=r.clone();caches.open(C).then(function(x){x.put(e.request,c);});return r;})
    .catch(function(){return caches.match(e.request);}));
});
"""

_cache = {"html": "<body>loading</body>", "statuses": {}, "ts": 0}
_lock = threading.Lock()
_last_status = {}
_initialized = [False]
_ever_online = set()
_since = {}
_since_status = {}
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

def check(ip, port):
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(f"http://{ip}:{port}/", method="GET"), timeout=2.5) as r:
            return "online", int((time.time() - t0) * 1000), r.status
    except Exception:
        return "offline", int((time.time() - t0) * 1000), None

def check_metrics(ip, port):
    try:
        with urllib.request.urlopen(f"http://{ip}:{port}/metrics", timeout=1.5) as r:
            return json.load(r)
    except Exception:
        return {}

def notify(text):
    if not (TG_TOKEN and TG_CHAT):
        return
    try:
        data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": text}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data, method="POST")
        with urllib.request.urlopen(req, timeout=8):
            print(f"[tg] sent: {text}", flush=True)
    except Exception as e:
        print(f"[tg] FAIL: {text} err={e}", flush=True)

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
            if st == "online" and prev == "offline":
                if name in _ever_online:
                    notify(f"\U0001F7E2 {name} ({e.get('label', name)}) is back online")
            elif st == "offline" and name in _ever_online:
                notify(f"\U0001F534 {name} ({e.get('label', name)}) is DOWN")
            _ever_online.add(name)
        _last_status[name] = st

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
  --ok:#34d399;--down:#f87171;--warn:#fbbf24;--radius:12px;--radius-sm:8px;
  --shadow:0 10px 30px -14px rgba(0,0,0,.7)}
[data-theme="light"]{--bg:#f6f8fb;--panel:#ffffff;--panel2:#fbfcfe;--line:#e3e8ef;--line2:#d4dae3;
  --ink:#0f1b2a;--muted:#5b6b7f;--shadow:0 10px 30px -14px rgba(15,27,42,.22)}
*{box-sizing:border-box}
body{margin:0;font-family:Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:var(--ink);
  background-color:var(--bg);background-image:radial-gradient(900px 480px at 50% -12%,rgba(242,153,74,.08),transparent 70%);
  min-height:100vh;display:flex;flex-direction:column;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{width:100%;max-width:1200px;margin:0 auto;padding:24px 24px 48px;flex:1 0 auto;display:flex;flex-direction:column}
header{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:20px}
.brand{display:flex;align-items:center;gap:12px}
.brand .name{font-size:22px;font-weight:800;letter-spacing:-.01em;line-height:1}
.brand .name span{color:var(--accent)}
.brand .sub{font-size:12px;color:var(--muted);margin-top:5px}
.ctrls{margin-left:auto;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.search{position:relative}
.search input{width:280px;max-width:56vw;padding:10px 14px 10px 38px;border:1px solid var(--line);border-radius:var(--radius-sm);
  background:var(--panel);font-size:14px;color:var(--ink);outline:none;transition:border-color .15s,box-shadow .15s}
.search input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(242,153,74,.15)}
.search svg{position:absolute;left:12px;top:11px;color:var(--muted)}
.iconbtn2{border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:var(--radius-sm);padding:9px 12px;
  font-size:13px;font-weight:600;cursor:pointer;line-height:1;transition:border-color .15s,background .15s}
.iconbtn2:hover{border-color:var(--line2);background:var(--panel2)}
.addbtn{border:1px solid transparent;background:var(--accent);color:var(--accent-ink);border-radius:var(--radius-sm);padding:10px 16px;
  font-weight:700;font-size:14px;cursor:pointer;transition:background .15s}
.addbtn:hover{background:var(--accent2)}
.filters{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:4px 0 22px}
.chipf{border:1px solid var(--line);background:var(--panel);color:var(--muted);border-radius:999px;padding:6px 14px;font-size:13px;
  font-weight:600;cursor:pointer;transition:all .15s}
.chipf:hover{color:var(--ink);border-color:var(--line2)}
.chipf.active{background:var(--accent);color:var(--accent-ink);border-color:transparent}
.meta-line{color:var(--muted);font-size:12px;margin-left:auto;font-weight:500}
h2.group{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:600;
  margin:24px 0 12px;display:flex;align-items:center;gap:9px;cursor:pointer;user-select:none}
h2.group .dot{width:8px;height:8px;border-radius:50%;background:var(--accent)}
h2.group .chev{margin-left:auto;font-size:11px;transition:transform .15s}
h2.group.collapsed .chev{transform:rotate(-90deg)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px}
.grid.collapsed{display:none}
.card{background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--line);border-radius:var(--radius);
  padding:16px;box-shadow:var(--shadow);transition:border-color .15s,transform .1s;position:relative}
.card:hover{border-color:var(--line2);transform:translateY(-1px)}
.top{display:flex;align-items:center;gap:8px;margin-bottom:12px}
.chip{color:var(--muted);font-size:11px;font-weight:600;padding:3px 9px;border-radius:999px;border:1px solid var(--line);
  background:var(--panel2);display:inline-flex;align-items:center;gap:6px}
.chip::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--rc,var(--accent))}
.engine{font-size:11px;font-weight:600;color:var(--accent);border:1px solid var(--line);border-radius:999px;padding:2px 8px;background:var(--panel2)}
.pill{margin-left:auto;display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;
  padding:4px 10px;border-radius:999px;background:rgba(52,211,153,.14);color:var(--ok)}
.pill.offline{background:rgba(248,113,113,.14);color:var(--down)}
.pill .dot{width:7px;height:7px;border-radius:50%;background:currentColor}
.pill.online .dot{animation:pulse 2s infinite}
.pill .ms{color:var(--muted);font-weight:500}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(52,211,153,.5)}70%{box-shadow:0 0 0 5px rgba(52,211,153,0)}100%{box-shadow:0 0 0 0 rgba(52,211,153,0)}}
.title{font-size:16px;font-weight:700;letter-spacing:-.01em}
.aliaschip{font-size:11px;font-weight:600;color:var(--accent);border:1px solid var(--line);border-radius:999px;padding:1px 8px;margin-left:6px;vertical-align:middle}
.aliaschip:hover{text-decoration:none;border-color:var(--accent)}
.label{color:var(--muted);font-size:13px;margin:2px 0 12px}
.kv{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12px;color:var(--muted);margin-bottom:14px}
.kv b{color:var(--ink);font-weight:600;font-family:var(--mono)}
.metrics{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12px;color:var(--muted);margin:-6px 0 14px;font-family:var(--mono)}
.metrics b{color:var(--ink);font-weight:600}
.metrics b.warm{color:var(--warn)}
.metrics b.hot{color:var(--down)}
.actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.open{display:inline-flex;align-items:center;gap:7px;background:var(--accent);color:var(--accent-ink);font-weight:700;
  font-size:13px;padding:9px 14px;border-radius:var(--radius-sm);border:1px solid transparent;transition:background .15s}
.open:hover{background:var(--accent2);text-decoration:none}
.mini{border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:var(--radius-sm);padding:8px 11px;
  font-size:12px;font-weight:600;cursor:pointer;transition:all .15s}
.mini:hover{color:var(--ink);border-color:var(--line2);background:var(--panel2)}
.mini.del:hover{color:#fff;background:var(--down);border-color:var(--down)}
.mini svg{width:15px;height:15px;display:block}
.mini{padding:9px}
.aliases{margin-top:12px;font-size:12px;color:var(--muted)}
.aliases a{margin-right:12px}
.foot{color:var(--muted);font-size:12px;margin-top:auto;padding-top:36px;text-align:center}
.empty{color:var(--muted);padding:24px;text-align:center}
.modal{position:fixed;inset:0;background:rgba(5,9,14,.65);display:flex;align-items:center;justify-content:center;z-index:50;padding:16px}
.modal[hidden]{display:none}
.box{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:24px;width:min(520px,96vw);box-shadow:var(--shadow)}
.box h3{margin:0 0 18px;font-weight:700;font-size:17px}
.row{display:flex;flex-direction:column;gap:5px;margin-bottom:12px}
.row label{font-size:12px;color:var(--muted);font-weight:600}
.row input{padding:10px 12px;border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--panel2);color:var(--ink);font-size:14px}
.row input:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(242,153,74,.15)}
.hint{font-size:12px;color:var(--muted);margin:6px 0 18px}
.joincmd{background:var(--panel2);border:1px solid var(--line);border-radius:var(--radius-sm);padding:12px;font-family:var(--mono);
  font-size:12.5px;line-height:1.5;white-space:pre-wrap;overflow-wrap:anywhere;color:var(--ink);max-height:180px;overflow:auto;margin:0 0 16px}
.prov{margin-top:18px;padding-top:16px;border-top:1px solid var(--line)}
.prov .hint{margin-top:0}
.modalactions{display:flex;gap:10px;justify-content:flex-end}
.toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:var(--panel);color:var(--ink);border:1px solid var(--line);
  padding:12px 20px;border-radius:var(--radius-sm);font-size:14px;font-weight:600;z-index:60;box-shadow:var(--shadow)}
"""

JS = """
(function(){
  var REFRESH=__REFRESH__*1000;
  var I18N={
    ru:{filter:"Фильтр: имя, место, тег… (клавиша /)",updated:"обновлено",autorefresh:"автообновление",
        envs:"окружений",open:"Открыть",copyurl:"копировать URL",copyip:"копировать IP",copied:"скопировано",
        tags:"теги",online_for:"в сети",offline_for:"недоступен",os_up:"аптайм ОС",all:"Все",add:"Добавить",addtitle:"Добавить окружение",edittitle:"Изменить окружение",flabel:"Метка",flocation:"Место",
        ftags:"Теги (через запятую)",faliases:"Алиасы (через запятую)",fhint:"Сначала поднимите узел на машине (node-join.sh), затем введите его mesh-IP.",
        save:"Сохранить",cancel:"Отмена",delete:"Удалить",edit:"Изменить",delconfirm:"Удалить окружение",applying:"Применяю… страница обновится",empty:"Ничего не найдено",
        join:"Пригласить",jointitle:"Подключить машину",joinhint:"Выполните эту одну строку на новой машине (без флагов). Пусто? Нажмите «Сгенерировать».",jgenerate:"Сгенерировать",jcopy:"Копировать",joinempty:"Сначала сгенерируйте приглашение",
        provhint:"…или поднимите узел по SSH (машина достижима с хаба; root или passwordless-sudo):",provpass:"Пароль SSH",provbtn:"Провизжинить по SSH"},
    en:{filter:"Filter: name, location, tag… (press /)",updated:"updated",autorefresh:"auto-refresh",
        envs:"environments",open:"Open",copyurl:"copy URL",copyip:"copy IP",copied:"copied",
        tags:"tags",online_for:"online for",offline_for:"down for",os_up:"os uptime",all:"All",add:"Add",addtitle:"Add environment",edittitle:"Edit environment",flabel:"Label",flocation:"Location",
        ftags:"Tags (comma-separated)",faliases:"Aliases (comma-separated)",fhint:"First onboard the machine (node-join.sh), then enter its mesh IP.",
        save:"Save",cancel:"Cancel",delete:"Delete",edit:"Edit",delconfirm:"Delete environment",applying:"Applying… page will refresh",empty:"Nothing found",
        join:"Invite",jointitle:"Join a machine",joinhint:"Run this one line on the new machine (no flags). Empty? Click Generate invite.",jgenerate:"Generate invite",jcopy:"Copy",joinempty:"Generate an invite first",
        provhint:"…or provision a node over SSH (reachable from the hub; root or passwordless-sudo):",provpass:"SSH password",provbtn:"Provision by SSH"}
  };
  function cur(){return localStorage.getItem('cn_lang')||'ru';}
  function humanize(sec){sec=Math.max(0,sec|0);if(sec<60)return sec+'s';if(sec<3600)return Math.floor(sec/60)+'m';if(sec<86400)return Math.floor(sec/3600)+'h';return Math.floor(sec/86400)+'d';}
  var locFilter='all';
  function apply(l){
    localStorage.setItem('cn_lang',l); document.documentElement.lang=l;
    document.querySelectorAll('[data-i18n]').forEach(function(el){var k=el.getAttribute('data-i18n'); if(I18N[l][k]!=null) el.textContent=I18N[l][k];});
    document.querySelectorAll('[data-i18n-ph]').forEach(function(el){var k=el.getAttribute('data-i18n-ph'); if(I18N[l][k]!=null) el.placeholder=I18N[l][k];});
    document.querySelectorAll('[data-i18n-title]').forEach(function(el){var k=el.getAttribute('data-i18n-title'); if(I18N[l][k]!=null) el.title=I18N[l][k];});
    var t=document.getElementById('langtoggle'); if(t) t.textContent=(l==='ru'?'EN':'RU');
  }
  function setTheme(t){document.documentElement.setAttribute('data-theme',t);localStorage.setItem('cn_theme',t);
    var b=document.getElementById('themebtn'); if(b) b.textContent=(t==='dark'?'\\u2600':'\\u263E');}
  function filters(){
    var v=(document.getElementById('q').value||'').toLowerCase();
    document.querySelectorAll('.card').forEach(function(c){
      var okText=(c.getAttribute('data-search')||'').indexOf(v)>=0;
      var okLoc=(locFilter==='all'||c.getAttribute('data-location')===locFilter);
      c.style.display=(okText&&okLoc)?'':'none';
    });
    document.querySelectorAll('.groupwrap').forEach(function(g){
      var any=Array.prototype.some.call(g.querySelectorAll('.card'),function(c){return c.style.display!=='none';});
      g.style.display=any?'':'none';
    });
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
    document.getElementById('modal').setAttribute('data-original',env.name||'');
    document.querySelector('#modal h3').textContent=(env.name?I18N[cur()].edittitle:I18N[cur()].addtitle);
    document.getElementById('modal').hidden=false;
  }
  function upd(d){
    var el=document.getElementById('utime');
    if(el) el.textContent=new Date((d.ts||Date.now()/1000)*1000).toLocaleTimeString();
    for(var n in d.envs){var p=document.getElementById('st-'+n); if(!p) continue; var s=d.envs[n];
      p.className='pill '+(s.status==='online'?'online':'offline');
      var t=p.querySelector('.txt'); if(t) t.textContent=s.status;
      var m=p.querySelector('.ms'); if(m) m.textContent=s.ms+' ms';
      var up=document.getElementById('up-'+n); if(up&&s.since) up.textContent=humanize(Date.now()/1000-s.since);
      if(s.since) p.title=(I18N[cur()][s.status==='online'?'online_for':'offline_for'])+' '+humanize(Date.now()/1000-s.since);
      var mc=document.getElementById('mc-'+n); if(mc&&s.cpu!=null){mc.textContent=s.cpu+'%';mc.className=s.cpu>=90?'hot':(s.cpu>=75?'warm':'');}
      var mm=document.getElementById('mm-'+n); if(mm&&s.mem!=null){mm.textContent=s.mem+'%';mm.className=s.mem>=90?'hot':(s.mem>=75?'warm':'');}
      var mt=document.getElementById('mt-'+n); if(mt&&s.uptime!=null) mt.textContent=humanize(s.uptime);
    }
  }
  function poll(){fetch('status.json',{cache:'no-store'}).then(function(r){return r.json()}).then(upd).catch(function(){});}
  document.addEventListener('input',function(e){ if(e.target&&e.target.id==='q') filters(); });
  document.addEventListener('click',function(e){
    var gh=e.target.closest('h2.group'); if(gh){ var grid=gh.parentNode.querySelector('.grid');
      if(grid){ grid.classList.toggle('collapsed'); gh.classList.toggle('collapsed'); } return; }
    var cf=e.target.closest('.chipf'); if(cf){ locFilter=cf.getAttribute('data-location');
      document.querySelectorAll('.chipf').forEach(function(x){x.classList.toggle('active',x===cf);}); filters(); return; }
    var b=e.target.closest('[data-copy]');
    if(b){navigator.clipboard.writeText(b.getAttribute('data-copy')).then(function(){toast(I18N[cur()].copied);}); return;}
    var t=e.target.closest('#langtoggle'); if(t){apply(cur()==='ru'?'en':'ru'); return;}
    var th=e.target.closest('#themebtn'); if(th){var c=document.documentElement.getAttribute('data-theme');setTheme(c==='dark'?'light':'dark');return;}
    var ad=e.target.closest('#addbtn'); if(ad){openModal({});return;}
    var jb=e.target.closest('#joinbtn'); if(jb){document.getElementById('joinmodal').hidden=false;return;}
    var jc=e.target.closest('#jclose'); if(jc){document.getElementById('joinmodal').hidden=true;return;}
    var jg=e.target.closest('#jgen'); if(jg){post({action:'invite'},function(){toast(I18N[cur()].applying);setTimeout(function(){location.reload();},7000);});return;}
    var jcp=e.target.closest('#jcopy'); if(jcp){var t=(document.getElementById('joincmd').textContent||'').trim();if(!t){toast(I18N[cur()].joinempty);return;}navigator.clipboard.writeText(t).then(function(){toast(I18N[cur()].copied);});return;}
    var pp=e.target.closest('#pprov'); if(pp){var ph=(document.getElementById('p-host').value||'').trim();var pu=(document.getElementById('p-user').value||'').trim();var pw=document.getElementById('p-pass').value||'';if(!ph||!pu){alert('host & user required');return;}post({action:'provision',host:ph,user:pu,password:pw},function(){toast(I18N[cur()].applying);});return;}
    var ed=e.target.closest('[data-edit]'); if(ed){ var c=ed.closest('.card');
      openModal({name:c.getAttribute('data-name'),ip:c.getAttribute('data-ip'),port:c.getAttribute('data-port'),
        label:c.getAttribute('data-label'),location:c.getAttribute('data-location'),engine:c.getAttribute('data-engine'),
        tags:(c.getAttribute('data-tags')||'').split(',').map(function(s){return s.trim();}).filter(Boolean),
        aliases:(c.getAttribute('data-aliases')||'').split(',').map(function(s){return s.trim();}).filter(Boolean)}); return;}
    var cx=e.target.closest('#fcancel'); if(cx){document.getElementById('modal').hidden=true;return;}
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
    if(e.key==='Escape'){['modal','joinmodal'].forEach(function(id){var m=document.getElementById(id); if(m) m.hidden=true;});}
  });
  apply(cur()); setTheme(localStorage.getItem('cn_theme')||'dark');
  setInterval(poll,REFRESH); poll();
})();
"""

def render(data, statuses, ts):
    domain = data.get("domain", "")
    envs = data.get("envs", [])
    try:
        with open(os.path.join(REQUESTS_DIR, "invite.txt"), encoding="utf-8") as fh:
            invite_cmd = fh.read().strip()
    except Exception:
        invite_cmd = ""
    locs = []
    for e in envs:
        loc = e.get("location", "") or "—"
        if loc not in locs:
            locs.append(loc)
    chips = ['<button class="chipf active" data-location="all" data-i18n="all">Все</button>']
    for loc in locs:
        chips.append(f'<button class="chipf" data-location="{esc(loc)}">{esc(loc)}</button>')
    groups = {}
    for e in envs:
        groups.setdefault(e.get("location", "") or "—", []).append(e)
    sections = []
    for loc, items in groups.items():
        cards = []
        for e in items:
            name = e["name"]
            lcol = loc_color(loc)
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
            cards.append(f"""
        <div class="card" data-search="{esc(search)}" data-location="{esc(loc)}" style="--rc:{lcol}"
             data-name="{esc(name)}" data-ip="{esc(e['ip'])}" data-port="{esc(e['port'])}" data-label="{esc(e.get('label',''))}"
             data-tags="{esc(','.join(e.get('tags',[])))}" data-aliases="{esc(','.join(aliases))}" data-engine="{esc(e.get('engine',''))}">
          <div class="top">
            <span class="chip">{esc(loc)}</span>
            {f'<span class="engine">{esc(e["engine"])}</span>' if e.get('engine') else ''}
            <span class="pill {'online' if onl else 'offline'}" id="st-{esc(name)}"
                  title="{'в сети' if onl else 'недоступен'} {humanize(ts - st.get('since', ts))}">
              <span class="dot"></span><span class="txt">{st['status']}</span><span class="ms">{st['ms']} ms</span>
            </span>
          </div>
          <div class="title">{esc(name)} {alias_chips}</div>
          <div class="label">{esc(e.get('label', name))}</div>
          <div class="kv">
            <span>mesh <b>{esc(e['ip'])}:{esc(e['port'])}</b></span>
            {'<span><span data-i18n="tags">теги</span> <b>'+esc(tags)+'</b></span>' if tags else ''}
          </div>
          {metrics_html}
          <div class="actions">
            <a class="open" target="_blank" rel="noopener" href="{url}"><span data-i18n="open">Открыть</span> &rarr;</a>
            <button class="mini" data-copy="{url}" data-i18n-title="copyurl" title="копировать URL"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg></button>
            <button class="mini" data-edit="1" data-i18n-title="edit" title="Изменить"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg></button>
            <button class="mini del" data-del="{esc(name)}" data-i18n-title="delete" title="Удалить"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M6 6l1 14h10l1-14"/></svg></button>
          </div>
        </div>""")
        sections.append(f'<div class="groupwrap"><h2 class="group"><span class="dot"></span>{esc(loc)}<span class="chev">▾</span></h2><div class="grid">{"".join(cards)}</div></div>')
    body = "".join(sections) if sections else '<div class="empty" data-i18n="empty">Ничего не найдено</div>'
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" type="image/svg+xml" href="{FAVICON}">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/icon-192.png">
<meta name="theme-color" content="#0b0f14">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>Caravan</title><style>{CSS}</style></head><body>
<div class="wrap">
  <header>
    <div class="brand">{LOGO_SVG}
      <div><div class="name">Cara<span>van</span></div>
      <div class="sub">{len(envs)} <span data-i18n="envs">окружений</span></div></div>
    </div>
    <div class="ctrls">
      <button id="joinbtn" class="iconbtn2" data-i18n="join">Пригласить</button>
      <button id="addbtn" class="addbtn">+ <span data-i18n="add">Добавить</span></button>
      <div class="search">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/></svg>
        <input id="q" type="text" data-i18n-ph="filter" placeholder="Фильтр: имя, место, тег… (клавиша /)">
      </div>
      <button id="langtoggle" class="iconbtn2" title="RU / EN">EN</button>
      <button id="themebtn" class="iconbtn2" title="theme">☾</button>
    </div>
  </header>
  <div class="filters">
    {''.join(chips)}
    <span class="meta-line"><span data-i18n="updated">обновлено</span> <span id="utime">{time.strftime('%H:%M:%S', time.localtime(ts))}</span> · <span data-i18n="autorefresh">автообновление</span> {REFRESH}s</span>
  </div>
  {body}
  <div class="foot"><a href="https://{esc(domain)}/">{esc(domain)}</a></div>
</div>
<div id="modal" class="modal" hidden><div class="box">
  <h3 data-i18n="addtitle">Добавить окружение</h3>
  <div class="row"><label>name</label><input id="f-name" placeholder="web1"></div>
  <div class="row"><label>mesh IP</label><input id="f-ip" placeholder="100.64.0.10"></div>
  <div class="row"><label>port</label><input id="f-port" value="9898"></div>
  <div class="row"><label data-i18n="flabel">Метка</label><input id="f-label"></div>
  <div class="row"><label data-i18n="flocation">Место</label><input id="f-location" placeholder="My server · Hetzner"></div>
  <div class="row"><label data-i18n="ftags">Теги (через запятую)</label><input id="f-tags"></div>
  <div class="row"><label data-i18n="faliases">Алиасы (через запятую)</label><input id="f-aliases"></div>
  <div class="row"><label>engine</label><select id="f-engine"><option value="">codenomad</option><option value="opencode">opencode</option></select></div>
  <div class="hint" data-i18n="fhint">Сначала поднимите узел на машине (node-join.sh), затем введите его mesh-IP.</div>
  <div class="modalactions">
    <button id="fcancel" class="mini" data-i18n="cancel">Отмена</button>
    <button id="fsave" class="open" data-i18n="save">Сохранить</button>
  </div>
</div></div>
<div id="joinmodal" class="modal" hidden><div class="box">
  <h3 data-i18n="jointitle">Подключить машину</h3>
  <p class="hint" data-i18n="joinhint">Выполните эту одну строку на новой машине (без флагов). Пусто? Нажмите «Сгенерировать».</p>
  <pre id="joincmd" class="joincmd">{esc(invite_cmd)}</pre>
  <div class="modalactions">
    <button id="jgen" class="mini" data-i18n="jgenerate">Сгенерировать</button>
    <button id="jcopy" class="open" data-i18n="jcopy">Копировать</button>
    <button id="jclose" class="mini" data-i18n="cancel">Закрыть</button>
  </div>
  <div class="prov">
    <p class="hint" data-i18n="provhint">…или поднимите узел по SSH (машина должна быть достижима с хаба, root или passwordless-sudo):</p>
    <div class="row"><label>host</label><input id="p-host" placeholder="203.0.113.10"></div>
    <div class="row"><label>ssh user</label><input id="p-user" placeholder="root"></div>
    <div class="row"><label data-i18n="provpass">Пароль SSH</label><input id="p-pass" type="password" autocomplete="off"></div>
    <button id="pprov" class="mini" data-i18n="provbtn">Provision by SSH</button>
  </div>
</div></div>
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
            statuses = {}
            cur = {}
            changed = False
            for e in data.get("envs", []):
                st, ms, _ = check(e["ip"], e["port"])
                name = e["name"]
                if _since_status.get(name) != st:
                    _since_status[name] = st
                    _since[name] = time.time()
                    changed = True
                entry = {"status": st, "ms": ms, "since": _since.get(name, time.time())}
                if st == "online":
                    m = check_metrics(e["ip"], e.get("metrics_port", 9101))
                    for k in ("uptime", "cpu", "mem"):
                        if k in m:
                            entry[k] = m[k]
                statuses[name] = entry
                cur[name] = (st, ms)
            if changed:
                save_state()
            track_transitions(data.get("envs", []), cur)
            html = render(data, statuses, time.time())
            with _lock:
                _cache["html"] = html
                _cache["statuses"] = statuses
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
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/status.json":
            with _lock:
                payload = {"ts": _cache["ts"], "envs": _cache["statuses"]}
            self._send(200, "application/json", json.dumps(payload))
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
            self._send(200, "text/html; charset=utf-8", _cache["html"])
    def do_POST(self):
        path = self.path.split("?", 1)[0]
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
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
