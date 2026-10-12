"""Galeria de aprovação do porte3d.

Uma página só (`index.html`, sem dependências) com um cartão por objeto: o sprite do jogo ao lado dos dois giros
(arte e realista), as notas e os defeitos do crítico, e os botões Aprovar / Refazer. `servir` sobe um servidor
mínimo só em 127.0.0.1, que entrega a pasta de trabalho como arquivos estáticos e aceita um único POST (/decidir).

Uso:
    python -m porte3d.galeria gerar
    python -m porte3d.galeria servir [--porta 8765]

A fila (porte3d/fila.py) é importada só na hora de usar; todos os caminhos podem ser trocados (testes).
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlsplit

HERE = Path(__file__).resolve().parent
RAIZ = HERE.parent / "acervo" / "data" / "porte3d"      # pasta de trabalho (fora do git)
VEREDITOS = HERE / "vereditos"
FICHAS = HERE / "fichas"

AGUARDANDO = "aguardando_aprovacao"
ID_OK = re.compile(r"^[a-z0-9_]+$")
MAX_CORPO = 16 * 1024
MAX_COMENTARIO = 1000

# abas: chave -> (título, estados que entram, texto do quadro vazio)
ABAS = {
    "aguardando": ("Aguardando você", (AGUARDANDO,), "Nada esperando aprovação."),
    "aprovados": ("Aprovados", ("aprovado", "publicado"), "Nenhum aprovado ainda."),
    "rejeitados": ("Para refazer", ("rejeitado",), "Nenhum pedido de refazer."),
    "reprovados": ("Reprovados / não portados", ("reprovado", "nao_portar"), "Nenhum reprovado."),
}
ESTADOS_TODOS = tuple(e for _, es, _ in ABAS.values() for e in es)

TIPO_PT = {
    "ausencia": "falta peça", "chapado": "chapado", "textura_deslocada": "textura fora do lugar",
    "buraco": "buraco", "emenda": "emenda", "proporcao": "proporção", "sobra": "sobra",
    "estrutura": "estrutura", "cor": "cor",
}
ORDEM_GRAV = {"grave": 0, "media": 1, "leve": 2}
GRAV_PT = {"grave": "grave", "media": "média", "leve": "leve"}
FOLHAS = (("comparacao", "Comparação"), ("fio", "Fio"), ("sobreposicao", "Sobreposição"), ("zoom", "Zoom"))
MAX_DEFEITOS = 5


# ---------------------------------------------------------------- dados

def _fila(fila=None):
    if fila is not None:
        return fila
    from porte3d import fila as f      # import tardio: o módulo é escrito por outra parte
    return f


def _ler_json(caminho: Path):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def veredito_ultimo(id_: str, vereditos: Path | None = None) -> dict | None:
    """Veredito da última rodada (maior n em vereditos/<id>/rodada_<n>.json)."""
    pasta = Path(vereditos or VEREDITOS) / id_
    melhor = None
    if pasta.is_dir():
        for p in pasta.glob("rodada_*.json"):
            m = re.fullmatch(r"rodada_(\d+)\.json", p.name)
            if m and (melhor is None or int(m.group(1)) > melhor[0]):
                melhor = (int(m.group(1)), p)
    return _ler_json(melhor[1]) if melhor else None


def ficha_de(id_: str, fichas: Path | None = None) -> dict | None:
    return _ler_json(Path(fichas or FICHAS) / f"{id_}.json")


# ---------------------------------------------------------------- HTML

def _e(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def _nota(valor) -> str:
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return "–"
    return f"{v:g}"


def _classe_nota(valor) -> str:
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return "nd"
    return "boa" if v >= 8 else ("media" if v >= 6 else "ruim")


def _notas_do_cartao(obj: dict, vered: dict | None) -> tuple:
    """(arte, realista, rodada): do veredito, ou da última entrada de `notas` da fila."""
    if vered:
        return vered.get("nota_arte"), vered.get("nota_realista"), vered.get("rodada")
    notas = obj.get("notas") or []
    if notas:
        u = notas[-1]
        return u.get("arte"), u.get("realista"), u.get("rodada")
    return None, None, obj.get("rodada")


def _lista_defeitos(vered: dict | None) -> str:
    if not vered:
        return '<p class="vazio">Sem veredito do crítico.</p>'
    defs = sorted(vered.get("defeitos") or [], key=lambda d: ORDEM_GRAV.get(d.get("gravidade"), 9))
    if not defs:
        return '<p class="vazio">O crítico não apontou defeitos.</p>'
    itens = []
    for d in defs[:MAX_DEFEITOS]:
        grav = d.get("gravidade") if d.get("gravidade") in GRAV_PT else "leve"
        nivel = {"arte": "arte", "realista": "realista", "ambos": "os dois"}.get(d.get("nivel"), "")
        itens.append(
            f'<li><span class="grav {grav}">{_e(GRAV_PT[grav])}</span> '
            f'<b>{_e(d.get("parte", ""))}</b> · {_e(TIPO_PT.get(d.get("tipo"), d.get("tipo", "")))}'
            f'{" (" + _e(nivel) + ")" if nivel else ""} — {_e(d.get("onde", ""))}</li>')
    mais = len(defs) - MAX_DEFEITOS
    extra = f'<li class="mais">+ {mais} defeito(s) menores na folha do crítico</li>' if mais > 0 else ""
    return f'<ul class="defeitos">{"".join(itens)}{extra}</ul>'


def _img(base: str, id_: str, rel: str, raiz: Path, alt: str, cls: str = "") -> str:
    if not (raiz / id_ / rel).is_file():
        return f'<div class="semimg">sem imagem<br><small>{_e(rel)}</small></div>'
    src = f"{base}{quote(id_)}/{quote(rel)}"
    return f'<img class="{cls}" src="{_e(src)}" alt="{_e(alt)}" loading="lazy">'


def _aba_de(estado: str) -> str:
    for chave, (_, estados, _) in ABAS.items():
        if estado in estados:
            return chave
    return ""


def cartao(obj: dict, raiz: Path, base: str, vered: dict | None, ficha: dict | None) -> str:
    id_ = str(obj.get("id", ""))
    estado = obj.get("estado") or ""
    nome = obj.get("custom_name") or obj.get("group_name") or id_
    grupo = obj.get("group_name") if obj.get("custom_name") and obj.get("group_name") != obj.get("custom_name") else ""
    na, nr, rodada = _notas_do_cartao(obj, vered)
    o_que_e = (ficha or {}).get("o_que_e") or ""
    aba = _aba_de(estado)
    pendente = estado == AGUARDANDO

    links = "".join(
        f'<a href="{_e(base + quote(id_) + "/folhas/" + n + ".png")}" target="_blank" rel="noopener">{_e(t)}</a>'
        for n, t in FOLHAS if (raiz / id_ / "folhas" / f"{n}.png").is_file())

    if pendente:
        rodape = (
            '<div class="acoes">'
            '<textarea class="coment" rows="2" maxlength="1000" '
            'placeholder="Se for refazer: o que está errado? (opcional)" aria-label="Comentário"></textarea>'
            '<div class="botoes">'
            '<button type="button" class="b-aprovar" data-decisao="aprovado">Aprovar</button>'
            '<button type="button" class="b-refazer" data-decisao="rejeitado">Refazer</button>'
            '</div><p class="msg" role="status"></p></div>')
    else:
        rodape = '<div class="acoes"><p class="msg" role="status"></p></div>'

    motivo = ""
    if obj.get("motivo") and not pendente:
        motivo = f'<p class="motivo"><b>Motivo:</b> {_e(obj["motivo"])}</p>'
    cu = obj.get("comentario_usuario")
    coment = (f'<p class="motivo" data-coment-novo><b>Seu comentário:</b> {_e(cu)}</p>' if cu
              else '<p class="motivo" data-coment-novo hidden></p>')

    tem_img = any((raiz / id_ / rel).is_file() for rel in
                  ("entrada/frente_original.png", "folhas/giro_arte.gif", "folhas/giro_realista.gif"))
    imagens = f"""<div class="imagens">
    <figure class="f-sprite"><figcaption>Jogo</figcaption>{_img(base, id_, "entrada/frente_original.png", raiz, "sprite do jogo", "sprite")}</figure>
    <figure><figcaption>Arte</figcaption>{_img(base, id_, "folhas/giro_arte.gif", raiz, "giro, nível arte")}</figure>
    <figure><figcaption>Realista</figcaption>{_img(base, id_, "folhas/giro_realista.gif", raiz, "giro, nível realista")}</figure>
  </div>""" if tem_img else ""

    notas_html = "" if (na is None and nr is None) else f"""<div class="notas">
    <div class="nota {_classe_nota(na)}"><span>{_e(_nota(na))}</span><small>arte</small></div>
    <div class="nota {_classe_nota(nr)}"><span>{_e(_nota(nr))}</span><small>realista</small></div>
    <p class="rodada">{f"Rodada {_e(rodada)} do crítico" if rodada else ""}</p>
  </div>"""

    return f"""
