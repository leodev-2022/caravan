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
REFRESH = int(os.environ.get("PORTAL_REFRESH", "10"))
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT", "")

LOGO_SVG = ('<svg width="44" height="44" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">'
            '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
            '<stop offset="0" stop-color="#ffb26b"/><stop offset="1" stop-color="#d97b23"/></linearGradient></defs>'
            '<rect x="2" y="2" width="60" height="60" rx="16" fill="url(#g)"/>'
            '<path d="M43 21a16 16 0 1 0 0 22" stroke="#20160a" stroke-width="7" stroke-linecap="round" fill="none"/></svg>')
FAVICON = "data:image/svg+xml;base64," + base64.b64encode(LOGO_SVG.encode()).decode()

_cache = {"html": "<body>loading</body>", "statuses": {}, "ts": 0}
_lock = threading.Lock()
_last_status = {}
_initialized = [False]
_ever_online = set()
PALETTE = ["#f2994a", "#5b9dff", "#34d399", "#c084fc", "#f472b6", "#22d3ee"]

def load_data():
    with open(NODES_JSON, encoding="utf-8") as f:
        return json.load(f)

def check(ip, port):
    t0 = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(f"http://{ip}:{port}/", method="GET"), timeout=2.5) as r:
            return "online", int((time.time() - t0) * 1000), r.status
    except Exception:
        return "offline", int((time.time() - t0) * 1000), None

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

def loc_color(loc):
    h = 0
    for ch in (loc or "?"):
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return PALETTE[h % len(PALETTE)]

