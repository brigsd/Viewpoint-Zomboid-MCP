#!/usr/bin/env python3
"""Gera o visualizador local do acervo: data/viewer/index.html (abre direto do disco, sem servidor).

Estrutura (tudo em data/viewer/, fora do git; as imagens sao as de data/sprites, data/depth e data/align):
    index.html        pagina unica (CSS e JS embutidos)
    catalog.js        indice compacto de todos os tiles (~2 MB): [nome, tileset, idx, categoria, flags]
    d/<n>.js          detalhes de um tileset (propriedades, geometria, mapa de profundidade), carregado ao abrir um tile

A grade e paginada (120 por pagina) e as miniaturas usam loading="lazy", entao ~40 mil entradas continuam fluidas.
Filtros: categoria, tileset, busca por nome (varias palavras = E), so com imagem / geometria / profundidade / sem imagem.

Uso: python viewer.py [--data-dir DIR] [--open]
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import extract_textures  # noqa: E402
import report_missing  # noqa: E402

CATEGORY_LABELS = {
    "moveis": "Móveis", "eletrodomesticos": "Eletrodomésticos", "containers": "Contêineres",
    "cozinha": "Cozinha", "banheiro": "Banheiro", "iluminacao": "Iluminação", "decoracao": "Decoração",
    "construcao": "Construção", "portas_janelas": "Portas e janelas", "vegetacao": "Vegetação", "outros": "Outros",
}
CATEGORY_ORDER = ["moveis", "eletrodomesticos", "containers", "cozinha", "banheiro", "iluminacao", "decoracao",
                  "construcao", "portas_janelas", "vegetacao", "outros"]
REASON_TEXT = {
    "lit_so_geometria": "Variante acesa (_on): só existe na geometria/atribuições de profundidade; o jogo reaproveita o sprite base.",
    "lit_definida": "Variante acesa (_on) definida nos .tiles, mas nenhum pack tem a imagem.",
    "tileset_sem_sprite": "Nenhum pack traz imagem para este tileset inteiro (o tileset tem mapas de profundidade, mas nenhum sprite de cor).",
    "indice_alem_pack": "A definição lista mais índices do que o pack fornece para este tileset.",
    "lacuna_no_pack": "O pack tem índices maiores deste tileset, mas não este.",
    "sem_definicao": "Só aparece em tileGeometry/profundidade: sem definição nos .tiles e sem imagem.",
}
F_PNG, F_GEO, F_DEP, F_DEPA, F_DEF, F_LIT = 1, 2, 4, 8, 16, 32


def _natkey(t):
    return (t[1], t[2])


def build(data_dir, out_dir=None) -> dict:
    """Le acervo.sqlite e grava data/viewer/{index.html,catalog.js,d/*.js}. Devolve contagens."""
    t0 = time.time()
    data_dir = Path(data_dir)
    out = Path(out_dir) if out_dir else data_dir / "viewer"
    (out / "d").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(data_dir / "acervo.sqlite")

    sprites = {r[0]: r[1:] for r in conn.execute(
        "SELECT name, png, width, height, offset_x, offset_y, scale, frame_w, frame_h, pack FROM sprites")}
    geo_n = dict(conn.execute("SELECT name, COUNT(*) FROM geometry GROUP BY name"))
    depth_own = {r[0]: r[1] for r in conn.execute("SELECT name, png FROM depth_maps")}
    assigned = dict(conn.execute("SELECT name, depth FROM depth_assignments"))
    miss_reason = {x["name"]: x["reason"] for x in report_missing.classify(conn)}
    reasons = list(report_missing.REASONS)

    tiles = conn.execute("SELECT name, tileset, idx, COALESCE(category,'outros'), COALESCE(source,'') FROM tiles").fetchall()
    tiles.sort(key=_natkey)
    tileset_names = sorted({t[1] for t in tiles})
    ts_index = {n: i for i, n in enumerate(tileset_names)}
    cats_present = {t[3] for t in tiles}
    cat_ids = [c for c in CATEGORY_ORDER if c in cats_present] + sorted(cats_present - set(CATEGORY_ORDER))
    cat_index = {c: i for i, c in enumerate(cat_ids)}
    align_dir = data_dir / "align"
    align = sorted(p.stem for p in align_dir.glob("*.png") if not p.stem.endswith("_lado_a_lado") and p.stem != "painel") \
        if align_dir.is_dir() else []

    rows, ov = [], {}
    for name, ts, idx, cat, src in tiles:
        fl = 0
        if name in sprites:
            fl |= F_PNG
            default = extract_textures.sprite_relpath(name)
            if sprites[name][0] != default:
                ov[name] = sprites[name][0]
        if geo_n.get(name):
            fl |= F_GEO
        if name in depth_own:
            fl |= F_DEP
        elif assigned.get(name) in depth_own:
            fl |= F_DEPA
        if report_missing.is_definition(src):
            fl |= F_DEF
        if report_missing.LIT_RE.search(ts):
            fl |= F_LIT
        rows.append([name, ts_index[ts], idx, cat_index[cat], fl])

    catalog = {
        "gerado": time.strftime("%Y-%m-%d %H:%M"),
        "cats": [[c, CATEGORY_LABELS.get(c, c)] for c in cat_ids],
        "ts": tileset_names,
        "t": rows,
        "ov": ov,
        "al": align,
        "motivos": {k: REASON_TEXT[k] for k in reasons},
        "falta": {n: r for n, r in miss_reason.items()},
    }
    (out / "catalog.js").write_text(
        "window.CAT=" + json.dumps(catalog, ensure_ascii=False, separators=(",", ":")) + ";", encoding="utf-8")

    # detalhes por tileset
    props: dict[str, list] = {}
    for n, k, v in conn.execute("SELECT name, key, value FROM tile_props"):
        props.setdefault(n, []).append([k, v])
    gprops: dict[str, list] = {}
    for n, k, v in conn.execute("SELECT name, key, value FROM geometry_props"):
        gprops.setdefault(n, []).append([k, v])
    geom: dict[str, list] = {}
    for r in conn.execute("""SELECT name, shape, tx, ty, tz, rx, ry, rz, min_x, min_y, min_z, max_x, max_y, max_z, raw
                             FROM geometry ORDER BY name, shape_idx"""):
        geom.setdefault(r[0], []).append([r[1]] + [None if v is None else (int(v) if float(v).is_integer() else v) for v in r[2:14]] + [r[14]])
    srcs = {t[0]: t[4] for t in tiles}
    per_ts: dict[int, dict] = {}
    for name, ts, idx, cat, src in tiles:
        rec: dict = {}
        if name in props:
            rec["p"] = props[name]
        if name in geom:
            rec["g"] = geom[name]
        if name in gprops:
            rec["gp"] = gprops[name]
        if src:
            rec["s"] = srcs[name]
        sp = sprites.get(name)
        if sp:
            rec["o"] = [sp[1], sp[2], sp[3], sp[4], sp[5], sp[6], sp[7], sp[8]]   # w,h,ox,oy,scale,fw,fh,pack
        da = assigned.get(name)
        if da:
            rec["da"] = da
        if name in depth_own:
            rec["dp"] = [depth_own[name], name]
        elif da in depth_own:
            rec["dp"] = [depth_own[da], da]
        per_ts.setdefault(ts_index[ts], {})[name] = rec
    for i, recs in per_ts.items():
        body = json.dumps(recs, ensure_ascii=False, separators=(",", ":"))
        (out / "d" / f"{i}.js").write_text(
            "window.__D=window.__D||{};window.__D[" + json.dumps(tileset_names[i]) + "]=" + body + ";", encoding="utf-8")

    (out / "index.html").write_text(TEMPLATE, encoding="utf-8")
    conn.close()
    return {"tiles": len(rows), "tilesets": len(tileset_names), "with_png": sum(1 for r in rows if r[4] & F_PNG),
            "with_geometry": sum(1 for r in rows if r[4] & F_GEO),
            "with_depth": sum(1 for r in rows if r[4] & (F_DEP | F_DEPA)),
            "align_images": len(align), "catalog_bytes": (out / "catalog.js").stat().st_size,
            "html": str(out / "index.html"), "seconds": round(time.time() - t0, 1)}


TEMPLATE = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Acervo de objetos do jogo</title>
<style>
:root{--bg:#15171a;--panel:#1d2025;--panel2:#252a31;--line:#323842;--fg:#e6e8eb;--mute:#9aa3ad;--acc:#4da3ff;--ok:#4cc38a;--warn:#e5b44b;--bad:#e5645b;--chk1:#2a2e34;--chk2:#23272c}
@media (prefers-color-scheme:light){:root{--bg:#f3f4f6;--panel:#fff;--panel2:#eceef1;--line:#d4d8de;--fg:#1c2128;--mute:#5d6672;--acc:#0a66d1;--ok:#17814f;--warn:#9a6b00;--bad:#c4362d;--chk1:#e4e6ea;--chk2:#d9dce1}}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,Segoe UI,Roboto,sans-serif}
header{display:flex;flex-wrap:wrap;gap:10px 16px;align-items:center;padding:10px 16px;background:var(--panel);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
h1{font-size:16px;margin:0;font-weight:600}
.sub{color:var(--mute);font-size:12px}
input[type=search],input[type=text],select{background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px 9px;font:inherit}
input[type=search]{width:260px;max-width:100%}
#ts{width:250px}
label.chk{display:inline-flex;gap:5px;align-items:center;color:var(--mute);cursor:pointer;user-select:none}
.chips{display:flex;flex-wrap:wrap;gap:6px;padding:10px 16px 0}
.chip{background:var(--panel2);border:1px solid var(--line);border-radius:999px;padding:3px 11px;cursor:pointer;color:var(--fg);font:inherit;font-size:13px}
.chip small{color:var(--mute);margin-left:4px}
.chip[aria-pressed=true]{background:var(--acc);border-color:var(--acc);color:#fff}
.chip[aria-pressed=true] small{color:#dbeaff}
.bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:10px 16px}
button{background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:5px 11px;font:inherit;cursor:pointer}
button:hover:not(:disabled){border-color:var(--acc)}
button:disabled{opacity:.4;cursor:default}
main{padding:0 16px 40px}
#grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(132px,1fr));gap:10px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;overflow:hidden;cursor:pointer;display:flex;flex-direction:column}
.card:hover,.card:focus-visible{border-color:var(--acc);outline:none}
.card.sel{border-color:var(--warn)}
.thumb{height:150px;display:flex;align-items:center;justify-content:center;background:conic-gradient(var(--chk1) 25%,var(--chk2) 0 50%,var(--chk1) 0 75%,var(--chk2) 0) 0 0/16px 16px;position:relative}
.thumb img{max-width:100%;max-height:100%;image-rendering:pixelated}
.thumb .none{color:var(--mute);font-size:11px;text-align:center;padding:6px}
.badges{position:absolute;right:3px;top:3px;display:flex;gap:3px}
.b{font-size:10px;font-weight:700;border-radius:3px;padding:0 4px;background:#000a;color:#fff}
.b.g{background:#18805a}.b.d{background:#2a62b0}
.nm{padding:5px 7px;font-size:11.5px;word-break:break-all;color:var(--mute)}
.empty{padding:40px;text-align:center;color:var(--mute)}
#panel{position:fixed;top:0;right:0;bottom:0;width:min(640px,100%);background:var(--panel);border-left:1px solid var(--line);z-index:10;display:none;flex-direction:column;box-shadow:-8px 0 24px #0006}
#panel.open{display:flex}
#ph{display:flex;gap:8px;align-items:center;padding:10px 14px;border-bottom:1px solid var(--line)}
#ph h2{font-size:15px;margin:0;flex:1;word-break:break-all}
#pb{overflow:auto;padding:12px 14px 30px;flex:1}
.views{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.view{background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:8px}
.view h3{margin:0 0 6px;font-size:12px;color:var(--mute);font-weight:600}
.view canvas,.view img{display:block;image-rendering:pixelated;background:conic-gradient(var(--chk1) 25%,var(--chk2) 0 50%,var(--chk1) 0 75%,var(--chk2) 0) 0 0/16px 16px}
table{border-collapse:collapse;width:100%;font-size:12.5px}
th,td{text-align:left;padding:3px 8px;border-bottom:1px solid var(--line);vertical-align:top;word-break:break-word}
th{color:var(--mute);font-weight:600;width:38%}
td.num{font-variant-numeric:tabular-nums}
.sec{margin:16px 0 6px;font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:var(--mute)}
.note{color:var(--mute);font-size:12px;margin:4px 0}
.warn{color:var(--warn)}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px}
a{color:var(--acc)}
@media (max-width:720px){input[type=search],#ts{width:100%}.thumb{height:120px}}
</style>
</head>
<body>
<header>
  <div><h1>Acervo de objetos do jogo</h1><div class="sub" id="sub">carregando…</div></div>
  <input type="search" id="q" placeholder="Buscar por nome (ex.: fridge 01)" aria-label="Buscar por nome" autocomplete="off">
  <input type="text" id="ts" list="tslist" placeholder="Tileset (todos)" aria-label="Tileset" autocomplete="off">
  <datalist id="tslist"></datalist>
  <label class="chk"><input type="checkbox" id="fPng"> só com imagem</label>
  <label class="chk"><input type="checkbox" id="fGeo"> só com geometria</label>
  <label class="chk"><input type="checkbox" id="fDep"> só com profundidade</label>
  <label class="chk"><input type="checkbox" id="fMiss"> só sem imagem</label>
</header>
<div class="chips" id="chips" role="group" aria-label="Categorias"></div>
<div class="bar">
  <button id="prev">‹ Anterior</button>
  <span id="pg" class="sub"></span>
  <button id="next">Próxima ›</button>
  <select id="ps" aria-label="Itens por página"><option>60</option><option selected>120</option><option>240</option></select>
  <span class="sub" id="cnt"></span>
  <button id="clr">Limpar filtros</button>
</div>
<main><div id="grid"></div></main>

<aside id="panel" aria-label="Detalhes do objeto">
  <div id="ph">
    <button id="dprev" title="Anterior (←)">‹</button><button id="dnext" title="Próximo (→)">›</button>
    <h2 id="pt"></h2>
    <button id="pcopy" title="Copiar o nome">Copiar nome</button>
    <button id="pclose" title="Fechar (Esc)">✕</button>
  </div>
  <div id="pb"></div>
</aside>

<script src="catalog.js"></script>
<script>
(function(){
'use strict';
var CAT=window.CAT;
if(!CAT){document.getElementById('sub').textContent='catalog.js não encontrado: rode viewer.py de novo.';return;}
var F={PNG:1,GEO:2,DEP:4,DEPA:8,DEF:16,LIT:32};
var SAFE=/[<>:"\/\\|?*\x00-\x1f]/g;
function safe(s){return s.replace(SAFE,'_');}
function spritePath(r){return '../'+(CAT.ov[r[0]]||('sprites/'+safe(CAT.ts[r[1]])+'/'+safe(r[0])+'.png'));}
function $(id){return document.getElementById(id);}
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
var T=CAT.t, st={cat:-1,ts:-1,q:'',png:false,geo:false,dep:false,miss:false,page:0,ps:120}, list=[], catCount=[], sel=-1;
var alSet={}; CAT.al.forEach(function(n){alSet[n]=1;});
var tsIdx={}; CAT.ts.forEach(function(n,i){tsIdx[n]=i;});

// ---- filtros
function apply(){
  var terms=st.q.toLowerCase().split(/\s+/).filter(Boolean), out=[], cc=new Array(CAT.cats.length).fill(0);
  for(var i=0;i<T.length;i++){
    var r=T[i], f=r[4];
    if(st.ts>=0&&r[1]!==st.ts)continue;
    if(st.png&&!(f&F.PNG))continue;
    if(st.miss&&(f&F.PNG))continue;
    if(st.geo&&!(f&F.GEO))continue;
    if(st.dep&&!(f&(F.DEP|F.DEPA)))continue;
    if(terms.length){var nm=r[0].toLowerCase(),ok=true;for(var k=0;k<terms.length;k++){if(nm.indexOf(terms[k])<0){ok=false;break;}}if(!ok)continue;}
    cc[r[3]]++;
    if(st.cat>=0&&r[3]!==st.cat)continue;
    out.push(i);
  }
  list=out; catCount=cc;
  var pages=Math.max(1,Math.ceil(list.length/st.ps)); if(st.page>=pages)st.page=pages-1;
  renderChips(); renderGrid();
}
function renderChips(){
  var tot=catCount.reduce(function(a,b){return a+b;},0), h='<button class="chip" aria-pressed="'+(st.cat<0)+'" data-c="-1">Todas<small>'+tot+'</small></button>';
  CAT.cats.forEach(function(c,i){h+='<button class="chip" aria-pressed="'+(st.cat===i)+'" data-c="'+i+'">'+esc(c[1])+'<small>'+catCount[i]+'</small></button>';});
  $('chips').innerHTML=h;
}
function renderGrid(){
  var a=st.page*st.ps, b=Math.min(list.length,a+st.ps), h=[];
  for(var k=a;k<b;k++){
    var r=T[list[k]], f=r[4], img;
    if(f&F.PNG) img='<img loading="lazy" decoding="async" alt="" src="'+esc(spritePath(r))+'">';
    else img='<div class="none">sem imagem'+((f&F.LIT)?'<br>(variante acesa)':'')+'</div>';
    var bd=''; if(f&F.GEO)bd+='<span class="b g" title="tem geometria 3D">3D</span>'; if(f&(F.DEP|F.DEPA))bd+='<span class="b d" title="tem mapa de profundidade">P</span>';
    h.push('<div class="card'+(list[k]===sel?' sel':'')+'" tabindex="0" data-i="'+list[k]+'" title="'+esc(r[0])+'"><div class="thumb">'+img+'<div class="badges">'+bd+'</div></div><div class="nm">'+esc(r[0])+'</div></div>');
  }
  $('grid').innerHTML=h.length?h.join(''):'<div class="empty">Nenhum objeto com esses filtros.</div>';
  var pages=Math.max(1,Math.ceil(list.length/st.ps));
  $('pg').textContent='Página '+(st.page+1)+' de '+pages;
  $('cnt').textContent=list.length+' objetos';
  $('prev').disabled=st.page<=0; $('next').disabled=st.page>=pages-1;
}
function setPage(p){st.page=p;renderGrid();window.scrollTo(0,0);}

// ---- geometria -> tela (mesma projecao do align_check.py)
var K=0.0064, H=0.8660254*128/Math.SQRT2/10000, OX=64, OY=224;
function proj(p){return [OX+K*(p[0]-p[2]), OY+K/2*(p[0]+p[2])-H*p[1]];}
function rot(rx,ry,rz){
  var d=Math.PI/180/10000; rx*=d;ry*=d;rz*=d;
  var Rx=[[1,0,0],[0,Math.cos(rx),-Math.sin(rx)],[0,Math.sin(rx),Math.cos(rx)]],
      Ry=[[Math.cos(ry),0,Math.sin(ry)],[0,1,0],[-Math.sin(ry),0,Math.cos(ry)]],
      Rz=[[Math.cos(rz),-Math.sin(rz),0],[Math.sin(rz),Math.cos(rz),0],[0,0,1]];
  return mul(mul(Rx,Ry),Rz);
}
function mul(A,B){var C=[[0,0,0],[0,0,0],[0,0,0]];for(var i=0;i<3;i++)for(var j=0;j<3;j++)for(var k=0;k<3;k++)C[i][j]+=A[i][k]*B[k][j];return C;}
function xf(R,t,p){return [R[0][0]*p[0]+R[0][1]*p[1]+R[0][2]*p[2]+t[0],R[1][0]*p[0]+R[1][1]*p[1]+R[1][2]*p[2]+t[1],R[2][0]*p[0]+R[2][1]*p[1]+R[2][2]*p[2]+t[2]];}
function num(raw,key){var m=new RegExp(key+'\\s*=\\s*(-?[\\d.]+)').exec(raw||'');return m?parseFloat(m[1]):0;}
// g = [shape,tx,ty,tz,rx,ry,rz,x0,y0,z0,x1,y1,z1,raw] -> lista de polilinhas 3D
function shapeLines(g){
  var R=rot(g[4]||0,g[5]||0,g[6]||0), t=[g[1]||0,g[2]||0,g[3]||0], L=[], i, j;
  if(g[0]==='box'&&g[7]!=null){
    var c=[]; for(i=0;i<8;i++)c.push(xf(R,t,[(i&4)?g[10]:g[7],(i&2)?g[11]:g[8],(i&1)?g[12]:g[9]]));
    for(i=0;i<8;i++)for(j=i+1;j<8;j++){var x=i^j;if(x===1||x===2||x===4)L.push([c[i],c[j]]);}
  }else if(g[0]==='cylinder'){
    var r1=num(g[13],'radius1'),r2=num(g[13],'radius2'),hh=num(g[13],'height'),a=[],b=[],n=28;
    for(i=0;i<n;i++){var th=2*Math.PI*i/n;a.push(xf(R,t,[r1*Math.cos(th),r1*Math.sin(th),-hh/2]));b.push(xf(R,t,[r2*Math.cos(th),r2*Math.sin(th),hh/2]));}
    a.push(a[0]);b.push(b[0]);L.push(a,b);for(i=0;i<n;i+=7)L.push([a[i],b[i]]);
  }else if(g[0]==='polygon'){
    var pl=/plane\s*=\s*(\w+)/.exec(g[13]||''), pm=/points\s*=\s*([^\n]+)/.exec(g[13]||'');
    if(pm){var pts=pm[1].replace(/[,\s]+/g,' ').trim().split(' ').filter(function(s){return s.indexOf('x')>0;}).map(function(s){var q=s.split('x');return [parseFloat(q[0]),parseFloat(q[1])];});
      var pn=pl?pl[1]:'XY', P=pts.map(function(q){return pn==='XZ'?[q[0],0,q[1]]:pn==='YZ'?[0,q[0],q[1]]:[q[0],q[1],0];}).map(function(p){return xf(R,t,p);});
      if(P.length>2){P.push(P[0]);L.push(P);}}
  }
  return L;
}
var COLORS=['#ff4040','#40ff40','#40a0ff','#ffdc00','#ff00ff','#00ffff','#ff8c00','#a064ff'];

// ---- detalhes
var chunks={};
function loadChunk(i){
  return new Promise(function(res){
    if(chunks[i])return res(chunks[i]);
    var s=document.createElement('script'); s.src='d/'+i+'.js';
    s.onload=function(){chunks[i]=(window.__D&&window.__D[CAT.ts[i]])||{};res(chunks[i]);};
    s.onerror=function(){chunks[i]={};res({});};
    document.head.appendChild(s);
  });
}
var curToken=0;
function open(i){
  sel=i; var r=T[i], tok=++curToken;
  $('panel').classList.add('open'); $('pt').textContent=r[0]; location.hash=encodeURIComponent(r[0]);
  $('pb').innerHTML='<p class="note">carregando…</p>';
  Array.prototype.forEach.call(document.querySelectorAll('.card.sel'),function(e){e.classList.remove('sel');});
  var cd=document.querySelector('.card[data-i="'+i+'"]'); if(cd)cd.classList.add('sel');
  loadChunk(r[1]).then(function(ch){ if(tok===curToken)renderDetail(r,ch[r[0]]||{}); });
}
function kv(rows){return '<table>'+rows.map(function(x){return '<tr><th>'+esc(x[0])+'</th><td>'+esc(x[1])+'</td></tr>';}).join('')+'</table>';}
function renderDetail(r,d){
  var f=r[4], h='', S=3, cat=CAT.cats[r[3]][1], o=d.o;
  h+='<div class="views">';
  if(f&F.PNG&&o){
    h+='<div class="view"><h3>Sprite no quadro cheio'+((d.g&&d.g.length)?' + geometria':'')+'</h3><canvas id="cv" width="'+128*S+'" height="'+256*S+'"></canvas>'
      +'<div class="note"><label class="chk"><input type="checkbox" id="tg" '+((d.g&&d.g.length)?'checked':'disabled')+'> geometria</label> <label class="chk"><input type="checkbox" id="td" checked> losango do tile</label></div></div>';
  }else{
    h+='<div class="view"><h3>Sprite</h3><div class="note warn">Sem imagem.</div><div class="note">'+esc(CAT.motivos[CAT.falta[r[0]]]||'Motivo não classificado.')+'</div></div>';
  }
  if(d.dp){
    h+='<div class="view"><h3>Profundidade'+(d.dp[1]!==r[0]?' (de '+esc(d.dp[1])+')':'')+'</h3><img id="dimg" width="'+128*S+'" height="'+256*S+'" src="../'+esc(d.dp[0])+'" alt="mapa de profundidade">'
      +'<div class="note">Escuro = mais perto da câmera (cinza = 190 − K·(X+Z) − ⅔·H·Y).</div></div>';
  }
  h+='</div>';
  if(alSet[r[0]])h+='<div class="sec">Prova de alinhamento</div><a href="../align/'+esc(r[0])+'.png" target="_blank"><img style="max-width:100%;border:1px solid var(--line);border-radius:6px" src="../align/'+esc(r[0])+'.png" alt="geometria sobre o sprite"></a>'
    +'<p class="note"><a href="../align/'+esc(r[0])+'_lado_a_lado.png" target="_blank">cor | profundidade | profundidade + geometria</a></p>';
  h+='<div class="sec">Resumo</div>'+kv([['Tileset',CAT.ts[r[1]]],['Índice',r[2]],['Categoria',cat],['Definido em',d.s||'—'],
     ['Imagem',(f&F.PNG&&o)?o[0]+'×'+o[1]+' px, recorte em ('+o[2]+','+o[3]+') do quadro '+o[5]+'×'+o[6]+', escala '+o[4]+'x, '+o[7]:'não'],
     ['Geometria',(d.g&&d.g.length)?d.g.length+' forma(s)':'não'],
     ['Profundidade',d.dp?(d.dp[1]===r[0]?'mapa próprio':'atribuído: '+d.dp[1]):(d.da?'atribuído a '+d.da+' (sem mapa)':'não')]]);
  if(d.g&&d.g.length){
    h+='<div class="sec">Formas da geometria (1/10000 de tile; Y = altura)</div><table><tr><th>#</th><th>forma</th><th>translate</th><th>rotate</th><th>min</th><th>max / dados</th></tr>';
    d.g.forEach(function(g,k){
      var det=g[0]==='box'?[g[10],g[11],g[12]].join(' × '):'<span class="note">'+esc((g[13]||'').replace(/\s+/g,' ').slice(0,160))+'</span>';
      h+='<tr><td style="width:auto"><span class="sw" style="background:'+COLORS[k%COLORS.length]+'"></span>'+k+'</td><td>'+esc(g[0])+'</td><td class="num">'+[g[1],g[2],g[3]].join(', ')+'</td><td class="num">'+[g[4],g[5],g[6]].join(', ')+'</td><td class="num">'+(g[7]!=null?[g[7],g[8],g[9]].join(', '):'')+'</td><td class="num">'+det+'</td></tr>';});
    h+='</table>';
    if(d.gp&&d.gp.length)h+='<div class="sec">Propriedades da geometria</div>'+kv(d.gp);
  }
  if(d.p&&d.p.length)h+='<div class="sec">Propriedades do tile ('+d.p.length+')</div>'+kv(d.p);
  $('pb').innerHTML=h;
  if(f&F.PNG&&o)drawCanvas(d,o,S);
  if($('tg'))$('tg').onchange=function(){drawCanvas(d,o,S);};
  if($('td'))$('td').onchange=function(){drawCanvas(d,o,S);};
  $('dprev').disabled=!neighbor(-1); $('dnext').disabled=!neighbor(1);
}
function drawCanvas(d,o,S){
  var cv=$('cv'); if(!cv)return; var c=cv.getContext('2d'); c.imageSmoothingEnabled=false; c.clearRect(0,0,cv.width,cv.height);
  var r=T[sel], img=new Image();
  img.onload=function(){
    if(T[sel]!==r)return;
    c.clearRect(0,0,cv.width,cv.height);
    var fz=(o[4]===1?2:1)*S;
    c.drawImage(img,o[2]*fz,o[3]*fz,o[0]*fz,o[1]*fz);
    if($('td')&&$('td').checked){c.strokeStyle='rgba(200,200,200,.7)';c.lineWidth=1;c.beginPath();
      [[0,-32],[64,0],[0,32],[-64,0],[0,-32]].forEach(function(p,k){var x=(OX+p[0])*S,y=(OY+p[1])*S;k?c.lineTo(x,y):c.moveTo(x,y);});c.stroke();}
    if($('tg')&&$('tg').checked&&d.g){
      c.lineWidth=1.5;
      d.g.forEach(function(g,k){c.strokeStyle=COLORS[k%COLORS.length];shapeLines(g).forEach(function(line){c.beginPath();line.forEach(function(p,m){var q=proj(p);m?c.lineTo(q[0]*S,q[1]*S):c.moveTo(q[0]*S,q[1]*S);});c.stroke();});});
    }
  };
  img.src=spritePath(r);
}
function neighbor(dir){var k=list.indexOf(sel);return k<0?null:(list[k+dir]!=null?list[k+dir]:null);}
function go(dir){var n=neighbor(dir);if(n==null)return;var k=list.indexOf(n);st.page=Math.floor(k/st.ps);renderGrid();open(n);}
function close(){$('panel').classList.remove('open');sel=-1;curToken++;history.replaceState(null,'',location.pathname+location.search);renderGrid();}

// ---- eventos
$('chips').addEventListener('click',function(e){var b=e.target.closest('.chip');if(!b)return;st.cat=parseInt(b.dataset.c,10);st.page=0;apply();});
$('grid').addEventListener('click',function(e){var c=e.target.closest('.card');if(c)open(parseInt(c.dataset.i,10));});
$('grid').addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){var c=e.target.closest('.card');if(c){e.preventDefault();open(parseInt(c.dataset.i,10));}}});
var qt; $('q').addEventListener('input',function(){clearTimeout(qt);var v=this.value;qt=setTimeout(function(){st.q=v;st.page=0;apply();},150);});
$('ts').addEventListener('input',function(){var v=this.value.trim();st.ts=v===''?-1:(tsIdx[v]!=null?tsIdx[v]:-2);if(st.ts===-2){return;}st.page=0;apply();});
['fPng:png','fGeo:geo','fDep:dep','fMiss:miss'].forEach(function(s){var p=s.split(':');$(p[0]).addEventListener('change',function(){st[p[1]]=this.checked;if(p[1]==='png'&&this.checked){st.miss=false;$('fMiss').checked=false;}if(p[1]==='miss'&&this.checked){st.png=false;$('fPng').checked=false;}st.page=0;apply();});});
$('ps').addEventListener('change',function(){st.ps=parseInt(this.value,10);st.page=0;apply();});
$('prev').onclick=function(){setPage(st.page-1);}; $('next').onclick=function(){setPage(st.page+1);};
$('clr').onclick=function(){st.cat=-1;st.ts=-1;st.q='';st.png=st.geo=st.dep=st.miss=false;st.page=0;$('q').value='';$('ts').value='';['fPng','fGeo','fDep','fMiss'].forEach(function(i){$(i).checked=false;});apply();};
$('pclose').onclick=close; $('dprev').onclick=function(){go(-1);}; $('dnext').onclick=function(){go(1);};
$('pcopy').onclick=function(){var n=T[sel][0];if(navigator.clipboard)navigator.clipboard.writeText(n).catch(function(){});this.textContent='Copiado';var b=this;setTimeout(function(){b.textContent='Copiar nome';},1200);};
document.addEventListener('keydown',function(e){
  if(e.target&&/input|select|textarea/i.test(e.target.tagName)){if(e.key==='Escape')e.target.blur();return;}
  if(e.key==='Escape'&&sel>=0)close();
  else if(e.key==='ArrowLeft'&&sel>=0)go(-1);else if(e.key==='ArrowRight'&&sel>=0)go(1);
  else if(e.key==='/'){e.preventDefault();$('q').focus();}
});

// ---- partida
var dl=''; CAT.ts.forEach(function(n){dl+='<option value="'+esc(n)+'">';}); $('tslist').innerHTML=dl;
var withPng=0,withGeo=0; T.forEach(function(r){if(r[4]&F.PNG)withPng++;if(r[4]&F.GEO)withGeo++;});
$('sub').textContent=T.length+' tiles · '+withPng+' com imagem · '+withGeo+' com geometria · gerado em '+CAT.gerado;
apply();
function fromHash(){var h=decodeURIComponent(location.hash.slice(1));if(!h)return;for(var i=0;i<T.length;i++)if(T[i][0]===h){var k=list.indexOf(i);if(k<0){st.cat=-1;st.ts=-1;st.q='';st.png=st.geo=st.dep=st.miss=false;apply();k=list.indexOf(i);}st.page=Math.floor(k/st.ps);renderGrid();open(i);break;}}
window.addEventListener('hashchange',function(){var h=decodeURIComponent(location.hash.slice(1));if(h&&(sel<0||T[sel][0]!==h))fromHash();});
fromHash();
})();
</script>
</body>
</html>
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-dir", default=str(HERE / "data"))
    ap.add_argument("--open", action="store_true", help="abre no navegador padrao ao terminar")
    a = ap.parse_args(argv)
    res = build(a.data_dir)
    for k, v in res.items():
        print(f"{k}: {v}")
    if a.open:
        import webbrowser
        webbrowser.open(Path(res["html"]).as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