<article class="cartao" data-id="{_e(id_)}" data-estado="{_e(estado)}" data-aba="{_e(aba)}"{"" if aba == "aguardando" else " hidden"}>
  <header>
    <div><h2>{_e(nome)}</h2>{f'<p class="grupo">{_e(grupo)}</p>' if grupo else ""}<p class="idobj">{_e(id_)}</p></div>
    <span class="selo" data-estado-selo>{_e(_selo(estado))}</span>
  </header>
  {f'<p class="oque">{_e(o_que_e)}</p>' if o_que_e else ""}
  {imagens}
  {notas_html}
  {_lista_defeitos(vered) if (vered or pendente) else ""}
  {motivo}
  {coment}
  {f'<nav class="folhas">{links}</nav>' if links else ""}
  {rodape}
</article>"""


def _selo(estado: str) -> str:
    return {
        AGUARDANDO: "aguardando", "aprovado": "aprovado", "publicado": "publicado",
        "rejeitado": "refazer", "reprovado": "reprovado", "nao_portar": "não portado",
    }.get(estado, estado)


CSS = """
:root{color-scheme:dark;--bg:#14161b;--card:#1d2027;--card2:#252932;--tx:#e8eaee;--mut:#9aa1ad;--bd:#323744;
--ok:#4cc38a;--okbg:#17382a;--am:#e5b84a;--ambg:#3b3213;--rd:#ee6a6a;--rdbg:#431d1d;--az:#6aa8ff}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--tx);font:16px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.topo{position:sticky;top:0;z-index:5;background:rgba(20,22,27,.96);backdrop-filter:blur(6px);border-bottom:1px solid var(--bd);padding:12px 16px 0}
h1{margin:0 0 2px;font-size:1.25rem}
.contador{margin:0 0 10px;color:var(--mut);font-size:.95rem}
.contador b{color:var(--tx)}
.abas{display:flex;gap:6px;overflow-x:auto;padding-bottom:0}
.aba{flex:0 0 auto;background:none;border:0;border-bottom:3px solid transparent;color:var(--mut);font:inherit;padding:8px 12px;cursor:pointer;white-space:nowrap}
.aba[aria-selected=true]{color:var(--tx);border-bottom-color:var(--az)}
.aba .n{display:inline-block;min-width:1.6em;margin-left:6px;padding:0 6px;border-radius:99px;background:var(--card2);font-size:.85rem;text-align:center}
.aba[data-aba=aguardando] .n:not(.zero){background:var(--az);color:#0b1220;font-weight:700}
main{max-width:1180px;margin:0 auto;padding:16px;display:grid;gap:16px;grid-template-columns:repeat(auto-fill,minmax(min(100%,520px),1fr))}
.vazio-aba{grid-column:1/-1;text-align:center;color:var(--mut);padding:48px 0}
.cartao{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:10px;min-width:0}
.cartao[hidden]{display:none}
.cartao header{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.cartao h2{margin:0;font-size:1.15rem;overflow-wrap:anywhere}
.grupo{margin:0;color:var(--mut);font-size:.9rem}
.idobj{margin:0;color:var(--mut);font:.78rem ui-monospace,Consolas,monospace;overflow-wrap:anywhere}
.selo{flex:0 0 auto;font-size:.8rem;padding:2px 10px;border-radius:99px;background:var(--card2);color:var(--mut);border:1px solid var(--bd)}
.cartao[data-estado=aprovado] .selo,.cartao[data-estado=publicado] .selo{background:var(--okbg);color:var(--ok);border-color:var(--ok)}
.cartao[data-estado=rejeitado] .selo{background:var(--ambg);color:var(--am);border-color:var(--am)}
.cartao[data-estado=reprovado] .selo,.cartao[data-estado=nao_portar] .selo{background:var(--rdbg);color:var(--rd);border-color:var(--rd)}
.oque{margin:0;color:var(--mut);font-size:.95rem}
.imagens{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.6fr) minmax(0,1.6fr);gap:8px;align-items:stretch}
.imagens figure{margin:0;display:flex;flex-direction:column;justify-content:center;background:var(--card2);border-radius:8px;padding:6px;text-align:center;min-width:0}
.imagens figcaption{font-size:.78rem;color:var(--mut);margin-bottom:4px;text-transform:uppercase;letter-spacing:.04em}
.imagens img{display:block;width:100%;height:auto;max-height:340px;object-fit:contain;margin:0 auto}
.imagens img.sprite{image-rendering:pixelated}
.semimg{color:var(--mut);font-size:.8rem;padding:24px 4px}
.notas{display:flex;align-items:center;gap:10px}
.nota{display:flex;flex-direction:column;align-items:center;min-width:76px;padding:4px 12px;border-radius:10px;border:1px solid var(--bd)}
.nota span{font-size:1.7rem;font-weight:700;line-height:1.1}
.nota small{color:var(--mut);font-size:.75rem}
.nota.boa{background:var(--okbg);border-color:var(--ok)}.nota.boa span{color:var(--ok)}
.nota.media{background:var(--ambg);border-color:var(--am)}.nota.media span{color:var(--am)}
.nota.ruim{background:var(--rdbg);border-color:var(--rd)}.nota.ruim span{color:var(--rd)}
.rodada{margin:0 0 0 auto;color:var(--mut);font-size:.85rem}
.defeitos{margin:0;padding:0;list-style:none;display:grid;gap:5px;font-size:.92rem}
.defeitos li{overflow-wrap:anywhere}
.defeitos .mais{color:var(--mut)}
.grav{display:inline-block;font-size:.72rem;padding:0 7px;border-radius:99px;margin-right:4px;vertical-align:1px}
.grav.grave{background:var(--rdbg);color:var(--rd)}.grav.media{background:var(--ambg);color:var(--am)}.grav.leve{background:var(--card2);color:var(--mut)}
.vazio{margin:0;color:var(--mut);font-size:.9rem}
.motivo{margin:0;font-size:.92rem;overflow-wrap:anywhere}
.folhas{display:flex;flex-wrap:wrap;gap:8px}
.folhas a{color:var(--az);text-decoration:none;border:1px solid var(--bd);border-radius:8px;padding:5px 12px;font-size:.9rem}
.folhas a:hover{background:var(--card2)}
.acoes{margin-top:auto;display:grid;gap:8px}
.coment{width:100%;resize:vertical;background:var(--bg);color:var(--tx);border:1px solid var(--bd);border-radius:8px;padding:8px;font:inherit;font-size:.95rem}
.botoes{display:grid;grid-template-columns:1fr 1fr;gap:10px}
button{font:inherit}
.botoes button{border:0;border-radius:10px;padding:13px 10px;font-weight:700;font-size:1rem;cursor:pointer}
.b-aprovar{background:var(--ok);color:#06210f}
.b-refazer{background:var(--am);color:#2b1f00}
.botoes button:disabled{opacity:.5;cursor:wait}
.msg{margin:0;min-height:1.2em;font-size:.9rem;color:var(--mut)}
.msg.erro{color:var(--rd)}.msg.certo{color:var(--ok)}
@media (max-width:560px){
  main{padding:12px;gap:12px}
  .cartao{padding:12px}
  .imagens{grid-template-columns:1fr 1fr}
  .imagens .f-sprite{grid-column:1/-1;max-width:110px;justify-self:center}
  .rodada{display:none}
}
"""

JS = """
(function(){
  var cartoes=[].slice.call(document.querySelectorAll('.cartao'));
  var abas=[].slice.call(document.querySelectorAll('.aba'));
  var vazio=document.getElementById('vazio-aba');
  var porAba={aguardando:['aguardando_aprovacao'],aprovados:['aprovado','publicado'],rejeitados:['rejeitado'],reprovados:['reprovado','nao_portar']};
  var SELO={aguardando_aprovacao:'aguardando',aprovado:'aprovado',publicado:'publicado',rejeitado:'refazer',reprovado:'reprovado',nao_portar:'não portado'};
  var atual='aguardando';
  var textos=JSON.parse(document.getElementById('vazios').textContent);
  try{var s=sessionStorage.getItem('aba');if(s&&porAba[s])atual=s;}catch(e){}
  function abaDe(est){for(var k in porAba){if(porAba[k].indexOf(est)>=0)return k;}return '';}
  function atualizar(){
    var cont={};
    cartoes.forEach(function(c){var a=abaDe(c.dataset.estado);c.dataset.aba=a;cont[a]=(cont[a]||0)+1;c.hidden=(a!==atual);});
    abas.forEach(function(b){
      var n=cont[b.dataset.aba]||0, el=b.querySelector('.n');
      el.textContent=n; el.classList.toggle('zero',n===0);
      var sel=b.dataset.aba===atual; b.setAttribute('aria-selected',sel?'true':'false');
      if(sel&&b.scrollIntoView){try{b.scrollIntoView({inline:'center',block:'nearest'});}catch(e){}}
    });
    var esp=cont.aguardando||0;
    document.getElementById('contador').innerHTML=esp?'<b>'+esp+'</b> '+(esp===1?'objeto esperando':'objetos esperando')+' você':'<b>Nada</b> esperando você';
    var visiveis=cartoes.filter(function(c){return !c.hidden;}).length;
    vazio.hidden=visiveis>0; vazio.textContent=textos[atual]||'';
  }
  abas.forEach(function(b){b.addEventListener('click',function(){atual=b.dataset.aba;try{sessionStorage.setItem('aba',atual);}catch(e){}atualizar();});});
  function msg(c,t,cls){var m=c.querySelector('.msg');m.textContent=t;m.className='msg '+(cls||'');}
  cartoes.forEach(function(c){
    [].slice.call(c.querySelectorAll('[data-decisao]')).forEach(function(b){
      b.addEventListener('click',function(){
        var dec=b.dataset.decisao, ta=c.querySelector('.coment'), com=ta?ta.value.trim():'';
        var btns=c.querySelectorAll('[data-decisao]');
        [].forEach.call(btns,function(x){x.disabled=true;});
        msg(c,'Enviando…');
        fetch('/decidir',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:c.dataset.id,decisao:dec,comentario:com||null})})
        .then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j};});})
        .then(function(r){
          if(!r.ok){throw new Error((r.j&&r.j.erro)||'Não deu certo.');}
          var o=r.j.objeto||r.j; c.dataset.estado=o.estado||(dec==='aprovado'?'aprovado':'rejeitado');
          c.querySelector('[data-estado-selo]').textContent=SELO[c.dataset.estado]||c.dataset.estado;
          var ac=c.querySelector('.acoes'); if(ta){ac.querySelector('.botoes').remove();ta.remove();}
          var n=c.querySelector('[data-coment-novo]'); var cm=o.comentario_usuario||com;
          if(cm){n.textContent='';var bb=document.createElement('b');bb.textContent='Seu comentário: ';n.appendChild(bb);n.appendChild(document.createTextNode(cm));n.hidden=false;}
          msg(c,dec==='aprovado'?'Aprovado.':'Vai ser refeito.','certo');
          setTimeout(atualizar,900);
        }).catch(function(e){
          [].forEach.call(btns,function(x){x.disabled=false;});
          msg(c,(e&&e.message)||'Erro de conexão. O servidor está rodando?','erro');
        });
      });
    });
  });
  atualizar();
})();
"""


def _pagina(cartoes: list[str], titulo: str) -> str:
    abas = "".join(
        f'<button type="button" class="aba" role="tab" data-aba="{k}" aria-selected="{"true" if k == "aguardando" else "false"}">'
        f'{_e(t)}<span class="n">0</span></button>' for k, (t, _, _) in ABAS.items())
    vazios = json.dumps({k: v for k, (_, _, v) in ABAS.items()}, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(titulo)}</title>
<style>{CSS}</style>
</head>
<body>
<div class="topo">
  <h1>{_e(titulo)}</h1>
  <p class="contador" id="contador"></p>
  <div class="abas" role="tablist">{abas}</div>
</div>
<main>
{"".join(cartoes)}
<p class="vazio-aba" id="vazio-aba" hidden></p>
</main>
<script type="application/json" id="vazios">{vazios}</script>
<script>{JS}</script>
</body>
</html>
"""