CSS = """
:root{--accent:#f2994a;--accent2:#ffb26b;--accent-ink:#20160a;
  --bg:#0b0f14;--panel:#131922;--panel2:#0f151d;--line:#222c38;--line2:#303c4a;
  --ink:#e9eff7;--muted:#8a99ad;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --ok:#34d399;--down:#f87171;--radius:12px;--radius-sm:8px;
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
.pill{margin-left:auto;display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;
  padding:4px 10px;border-radius:999px;background:rgba(52,211,153,.14);color:var(--ok)}
.pill.offline{background:rgba(248,113,113,.14);color:var(--down)}
.pill .dot{width:7px;height:7px;border-radius:50%;background:currentColor}
.pill.online .dot{animation:pulse 2s infinite}
.pill .ms{color:var(--muted);font-weight:500}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(52,211,153,.5)}70%{box-shadow:0 0 0 5px rgba(52,211,153,0)}100%{box-shadow:0 0 0 0 rgba(52,211,153,0)}}
.title{font-size:16px;font-weight:700;letter-spacing:-.01em}
.label{color:var(--muted);font-size:13px;margin:2px 0 12px}
.kv{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12px;color:var(--muted);margin-bottom:14px}
.kv b{color:var(--ink);font-weight:600;font-family:var(--mono)}
.actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.open{display:inline-flex;align-items:center;gap:7px;background:var(--accent);color:var(--accent-ink);font-weight:700;
  font-size:13px;padding:9px 14px;border-radius:var(--radius-sm);border:1px solid transparent;transition:background .15s}
.open:hover{background:var(--accent2);text-decoration:none}
.mini{border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:var(--radius-sm);padding:8px 11px;
  font-size:12px;font-weight:600;cursor:pointer;transition:all .15s}
.mini:hover{color:var(--ink);border-color:var(--line2);background:var(--panel2)}
.mini.del:hover{color:#fff;background:var(--down);border-color:var(--down)}
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
        tags:"теги",all:"Все",add:"Добавить",addtitle:"Добавить окружение",edittitle:"Изменить окружение",flabel:"Метка",flocation:"Место",
        ftags:"Теги (через запятую)",faliases:"Алиасы (через запятую)",fhint:"Сначала поднимите узел на машине (node-join.sh), затем введите его mesh-IP.",
        save:"Сохранить",cancel:"Отмена",delete:"Удалить",edit:"Изменить",delconfirm:"Удалить окружение",applying:"Применяю… страница обновится",empty:"Ничего не найдено"},
    en:{filter:"Filter: name, location, tag… (press /)",updated:"updated",autorefresh:"auto-refresh",
        envs:"environments",open:"Open",copyurl:"copy URL",copyip:"copy IP",copied:"copied",
        tags:"tags",all:"All",add:"Add",addtitle:"Add environment",edittitle:"Edit environment",flabel:"Label",flocation:"Location",
        ftags:"Tags (comma-separated)",faliases:"Aliases (comma-separated)",fhint:"First onboard the machine (node-join.sh), then enter its mesh IP.",
        save:"Save",cancel:"Cancel",delete:"Delete",edit:"Edit",delconfirm:"Delete environment",applying:"Applying… page will refresh",empty:"Nothing found"}
  };
  function cur(){return localStorage.getItem('cn_lang')||'ru';}
  var locFilter='all';
  function apply(l){
    localStorage.setItem('cn_lang',l); document.documentElement.lang=l;
    document.querySelectorAll('[data-i18n]').forEach(function(el){var k=el.getAttribute('data-i18n'); if(I18N[l][k]!=null) el.textContent=I18N[l][k];});
    document.querySelectorAll('[data-i18n-ph]').forEach(function(el){var k=el.getAttribute('data-i18n-ph'); if(I18N[l][k]!=null) el.placeholder=I18N[l][k];});
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
    if(b){navigator.clipboard.writeText(b.getAttribute('data-copy')).then(function(){
      var k=b.getAttribute('data-i18n'); var old=b.textContent; b.textContent=I18N[cur()].copied;
      setTimeout(function(){ b.textContent = k?I18N[cur()][k]:old; },900);}); return;}
    var t=e.target.closest('#langtoggle'); if(t){apply(cur()==='ru'?'en':'ru'); return;}
    var th=e.target.closest('#themebtn'); if(th){var c=document.documentElement.getAttribute('data-theme');setTheme(c==='dark'?'light':'dark');return;}
    var ad=e.target.closest('#addbtn'); if(ad){openModal({});return;}
    var ed=e.target.closest('[data-edit]'); if(ed){ var c=ed.closest('.card');
      openModal({name:c.getAttribute('data-name'),ip:c.getAttribute('data-ip'),port:c.getAttribute('data-port'),
        label:c.getAttribute('data-label'),location:c.getAttribute('data-location'),
        tags:(c.getAttribute('data-tags')||'').split(',').map(function(s){return s.trim();}).filter(Boolean),
        aliases:(c.getAttribute('data-aliases')||'').split(',').map(function(s){return s.trim();}).filter(Boolean)}); return;}
    var cx=e.target.closest('#fcancel'); if(cx){document.getElementById('modal').hidden=true;return;}
    var sv=e.target.closest('#fsave'); if(sv){
      var v=function(id){return (document.getElementById(id).value||'').trim();};
      var env={name:v('f-name'),ip:v('f-ip'),port:parseInt(v('f-port')||'9898',10)||9898,
        label:v('f-label'),location:v('f-location'),
        tags:v('f-tags').split(',').map(function(s){return s.trim();}).filter(Boolean),
        aliases:v('f-aliases').split(',').map(function(s){return s.trim();}).filter(Boolean)};
      if(!env.name||!env.ip){alert('name & mesh IP required');return;}
      post({action:'add',env:env},function(){ toast(I18N[cur()].applying); setTimeout(function(){location.reload();},9000); });
      return;}
    var del=e.target.closest('[data-del]'); if(del){
      if(confirm(I18N[cur()].delconfirm+' '+del.getAttribute('data-del')+'?')){
        post({action:'delete',name:del.getAttribute('data-del')},function(){ toast(I18N[cur()].applying); setTimeout(function(){location.reload();},9000); });}
      return;}
  });
  document.addEventListener('keydown',function(e){
    if(e.key==='/'&&document.activeElement&&document.activeElement.id!=='q'){e.preventDefault();document.getElementById('q').focus();}
    if(e.key==='Escape'){var m=document.getElementById('modal'); if(m) m.hidden=true;}
  });
  apply(cur()); setTheme(localStorage.getItem('cn_theme')||'dark');
  setInterval(poll,REFRESH); poll();
})();
"""

