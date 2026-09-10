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

LOGO_SVG = ('<svg width="52" height="52" viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">'
            '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
            '<stop offset="0" stop-color="#0a7ec2"/><stop offset="1" stop-color="#004a73"/></linearGradient></defs>'
            '<rect x="2" y="2" width="60" height="60" rx="14" fill="url(#g)"/>'
            '<path d="M20 18 V 44 H 46" stroke="#FFFFFF" stroke-width="8" stroke-linecap="round" fill="none"/>'
            '<circle cx="46" cy="22" r="5" fill="#F2994A"/></svg>')
FAVICON = "data:image/svg+xml;base64," + base64.b64encode(LOGO_SVG.encode()).decode()

_cache = {"html": "<body>loading</body>", "statuses": {}, "ts": 0}
_lock = threading.Lock()
_last_status = {}
_initialized = [False]
_ever_online = set()
PALETTE = ["#00679e", "#f2994a", "#0a7ec2", "#0a2540", "#d97b23"]

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
:root{--blue:#00679e;--blue2:#0a7ec2;--navy:#0a2540;--orange:#f2994a;--orange2:#d97b23;
  --ink:#0a1522;--muted:#54657a;--bg:#e7ecf1;--card:#ffffff;--card2:#f5f9fc;--line:#0a2540;--grid:rgba(10,37,64,.06);
  --ok:#0f9d58;--down:#e5484d;--hard:6px 6px 0 var(--line);--hard2:8px 8px 0 var(--line);
  --soft:0 14px 30px rgba(10,37,64,.14);--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
[data-theme="dark"]{--ink:#eef3f8;--muted:#93a6bb;--bg:#0b1016;--card:#141b23;--card2:#1a232e;--line:#f2994a;
  --blue:#2a9fd6;--blue2:#2a9fd6;--grid:rgba(255,255,255,.05);--ok:#37d67a;--down:#ff5c5c;
  --hard:6px 6px 0 #000;--hard2:8px 8px 0 #000;--soft:0 14px 30px rgba(0,0,0,.5)}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Inter,sans-serif;color:var(--ink);
  background-color:var(--bg);
  background-image:linear-gradient(var(--grid) 1px,transparent 1px),linear-gradient(90deg,var(--grid) 1px,transparent 1px);
  background-size:26px 26px;min-height:100vh;display:flex;flex-direction:column}
a{color:var(--blue2);text-decoration:none}
.wrap{width:100%;max-width:2400px;margin:0 auto;padding:20px 26px 40px;flex:1 0 auto;display:flex;flex-direction:column}
header{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:18px;
  background:linear-gradient(180deg,var(--card),var(--card2));border:2px solid var(--line);border-radius:6px;
  padding:14px 18px;box-shadow:var(--hard),var(--soft)}
.brand{display:flex;align-items:center;gap:14px}
.brand .name{font-size:26px;font-weight:900;text-transform:uppercase;letter-spacing:.02em;line-height:1}
.brand .name span{background:linear-gradient(90deg,#0a7ec2,#004a73);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.brand .sub{font-size:12px;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:.06em;margin-top:4px}
.ctrls{margin-left:auto;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.search{position:relative}
.search input{width:300px;max-width:60vw;padding:11px 14px 11px 38px;border:2px solid var(--line);
  border-radius:6px;background:var(--card);font-size:14px;color:var(--ink);outline:none;box-shadow:2px 2px 0 var(--line)}
.search input:focus{box-shadow:3px 3px 0 var(--line)}
.search svg{position:absolute;left:12px;top:12px;opacity:.7}
.iconbtn2{border:2px solid var(--line);background:linear-gradient(180deg,var(--card),var(--card2));color:var(--ink);
  border-radius:6px;padding:9px 12px;font-size:13px;font-weight:800;cursor:pointer;line-height:1;box-shadow:2px 2px 0 var(--line)}
.iconbtn2:hover{transform:translate(-1px,-1px);box-shadow:3px 3px 0 var(--line)}
.addbtn{border:2px solid var(--line);background:linear-gradient(180deg,#f7ac63,#f2994a);color:#0a1522;border-radius:6px;
  padding:11px 18px;font-weight:900;font-size:14px;cursor:pointer;text-transform:uppercase;letter-spacing:.03em;box-shadow:3px 3px 0 var(--line)}
.addbtn:hover{transform:translate(-1px,-1px);box-shadow:4px 4px 0 var(--line);background:linear-gradient(180deg,#f2994a,#d97b23)}
.filters{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:6px 0 18px}
.chipf{border:2px solid var(--line);background:linear-gradient(180deg,var(--card),var(--card2));color:var(--ink);border-radius:6px;
  padding:6px 13px;font-size:12px;font-weight:800;cursor:pointer;text-transform:uppercase;letter-spacing:.03em;box-shadow:2px 2px 0 var(--line)}
.chipf:hover{transform:translate(-1px,-1px);box-shadow:3px 3px 0 var(--line)}
.chipf.active{background:linear-gradient(180deg,#1a8fd6,#00679e);color:#fff}
.meta-line{color:var(--muted);font-size:12px;margin-left:auto;font-weight:700;text-transform:uppercase;letter-spacing:.04em}
h2.group{font-size:13px;text-transform:uppercase;letter-spacing:.1em;color:var(--ink);font-weight:900;
  margin:22px 0 12px;display:flex;align-items:center;gap:9px;cursor:pointer;user-select:none}
h2.group .dot{width:12px;height:12px;border-radius:2px;background:var(--orange);border:2px solid var(--line)}
h2.group .chev{margin-left:auto;font-size:11px;transition:transform .15s}
h2.group.collapsed .chev{transform:rotate(-90deg)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:20px}
.grid.collapsed{display:none}
.card{background:linear-gradient(180deg,var(--card),var(--card2));border:2px solid var(--line);border-radius:6px;padding:18px 18px 16px;
  box-shadow:var(--hard),var(--soft);transition:transform .1s,box-shadow .1s;position:relative}
.card:hover{transform:translate(-2px,-2px);box-shadow:var(--hard2),var(--soft)}
.top{display:flex;align-items:center;gap:8px;margin-bottom:12px}
.chip{color:#fff;font-size:11px;font-weight:800;padding:3px 8px;border-radius:4px;letter-spacing:.04em;
  text-transform:uppercase;background:var(--rc,#00679e);border:2px solid var(--line)}
.pill{margin-left:auto;display:inline-flex;align-items:center;gap:7px;font-size:11px;font-weight:800;
  padding:4px 9px;border-radius:4px;background:#e7f7ec;color:var(--ok);border:2px solid var(--line);text-transform:uppercase}
.pill.offline{background:#fdecec;color:var(--down)}
.pill .dot{width:8px;height:8px;border-radius:50%;background:currentColor}
.pill.online .dot{animation:pulse 1.8s infinite}
.pill .ms{color:var(--muted);font-weight:700}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(15,157,88,.55)}70%{box-shadow:0 0 0 6px rgba(15,157,88,0)}100%{box-shadow:0 0 0 0 rgba(15,157,88,0)}}
.title{font-size:20px;font-weight:900;text-transform:uppercase;letter-spacing:.01em}
.label{color:var(--muted);font-size:13px;margin:3px 0 10px;font-weight:600}
.kv{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12px;color:var(--muted);margin-bottom:14px}
.kv b{color:var(--ink);font-weight:800;font-family:var(--mono)}
.actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.open{display:inline-flex;align-items:center;gap:8px;background:linear-gradient(180deg,#1a8fd6,#00679e);color:#fff;font-weight:900;
  font-size:13px;padding:10px 16px;border-radius:6px;border:2px solid var(--line);text-transform:uppercase;
  letter-spacing:.03em;box-shadow:3px 3px 0 var(--line);transition:transform .1s,box-shadow .1s}
.open:hover{transform:translate(-1px,-1px);box-shadow:4px 4px 0 var(--line)}
.mini{border:2px solid var(--line);background:linear-gradient(180deg,var(--card),var(--card2));color:var(--ink);border-radius:6px;padding:8px 11px;
  font-size:11px;font-weight:800;cursor:pointer;text-transform:uppercase;letter-spacing:.03em;box-shadow:2px 2px 0 var(--line)}
.mini:hover{transform:translate(-1px,-1px);box-shadow:3px 3px 0 var(--line)}
.mini.del:hover{background:var(--down);color:#fff;border-color:var(--down)}
.aliases{margin-top:12px;font-size:12px;color:var(--muted);font-weight:600}
.aliases a{margin-right:12px}
.foot{color:var(--muted);font-size:12px;margin-top:auto;padding-top:30px;text-align:center;font-weight:800;
  text-transform:uppercase;letter-spacing:.08em}
.foot a{color:var(--blue2)}
.empty{color:var(--muted);padding:20px;font-weight:700}
.modal{position:fixed;inset:0;background:rgba(8,20,34,.6);display:flex;align-items:center;justify-content:center;z-index:50;padding:16px}
.modal[hidden]{display:none}
.box{background:var(--card);border:3px solid var(--line);border-radius:6px;padding:24px;width:min(540px,96vw);box-shadow:var(--hard2),var(--soft)}
.box h3{margin:0 0 16px;text-transform:uppercase;font-weight:900;letter-spacing:.03em}
.row{display:flex;flex-direction:column;gap:4px;margin-bottom:10px}
.row label{font-size:12px;color:var(--muted);font-weight:800;text-transform:uppercase;letter-spacing:.04em}
.row input{padding:10px 12px;border:2px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink);font-size:14px}
.row input:focus{outline:none;box-shadow:3px 3px 0 var(--line)}
.hint{font-size:12px;color:var(--muted);margin:8px 0 16px;font-weight:600}
.modalactions{display:flex;gap:10px;justify-content:flex-end}
.toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:linear-gradient(180deg,#f7ac63,#f2994a);color:#0a1522;
  border:2px solid var(--line);padding:12px 20px;border-radius:6px;font-size:14px;font-weight:800;z-index:60;box-shadow:4px 4px 0 var(--line)}
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
  apply(cur()); setTheme(localStorage.getItem('cn_theme')||'light');
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
            <a class="open" target="_blank" rel="noopener" href="{url}"><span data-i18n="open">Открыть</span> {esc(canon)}</a>
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