# ---------------------------------------------------------------- gerar

def gerar(saida=None, estados=(AGUARDANDO,), *, fila=None, raiz=None, vereditos=None, fichas=None,
          titulo="Galeria de aprovação do porte 3D") -> Path:
    """Escreve `index.html` em `saida` (padrão <raiz>/galeria/) e devolve o caminho do arquivo.

    As imagens são referenciadas por caminho relativo a `<raiz>/<id>/...`, então a página funciona servida de `raiz`.
    """
    raiz = Path(raiz or RAIZ).resolve()
    saida = Path(saida) if saida else raiz / "galeria"
    saida.mkdir(parents=True, exist_ok=True)
    saida = saida.resolve()
    rel = os.path.relpath(raiz, saida).replace("\\", "/")
    base = "" if rel == "." else rel.rstrip("/") + "/"
    f = _fila(fila)

    objs = []
    for est in estados:
        objs.extend(f.objetos(est))
    vistos, cartoes = set(), []
    ordem = {e: i for i, e in enumerate(ESTADOS_TODOS)}
    for o in sorted(objs, key=lambda o: (ordem.get(o.get("estado"), 99), str(o.get("id")))):
        id_ = str(o.get("id", ""))
        if not ID_OK.match(id_) or id_ in vistos:
            continue
        vistos.add(id_)
        cartoes.append(cartao(o, raiz, base, veredito_ultimo(id_, vereditos), ficha_de(id_, fichas)))
    destino = saida / "index.html"
    destino.write_text(_pagina(cartoes, titulo), encoding="utf-8")
    return destino