def render(data, statuses, ts):
    domain = data.get("domain", "")
    envs = data.get("envs", [])
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
            alias_html = "".join(f'<a target="_blank" rel="noopener" href="https://{esc(a)}.{esc(domain)}/">{esc(a)}.{esc(domain)}</a>' for a in aliases)
            search = f"{name} {e.get('label','')} {loc} {' '.join(e.get('tags',[]))}".lower()
            tags = ", ".join(esc(t) for t in e.get("tags", []))
            cards.append(f"""
        <div class="card" data-search="{esc(search)}" data-location="{esc(loc)}" style="--rc:{lcol}"
             data-name="{esc(name)}" data-ip="{esc(e['ip'])}" data-port="{esc(e['port'])}" data-label="{esc(e.get('label',''))}"
             data-tags="{esc(','.join(e.get('tags',[])))}" data-aliases="{esc(','.join(aliases))}">
          <div class="top">
            <span class="chip">{esc(loc)}</span>
            <span class="pill {'online' if onl else 'offline'}" id="st-{esc(name)}">
              <span class="dot"></span><span class="txt">{st['status']}</span><span class="ms">{st['ms']} ms</span>
            </span>
          </div>
          <div class="title">{esc(name)}</div>
          <div class="label">{esc(e.get('label', name))}</div>
          <div class="kv">
            <span>mesh <b>{esc(e['ip'])}:{esc(e['port'])}</b></span>
            {'<span><span data-i18n="tags">теги</span> <b>'+esc(tags)+'</b></span>' if tags else ''}
          </div>
          <div class="actions">
            <a class="open" target="_blank" rel="noopener" href="{url}"><span data-i18n="open">Открыть</span> &rarr;</a>
            <button class="mini" data-copy="{url}" data-i18n="copyurl">копировать URL</button>
            <button class="mini" data-edit="1" data-i18n="edit">Изменить</button>
            <button class="mini del" data-del="{esc(name)}" data-i18n="delete">Удалить</button>
          </div>
          {f'<div class="aliases">{alias_html}</div>' if alias_html else ''}
        </div>""")
        sections.append(f'<div class="groupwrap"><h2 class="group"><span class="dot"></span>{esc(loc)}<span class="chev">▾</span></h2><div class="grid">{"".join(cards)}</div></div>')
    body = "".join(sections) if sections else '<div class="empty" data-i18n="empty">Ничего не найдено</div>'
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" type="image/svg+xml" href="{FAVICON}">
<title>Caravan</title><style>{CSS}</style></head><body>
<div class="wrap">
  <header>
    <div class="brand">{LOGO_SVG}
      <div><div class="name">Cara<span>van</span></div>
      <div class="sub">{len(envs)} <span data-i18n="envs">окружений</span></div></div>
    </div>
    <div class="ctrls">
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
  <div class="hint" data-i18n="fhint">Сначала поднимите узел на машине (node-join.sh), затем введите его mesh-IP.</div>
  <div class="modalactions">
    <button id="fcancel" class="mini" data-i18n="cancel">Отмена</button>
    <button id="fsave" class="open" data-i18n="save">Сохранить</button>
  </div>
</div></div>
<script>{JS.replace('__REFRESH__', str(REFRESH))}</script>
</body></html>"""

def refresh_loop():
    while True:
        try:
            data = load_data()
            statuses = {}
            cur = {}
            for e in data.get("envs", []):
                st, ms, _ = check(e["ip"], e["port"])
                statuses[e["name"]] = {"status": st, "ms": ms}
                cur[e["name"]] = (st, ms)
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
            self._send(200, "application/json", '{"ok":true}')
        except Exception as e:
            self._send(400, "application/json", json.dumps({"error": str(e)}))
    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    threading.Thread(target=refresh_loop, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