# ---------------------------------------------------------------- servidor

def contagens(fila=None) -> dict:
    f = _fila(fila)
    por_estado = {}
    for o in f.objetos(None):
        por_estado[o.get("estado")] = por_estado.get(o.get("estado"), 0) + 1
    abas = {k: sum(por_estado.get(e, 0) for e in es) for k, (_, es, _) in ABAS.items()}
    return {"estados": por_estado, "abas": abas, "aguardando": abas["aguardando"]}


def _validar_decisao(corpo: bytes) -> tuple[str, str, str | None]:
    try:
        d = json.loads(corpo.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ValueError("corpo não é JSON válido")
    if not isinstance(d, dict) or set(d) - {"id", "decisao", "comentario"}:
        raise ValueError("campos inesperados")
    id_, dec, com = d.get("id"), d.get("decisao"), d.get("comentario")
    if not isinstance(id_, str) or not ID_OK.match(id_) or len(id_) > 120:
        raise ValueError("id inválido")
    if dec not in ("aprovado", "rejeitado"):
        raise ValueError("decisao deve ser 'aprovado' ou 'rejeitado'")
    if com is not None:
        if not isinstance(com, str) or len(com) > MAX_COMENTARIO:
            raise ValueError("comentário inválido ou longo demais")
        com = com.strip() or None
    return id_, dec, com


def criar_servidor(porta: int = 8765, *, fila=None, raiz=None) -> ThreadingHTTPServer:
    """Servidor ligado só a 127.0.0.1. `porta=0` escolhe uma porta livre (testes)."""
    raiz = str(Path(raiz or RAIZ).resolve())
    f = _fila(fila)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=raiz, **kw)

        def log_message(self, fmt, *args):
            pass

        def _json(self, codigo: int, dados: dict):
            corpo = json.dumps(dados, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)

        def _host_ok(self) -> bool:
            """Só aceita Host/Origin locais (barra DNS rebinding e página de outro site mandando POST)."""
            porta_atual = self.server.server_address[1]
            validos = {f"127.0.0.1:{porta_atual}", f"localhost:{porta_atual}"}
            if self.headers.get("Host", "") not in validos:
                return False
            origem = self.headers.get("Origin")
            return origem is None or urlsplit(origem).netloc in validos

        def do_GET(self):
            caminho = urlsplit(self.path).path
            if not self._host_ok():
                return self._json(403, {"erro": "host não permitido"})
            if caminho == "/estado":
                return self._json(200, contagens(f))
            if caminho in ("/", ""):
                self.send_response(302)
                self.send_header("Location", "/galeria/index.html")
                self.end_headers()
                return
            return super().do_GET()

        def do_HEAD(self):
            if not self._host_ok():
                return self._json(403, {"erro": "host não permitido"})
            return super().do_HEAD()

        def do_POST(self):
            # lê o corpo antes de qualquer resposta, para não derrubar a conexão do cliente no meio do envio
            try:
                n = int(self.headers.get("Content-Length", ""))
            except ValueError:
                n = -1
            corpo = self.rfile.read(n) if 0 <= n <= MAX_CORPO else b""
            if MAX_CORPO < n <= 1024 * 1024:          # joga fora o excesso (até 1 MB) para a resposta chegar inteira
                restante = n
                while restante > 0:
                    pedaco = self.rfile.read(min(65536, restante))
                    if not pedaco:
                        break
                    restante -= len(pedaco)
            if urlsplit(self.path).path != "/decidir":
                return self._json(404, {"erro": "não existe"})
            if not self._host_ok():
                return self._json(403, {"erro": "host não permitido"})
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                return self._json(415, {"erro": "use application/json"})
            if n < 0:
                return self._json(411, {"erro": "falta Content-Length"})
            if n > MAX_CORPO:
                self.close_connection = True
                return self._json(413, {"erro": "pedido grande demais"})
            try:
                id_, dec, com = _validar_decisao(corpo)
            except ValueError as e:
                return self._json(400, {"erro": str(e)})
            try:
                atual = f.obter(id_)
            except Exception:             # a fila real levanta ObjetoInexistente; a falsa pode devolver None
                atual = None
            if not atual:
                return self._json(404, {"erro": f"objeto '{id_}' não existe na fila"})
            if atual.get("estado") != AGUARDANDO:
                return self._json(409, {"erro": f"o objeto está '{atual.get('estado')}', não aguardando aprovação"})
            try:
                f.decidir(id_, dec, com)
            except Exception as e:        # TransicaoInvalida e afins: a decisão não foi aplicada
                return self._json(409, {"erro": str(e)})
            return self._json(200, {"objeto": f.obter(id_), "aguardando": contagens(f)["aguardando"]})

        def do_PUT(self):
            self._json(405, {"erro": "método não permitido"})
        do_DELETE = do_PATCH = do_PUT

    return ThreadingHTTPServer(("127.0.0.1", porta), Handler)


def servir(porta: int = 8765, *, fila=None, raiz=None, gerar_antes: bool = True, estados=ESTADOS_TODOS) -> None:
    """Regenera a página e serve até Ctrl+C."""
    f = _fila(fila)
    if gerar_antes:
        gerar(None if raiz is None else Path(raiz) / "galeria", estados, fila=f, raiz=raiz)
    srv = criar_servidor(porta, fila=f, raiz=raiz)
    print(f"Galeria em http://127.0.0.1:{srv.server_address[1]}/  (Ctrl+C para parar)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="porte3d.galeria", description="Galeria de aprovação do porte 3D")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gerar", help="escreve o index.html")
    g.add_argument("--saida", type=Path, default=None)
    s = sub.add_parser("servir", help="gera a página e serve em 127.0.0.1")
    s.add_argument("--porta", type=int, default=8765)
    a = ap.parse_args(argv)
    if a.cmd == "gerar":
        print(gerar(a.saida, ESTADOS_TODOS))
    else:
        servir(a.porta)
    return 0


if __name__ == "__main__":
    sys.exit(main())
