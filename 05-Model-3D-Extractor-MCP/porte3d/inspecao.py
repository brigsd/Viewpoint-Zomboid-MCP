"""Inspeção por script de um sprite do acervo: a metade "medida" do inspetor do porte 3D.

O agente inspetor só responde perguntas visuais; tudo o que dá para MEDIR sai daqui (ver ficha.schema.json e o
bullet "Inspetor" de planos/2026-10-12-esteira-de-porte-3d.md). `inspecionar()` grava, em
`<saida>/<id>/`: `medidas.json` e as imagens `direcoes.png`, `geometria.png`, `cobertura.png` e (se houver mapa de
profundidade) `profundidade.png`.

Uso:  python -m porte3d.inspecao <sprite_S> [--saida DIR]

Convenções: metros e eixos da receita (CONTRATO.md); a projeção da câmera do jogo é a de `conferir_formas.projetar`.

Como cada medida é feita
------------------------
- `contorno_0`, `cobertura`, `sobra`: a geometria do jogo (todas as peças de `acervo.formas`, preenchidas) é
  projetada pela câmera do jogo e rasterizada num quadro 128x256 (desenhada em 4x e reduzida; um pixel conta se pelo
  menos 25% dele é geometria, para que as peças finas de 1 cm não sumam). O desenho é o alfa >= 128 do quadro.
  `contorno_0` = interseção / união; `cobertura` = (desenho ∩ geometria) / desenho; `sobra` = (geometria \\ desenho) /
  geometria.
- `pecas_sem_par` (peça que só o jogo descreveu de um lado): o centro do objeto é o centro da caixa envolvente da
  geometria em x e y (ou o centro do tile, (0, 0), se ele deixar menos peças sem par). Para cada peça testamos os três
  espelhos em torno desse centro (em x, em y e em xy, que é o giro de 180°): a peça tem par se existir outra peça da
  mesma forma cuja caixa envolvente coincide com a caixa espelhada, com tolerância de 2 cm em cada coordenada. Uma
  peça simétrica por si mesma (como o tampo) tem par consigo. Uma mesa de 4 pés tem par em tudo; uma de 3 pés deixa
  cada pé sem um dos espelhos e `pecas_provavelmente_faltando` junta os espelhos que não existem (um só pé
  escondido, com 3 votos). Esses espelhos só entram se não caírem em cima de uma peça que já existe.
- `fino`: a menor medida de alguma peça é menor que 1,5 cm, ou há polígonos finos (o jogo descreve cortinas,
  placas, grades como polígonos de espessura zero; viram prismas de 1 cm).
- `montado_na_parede`: propriedade `MoveType = WallObject` ou `attached*` do jogo. A geometria que começa acima de
  50 cm do chão (`altura_base`) só gera uma dica, porque pias e bancadas também começam no alto.
- `espelhado_E_S` / `espelhado_W_N`: `acervo.espelhado` entre as direções (None se uma delas não existe). Perto de
  1 = a direção de lado é a outra espelhada.
- `tem_N`: existe um quadro N com desenho e ele não é cópia do quadro S (`N_igual_S` perto de 1 = a "traseira" é a
  frente repetida).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import acervo
from .conferir_formas import arestas, projetar

ESC = 3                                   # ampliação das imagens
SUPER = 4                                 # superamostragem da rasterização da geometria
PADRAO = acervo.ACERVO_DB.parent / "porte3d" / "inspecao"
TOL_PAR = 0.02                            # m
FINO_M = 0.015                            # m
FUNDO = (58, 60, 70)
CORES = [(255, 230, 0), (0, 255, 255), (255, 80, 255), (120, 255, 80), (255, 140, 0), (255, 90, 90),
         (110, 160, 255), (200, 200, 200)]
PROPS_CHAVE = ["CustomName", "GroupName", "Facing", "IsTable", "container", "Surface", "SpriteGridPos", "MoveType",
               "IsHigh", "IsLow", "IsMoveAble", "attachedN", "attachedS", "attachedE", "attachedW", "attachedCeiling",
               "ContainerCapacity", "IsFridge", "Freezer", "lightswitch", "HasLightOnSprite", "BlocksPlacement",
               "solidtrans", "Translucent", "IsStackable", "ScrapSize", "PickUpWeight"]
PROPS_MATERIAL = ["Material", "Material2", "Material3", "MaterialType"]


# ---------------------------------------------------------------- utilidades

def _fonte(tam: int = 13):
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:                                       # Pillow antigo
        return ImageFont.load_default()


def _arred(v, n: int = 4):
    if isinstance(v, (list, tuple, np.ndarray)):
        return [_arred(x, n) for x in v]
    return round(float(v), n)


def _caixa_pontos(p: dict) -> np.ndarray:
    """(N,3) pontos do contorno 3D da peça (com rot), em metros."""
    return np.vstack(arestas(p))


def _aabb(p: dict) -> tuple[np.ndarray, np.ndarray]:
    pts = _caixa_pontos(p)
    return pts.min(0), pts.max(0)


def _hull(pts: np.ndarray) -> np.ndarray:
    """Envoltória convexa 2D (cadeia monótona)."""
    pts = sorted(set(map(tuple, np.round(pts, 6))))
    if len(pts) <= 2:
        return np.array(pts)

    def meia(ps):
        h = []
        for q in ps:
            while len(h) >= 2 and (h[-1][0] - h[-2][0]) * (q[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (q[0] - h[-2][0]) <= 0:
                h.pop()
            h.append(q)
        return h
    inf, sup = meia(pts), meia(pts[::-1])
    return np.array(inf[:-1] + sup[:-1])


def _poligonos_2d(p: dict) -> list[np.ndarray]:
    """Polígonos (pixels do quadro 128x256) que preenchem a silhueta projetada da peça."""
    linhas = arestas(p)
    if p["forma"] == "prisma":
        n = len(p["perfil"])
        a, b = projetar(linhas[0][:n]), projetar(linhas[1][:n])      # os dois anéis, nessa ordem (ver arestas)
        polis = [a, b]
        for i in range(n):
            j = (i + 1) % n
            polis.append(np.array([a[i], a[j], b[j], b[i]]))
        return polis
    return [_hull(projetar(np.vstack(linhas)))]


def mascara_geometria(pecas: list[dict]) -> np.ndarray:
    """Máscara bool (256, 128) da silhueta projetada de todas as peças (preenchidas)."""
    img = Image.new("L", (acervo.FW * SUPER, acervo.FH * SUPER), 0)
    d = ImageDraw.Draw(img)
    for p in pecas:
        for poli in _poligonos_2d(p):
            if len(poli) >= 3:
                d.polygon([tuple(v) for v in (poli * SUPER)], fill=255)
            elif len(poli) == 2:
                d.line([tuple(v) for v in (poli * SUPER)], fill=255, width=SUPER)
    a = np.asarray(img, np.float32).reshape(acervo.FH, SUPER, acervo.FW, SUPER).mean((1, 3)) / 255.0
    return a >= 0.25


def _slug(nome: str) -> str:
    return acervo._slug(nome)


# ---------------------------------------------------------------- simetria

def _combina(a: tuple, b: tuple) -> bool:
    """(forma, min, max) quase iguais (tolerância TOL_PAR em cada coordenada)?"""
    return a[0] == b[0] and np.all(np.abs(a[1] - b[1]) <= TOL_PAR) and np.all(np.abs(a[2] - b[2]) <= TOL_PAR)


def _espelho(c: tuple, centro: tuple[float, float], eixo: str) -> tuple:
    forma, lo, hi = c
    lo2, hi2 = lo.copy(), hi.copy()
    if "x" in eixo:
        lo2[0], hi2[0] = 2 * centro[0] - hi[0], 2 * centro[0] - lo[0]
    if "y" in eixo:
        lo2[1], hi2[1] = 2 * centro[1] - hi[1], 2 * centro[1] - lo[1]
    return forma, lo2, hi2


def _iou3d(a: tuple, b: tuple) -> float:
    lo, hi = np.maximum(a[1], b[1]), np.minimum(a[2], b[2])
    inter = float(np.prod(np.clip(hi - lo, 0, None)))
    va, vb = float(np.prod(a[2] - a[1])), float(np.prod(b[2] - b[1]))
    uni = va + vb - inter
    return inter / uni if uni > 0 else 0.0


def _eh_pe(c: tuple) -> bool:
    """Pé: coluna pequena (<= 15 cm de lado) que sai do chão e tem pelo menos 10 cm de altura."""
    _, lo, hi = c
    return bool(hi[0] - lo[0] <= 0.15 and hi[1] - lo[1] <= 0.15 and lo[2] <= 0.03 and hi[2] - lo[2] >= 0.10)


def simetria(pecas: list[dict]) -> dict:
    """Peças sem par de espelho (ver o docstring do módulo). Devolve `centro`, `sem_par`, `faltando`, `n_pes`."""
    cs = [(p["forma"], *_aabb(p)) for p in pecas]
    nomes = [p["nome"] for p in pecas]
    if not cs:
        return {"centro": None, "sem_par": [], "faltando": [], "n_pes": 0}
    lo_t, hi_t = np.min([c[1] for c in cs], 0), np.max([c[2] for c in cs], 0)
    candidatos = [((lo_t[0] + hi_t[0]) / 2, (lo_t[1] + hi_t[1]) / 2), (0.0, 0.0)]

    def faltas(centro):
        out = []
        for i, c in enumerate(cs):
            sem = [e for e in ("x", "y", "xy") if not any(_combina(_espelho(c, centro, e), d) for d in cs)]
            out.append(sem)
        return out

    avaliados = [(sum(bool(s) for s in faltas(c)), k, c) for k, c in enumerate(candidatos)]
    _, _, centro = min(avaliados)
    sem_lista = faltas(centro)
    sem_par = [{"peca": nomes[i], "sem_par": s} for i, s in enumerate(sem_lista) if s]
    faltando: list[dict] = []
    for i, s in enumerate(sem_lista):
        for e in s:
            m = _espelho(cs[i], centro, e)
            if any(_iou3d(m, d) > 0.3 for d in cs):          # cairia em cima de uma peça que já existe
                continue
            for f in faltando:
                if _combina((f["forma"], f["_lo"], f["_hi"]), m):
                    f["votos"] += 1
                    break
            else:
                faltando.append({"forma": m[0], "_lo": m[1], "_hi": m[2], "copia_de": nomes[i], "espelho": e,
                                 "votos": 1, "pe": _eh_pe(m)})
    for f in faltando:
        f["min"], f["max"] = _arred(f.pop("_lo")), _arred(f.pop("_hi"))
    return {"centro": _arred(centro), "sem_par": sem_par, "faltando": faltando, "n_pes": sum(_eh_pe(c) for c in cs)}


# ---------------------------------------------------------------- imagens

def _rotulo(img: Image.Image, xy, texto: str, cor=(255, 255, 255), fonte=None):
    ImageDraw.Draw(img).text(xy, texto, fill=cor, font=fonte or _fonte())


def _quadro_ampliado(q: np.ndarray | None) -> Image.Image:
    fundo = Image.new("RGBA", (acervo.FW, acervo.FH), FUNDO + (255,))
    if q is not None:
        fundo.alpha_composite(Image.fromarray(q))
    return fundo.resize((acervo.FW * ESC, acervo.FH * ESC), Image.NEAREST).convert("RGB")


def _painel_ausente(texto: str) -> Image.Image:
    im = Image.new("RGB", (acervo.FW * ESC, acervo.FH * ESC), (40, 40, 44))
    d = ImageDraw.Draw(im)
    w, h = im.size
    d.line([(0, 0), (w, h)], fill=(120, 60, 60), width=2)
    d.line([(0, h), (w, 0)], fill=(120, 60, 60), width=2)
    d.text((10, h // 2 - 8), texto, fill=(255, 200, 200), font=_fonte(16))
    return im


def _faixas(paineis: list[tuple[str, Image.Image]], altura_topo: int = 22, rodape: int = 0) -> Image.Image:
    """Painéis lado a lado com um título em cada."""
    w, h = paineis[0][1].size
    folha = Image.new("RGB", (w * len(paineis) + 4 * (len(paineis) - 1), h + altura_topo + rodape), (0, 0, 0))
    for i, (titulo, im) in enumerate(paineis):
        x = i * (w + 4)
        folha.paste(im, (x, altura_topo))
        _rotulo(folha, (x + 4, 3), titulo)
    return folha


def img_direcoes(db, sprites: dict, medidas: dict) -> Image.Image:
    paineis = []
    for f in acervo.DIRECOES:
        nome = sprites.get(f)
        q = acervo.quadro(db, nome) if nome else None
        if q is None:
            paineis.append((f"{f}: ausente", _painel_ausente(f"{f} ausente")))
        else:
            paineis.append((f"{f}: {nome[-36:]}", _quadro_ampliado(q)))
    folha = _faixas(paineis, altura_topo=22, rodape=22)
    e, w = medidas.get("espelhado_E_S"), medidas.get("espelhado_W_N")
    txt = "espelho E~S: " + ("-" if e is None else f"{e:.2f}") + "   espelho W~N: " + ("-" if w is None else f"{w:.2f}")
    txt += "   N igual a S: " + ("-" if medidas.get("N_igual_S") is None else f"{medidas['N_igual_S']:.2f}")
    _rotulo(folha, (4, folha.size[1] - 18), txt)
    return folha


def _legenda_pecas(pecas: list[dict], largura: int, n_faltando: int = 0) -> Image.Image:
    linha = 16
    im = Image.new("RGB", (largura, (max(1, len(pecas)) + (1 if n_faltando else 0)) * linha + 6), (20, 20, 24))
    d = ImageDraw.Draw(im)
    f = _fonte(12)
    for k, p in enumerate(pecas):
        lo, hi = _aabb(p)
        dim = "x".join(f"{(b - a) * 100:.0f}" for a, b in zip(lo, hi))
        y = 3 + k * linha
        d.rectangle([4, y + 2, 16, y + 12], fill=CORES[k % len(CORES)])
        d.text((22, y), f"{p['nome']} {p['forma']} {dim} cm  z {lo[2] * 100:.0f}-{hi[2] * 100:.0f}", fill=(235, 235, 235), font=f)
    if not pecas:
        d.text((4, 3), "(sem geometria)", fill=(235, 235, 235), font=f)
    if n_faltando:
        y = 3 + max(1, len(pecas)) * linha
        d.rectangle([4, y + 2, 16, y + 12], outline=(255, 255, 255))
        d.text((22, y), f"tracejado: {n_faltando} pe(s) que a simetria pede", fill=(235, 235, 235), font=f)
    return im


def _tracejado(d: ImageDraw.ImageDraw, xy: np.ndarray, cor, passo: float = 6.0):
    for a, b in zip(xy[:-1], xy[1:]):
        n = max(1, int(np.hypot(*(b - a)) / passo))
        for k in range(0, n, 2):
            p0, p1 = a + (b - a) * k / n, a + (b - a) * min(k + 1, n) / n
            d.line([tuple(p0), tuple(p1)], fill=cor, width=2)


def _painel_geometria(db, nome: str | None, faltando: list[dict] | None = None) -> tuple[Image.Image, list[dict]]:
    if not nome:
        return _painel_ausente("ausente"), []
    q = acervo.quadro(db, nome)
    img = _quadro_ampliado(q)
    pecas = acervo.formas(db, nome)
    d = ImageDraw.Draw(img)
    for k, p in enumerate(pecas):
        for l in arestas(p):
            xy = projetar(l) * ESC
            d.line([tuple(v) for v in xy], fill=CORES[k % len(CORES)], width=2)
    for f in faltando or []:                                  # peças que a simetria pede e o jogo não tem: tracejado branco
        peca = {"forma": "caixa", "min": f["min"], "max": f["max"]}
        for l in arestas(peca):
            _tracejado(d, projetar(l) * ESC, (255, 255, 255))
    return img, pecas


def img_geometria(db, sprites: dict, faltando: list[dict] | None = None) -> Image.Image:
    paineis, legendas = [], []
    for f in ("S", "N"):
        nome = sprites.get(f)
        im, pecas = _painel_geometria(db, nome, [x for x in (faltando or []) if x["pe"]] if f == "S" else None)
        titulo = f"{f}: {nome[-40:]} - {len(pecas)} pecas" if nome else f"{f}: ausente"
        paineis.append((titulo, im))
        legendas.append(_legenda_pecas(pecas, im.size[0], len([x for x in (faltando or []) if x["pe"]]) if f == "S" else 0))
    altura_leg = max(l.size[1] for l in legendas)
    folha = _faixas(paineis, rodape=altura_leg)
    w = paineis[0][1].size[0]
    y0 = 22 + paineis[0][1].size[1]
    for i, l in enumerate(legendas):
        folha.paste(l, (i * (w + 4), y0))
    return folha


def classes_cobertura(q: np.ndarray | None, pecas: list[dict]):
    """Máscaras (desenho, geometria) bool (256,128)."""
    des = np.zeros((acervo.FH, acervo.FW), bool) if q is None else q[..., 3] >= 128
    return des, mascara_geometria(pecas)


def img_cobertura(q: np.ndarray | None, pecas: list[dict], m: dict) -> Image.Image:
    des, geo = classes_cobertura(q, pecas)
    base = np.zeros((acervo.FH, acervo.FW, 3), np.uint8)
    base[:] = FUNDO
    if q is not None:
        a = q[..., 3:4].astype(np.float32) / 255.0
        base = (q[..., :3] * a + base * (1 - a)).astype(np.uint8)
    tint = base.copy()
    cob = des & geo
    tint[cob] = (0.5 * base[cob] + 0.5 * np.array([60, 220, 60])).astype(np.uint8)
    tint[des & ~geo] = (255, 0, 255)
    tint[geo & ~des] = (0, 255, 255)
    ampl = lambda a: Image.fromarray(a).resize((acervo.FW * ESC, acervo.FH * ESC), Image.NEAREST)
    folha = _faixas([("desenho S", ampl(base)), ("verde = coberto pela geometria", ampl(tint))], rodape=40)
    txt = f"cobertura {m['cobertura']:.2f}  sobra {m['sobra']:.2f}  contorno_0 {m['contorno_0']:.2f}" if m.get("cobertura") is not None \
        else "sem geometria"
    _rotulo(folha, (4, folha.size[1] - 36), txt)
    _rotulo(folha, (4, folha.size[1] - 18), "magenta = desenho sem geometria   ciano = geometria sem desenho", fonte=_fonte(12))
    return folha


def _mapa_cor(v: np.ndarray) -> np.ndarray:
    """Valores 0..1 -> RGB (azul escuro -> amarelo), só para ver."""
    t = np.clip(v, 0, 1)[..., None]
    a, b, c = np.array([30, 30, 120]), np.array([220, 60, 120]), np.array([255, 240, 80])
    return np.where(t < 0.5, a + (b - a) * (t * 2), b + (c - b) * ((t - 0.5) * 2)).astype(np.uint8)


def carregar_profundidade(db, nome: str) -> np.ndarray | None:
    row = db.execute("select png from depth_maps where name=?", (nome,)).fetchone()
    if not row:
        return None
    p = acervo._raiz(db) / row[0]
    if not p.exists():
        return None
    im = Image.open(p)
    a = np.asarray(im.convert("LA"))
    return a[..., 0].astype(np.float32) * (a[..., 1] > 0)


def img_profundidade(q: np.ndarray | None, dep: np.ndarray) -> Image.Image:
    nz = dep > 0
    v = np.zeros_like(dep)
    if nz.any():
        lo, hi = dep[nz].min(), dep[nz].max()
        v = np.where(nz, (dep - lo) / max(hi - lo, 1.0), 0)
    rgb = _mapa_cor(v)
    rgb[~nz] = FUNDO
    ampl = lambda a: Image.fromarray(a).resize((acervo.FW * ESC, acervo.FH * ESC), Image.NEAREST)
    folha = _faixas([("desenho S", _quadro_ampliado(q)), ("profundidade (azul = valor baixo, amarelo = alto)", ampl(rgb))], rodape=0)
    return folha


# ---------------------------------------------------------------- medidas

def _props(db, nome: str) -> dict:
    return acervo._props(db, nome)


def _silhueta_espelho(qa: np.ndarray | None, qb: np.ndarray | None) -> float | None:
    """IoU entre o desenho `a` e o desenho `b` espelhado (só o contorno, sem cor): a cor do jogo muda de uma direção
    para outra (luz, sujeira), mas a forma de um objeto simétrico não."""
    if qa is None or qb is None:
        return None
    ma, mb = qa[..., 3] >= 128, qb[:, ::-1, 3] >= 128
    uni = (ma | mb).sum()
    return float((ma & mb).sum() / uni) if uni else None


def _semelhanca_direta(qa: np.ndarray | None, qb: np.ndarray | None) -> float | None:
    """Como `acervo.espelhado`, mas sem espelhar o segundo quadro."""
    if qa is None or qb is None:
        return None
    ma, mb = qa[..., 3] >= 128, qb[..., 3] >= 128
    uni = ma | mb
    if not uni.any():
        return None
    dif = np.abs(qa[..., :3].astype(np.int16) - qb[..., :3].astype(np.int16)).mean(-1) / 255.0
    dif = np.where(ma & mb, dif, 1.0)
    return float(1.0 - dif[uni].mean())


def _eh_espelho(cor: float | None, silhueta: float | None) -> bool:
    """Direção de lado = espelho da outra? A cor do jogo muda de um quadro para o outro (luz, sujeira: numa geladeira
    espelhada `acervo.espelhado` dá só 0,87), por isso vale a cor >= 0,75 junto com a silhueta >= 0,90 (medido em
    sprites de móveis; os que só se parecem de longe ficam abaixo de 0,8 na silhueta)."""
    return bool(cor is not None and silhueta is not None and cor >= 0.75 and silhueta >= 0.90)


def medir(db, sprite_S: str) -> tuple[dict, dict]:
    """Todas as medidas de um sprite. Devolve (medidas, material gráfico para as imagens)."""
    sprites = acervo.direcoes(db, sprite_S)
    if "S" not in sprites:
        sprites = {"S": sprite_S, **sprites}
    nome_S = sprites["S"]
    q_S = acervo.quadro(db, nome_S)
    props = _props(db, nome_S)
    ign: list = []
    pecas = acervo.formas(db, nome_S, ign)
    raw_n = db.execute("select count(*) from geometry where name=?", (nome_S,)).fetchone()[0]

    m: dict = {"sprite": nome_S, "sprites": sprites,
               "tem_quadro_S": q_S is not None, "n_formas_jogo": raw_n,
               "formas_ignoradas": [{"indice": i, "motivo": mt} for i, mt in ign]}
    m["tem_geometria"] = bool(pecas)
    m["n_formas"] = len(pecas)
    m["tipos"] = {t: sum(p["forma"] == t for p in pecas) for t in ("caixa", "cilindro", "prisma")}
    m["pecas"] = pecas
    m["multi_tile"] = "SpriteGridPos" in props
    m["material"] = acervo.material(db, nome_S)
    m["material_props"] = {k: props[k] for k in PROPS_MATERIAL if k in props}
    m["props"] = {k: props[k] for k in PROPS_CHAVE if k in props}
    m["props_geometria"] = {k: v for k, v in db.execute("select key, value from geometry_props where name=?", (nome_S,))}
    m["categoria"] = (db.execute("select category from tiles where name=?", (nome_S,)).fetchone() or [None])[0]

    # caixa envolvente da geometria
    if pecas:
        lo = np.min([_aabb(p)[0] for p in pecas], 0)
        hi = np.max([_aabb(p)[1] for p in pecas], 0)
        m["caixa"] = {"min": _arred(lo), "max": _arred(hi), "largura": _arred(hi[0] - lo[0]),
                      "profundidade": _arred(hi[1] - lo[1]), "altura": _arred(hi[2] - lo[2])}
        m["menor_medida_peca"] = _arred(min(float(np.min(h - l)) for l, h in (_aabb(p) for p in pecas)))
        dimensoes = [(p, _aabb(p)) for p in pecas]
        m["fino"] = bool(m["menor_medida_peca"] < FINO_M or any(
            p["forma"] == "prisma" and (p["ate"] - p["de"]) < FINO_M + 1e-9 for p in pecas))
        m["pecas_finas"] = [p["nome"] for p, (l, h) in dimensoes if float(np.min(h - l)) < FINO_M]
        m["altura_base"] = _arred(lo[2])
    else:
        m["caixa"], m["menor_medida_peca"], m["fino"], m["pecas_finas"], m["altura_base"] = None, None, False, [], None
    m["montado_na_parede"] = bool(
        props.get("MoveType") == "WallObject" or any(k in props for k in ("attachedN", "attachedS", "attachedE", "attachedW")))

    # silhueta × desenho
    if pecas and q_S is not None:
        des, geo = classes_cobertura(q_S, pecas)
        uni, inter = (des | geo).sum(), (des & geo).sum()
        m["contorno_0"] = _arred(inter / uni if uni else 0.0)
        m["cobertura"] = _arred(inter / des.sum() if des.sum() else 0.0)
        m["sobra"] = _arred((geo & ~des).sum() / geo.sum() if geo.sum() else 0.0)
        m["pixels_desenho"], m["pixels_geometria"] = int(des.sum()), int(geo.sum())
    else:
        m["contorno_0"] = m["cobertura"] = m["sobra"] = None

    # direções
    e, n, w = sprites.get("E"), sprites.get("N"), sprites.get("W")
    m["espelhado_E_S"] = _arred(acervo.espelhado(db, nome_S, e)) if e else None
    m["espelhado_W_N"] = _arred(acervo.espelhado(db, n, w)) if (n and w) else None
    q_N = acervo.quadro(db, n) if n else None
    ig = _semelhanca_direta(q_S, q_N)
    m["N_igual_S"] = None if ig is None else _arred(ig)
    q_E, q_W = (acervo.quadro(db, e) if e else None), (acervo.quadro(db, w) if w else None)
    si = _silhueta_espelho(q_S, q_E)
    m["silhueta_espelho_E_S"] = None if si is None else _arred(si)
    si = _silhueta_espelho(q_N, q_W)
    m["silhueta_espelho_W_N"] = None if si is None else _arred(si)
    m["E_e_espelho_de_S"] = _eh_espelho(m["espelhado_E_S"], m["silhueta_espelho_E_S"])
    m["W_e_espelho_de_N"] = _eh_espelho(m["espelhado_W_N"], m["silhueta_espelho_W_N"])
    m["tem_N"] = bool(q_N is not None and (q_N[..., 3] >= 128).any() and not (ig is not None and ig >= 0.97))

    # simetria
    sim = simetria(pecas)
    m["centro_simetria"] = sim["centro"]
    m["pecas_sem_par"] = sim["sem_par"]
    m["pecas_provavelmente_faltando"] = sim["faltando"]
    m["n_pes"] = sim["n_pes"]

    # profundidade
    dep = carregar_profundidade(db, nome_S)
    if dep is None:
        m["profundidade"] = {"existe": False}
    else:
        nz = dep > 0
        des = np.zeros_like(nz) if q_S is None else q_S[..., 3] >= 128
        m["profundidade"] = {"existe": True, "pixels": int(nz.sum()),
                             "cobertura": _arred((nz & des).sum() / des.sum()) if des.sum() else None,
                             "fora_do_desenho": _arred((nz & ~des).sum() / nz.sum()) if nz.sum() else None}
    m["sugestao"] = sugerir(m)
    return m, {"q_S": q_S, "pecas": pecas, "dep": dep}


def _pct(v: float) -> str:
    return f"{round(v * 100)}%"


def sugerir(m: dict) -> list[str]:
    """Dicas curtas, feitas por regras sobre as medidas (para o agente inspetor ler antes de olhar as imagens)."""
    s: list[str] = []
    if not m["tem_quadro_S"]:
        s.append("sem quadro 2x do sprite S: não dá para medir nada, candidato a não portar")
    if not m["tem_geometria"]:
        if m["n_formas_jogo"]:
            motivos = "; ".join(sorted({i["motivo"] for i in m["formas_ignoradas"]}))
            s.append(f"sem geometria aproveitável ({m['n_formas_jogo']} formas do jogo descartadas: {motivos}): candidato a não portar")
        else:
            s.append("sem geometria: candidato a não portar")
        if m["profundidade"]["existe"]:
            s.append("há mapa de profundidade, mas o volume viria só dele (sem caixas para a receita)")
    if m["montado_na_parede"]:
        s.append("objeto de parede (o jogo o prende à parede: MoveType/attached): candidato a não portar")
    if m["fino"]:
        quem = ", ".join(m["pecas_finas"]) or "polígonos de 1 cm"
        s.append(f"objeto fino/vazado (peças finas: {quem}): candidato a não portar")
    cob, sob, iou = m["cobertura"], m["sobra"], m["contorno_0"]
    if cob is not None:
        if cob < 0.85:
            s.append(f"geometria cobre só {_pct(cob)} do desenho: falta peça?")
        if sob > 0.35:
            s.append(f"{_pct(sob)} da geometria cai fora do desenho: medidas do jogo maiores que a arte, ou peça que não aparece")
        if iou < 0.6:
            s.append(f"contorno em 0° baixo (IoU {iou:.2f}): as caixas do jogo não casam com o desenho")
    faltando = m["pecas_provavelmente_faltando"]
    pes = [f for f in faltando if f["pe"]]
    if pes:
        descritos = m["n_pes"]
        s.append(f"{descritos} {'pé descrito' if descritos == 1 else 'pés descritos'}, provável pé escondido "
                 f"(falta{'m' if len(pes) > 1 else ''} {len(pes)}, espelho de {pes[0]['copia_de']}): completar por simetria")
    if m["altura_base"] is not None and m["altura_base"] > 0.5 and not m["montado_na_parede"]:
        s.append(f"a geometria começa a {m['altura_base'] * 100:.0f} cm do chão: objeto suspenso ou sobre outro móvel")
    if m["multi_tile"]:
        s.append(f"ocupa mais de um tile (SpriteGridPos={m['props'].get('SpriteGridPos')}): modelar o conjunto, este é um pedaço")
    if m["E_e_espelho_de_S"]:
        s.append("E é o espelho de S")
    if m["W_e_espelho_de_N"]:
        s.append("W é o espelho de N")
    if m["E_e_espelho_de_S"] and m["W_e_espelho_de_N"]:
        s.append("E/W são só espelhos: bastam S e N")
    if m["tem_N"]:
        s.append("há desenho de trás real (N): usar tras = N")
    elif m["sprites"].get("N"):
        s.append("o desenho N é a frente repetida (ou está vazio): tras = simetrico")
    else:
        s.append("sem desenho de trás (N): tras = simetrico, a traseira é inventada")
    if len(m["sprites"]) < 4:
        n = len(m["sprites"])
        s.append(f"só {n} {'direção' if n == 1 else 'direções'} no acervo ({', '.join(m['sprites'])})")
    if m["caixa"]:
        c = m["caixa"]
        if c["largura"] > 1.05 or c["profundidade"] > 1.05:
            s.append(f"geometria passa do tile ({c['largura']:.2f} x {c['profundidade']:.2f} m)")
        if m["n_formas"] >= 8:
            s.append(f"geometria com {m['n_formas']} peças: objeto complexo")
    if m["material"] == "liso" and not m["material_props"]:
        s.append("material do jogo não informado: conferir pela imagem")
    return s


# ---------------------------------------------------------------- entrada principal

def inspecionar(sprite_S: str, saida: str | Path | None = None, db=None, id: str | None = None) -> dict:
    """Mede o sprite e grava `medidas.json` e as imagens em `<saida>/<id>/`. Devolve as medidas (com `pasta` e `imagens`)."""
    fechar = db is None
    db = db or acervo.abrir()
    try:
        m, extra = medir(db, sprite_S)
        pasta = Path(saida or PADRAO) / (id or _slug(sprite_S))
        pasta.mkdir(parents=True, exist_ok=True)
        sprites = m["sprites"]
        imagens = {}

        def salvar(nome: str, im: Image.Image):
            im.save(pasta / nome)
            imagens[nome] = str(pasta / nome)

        salvar("direcoes.png", img_direcoes(db, sprites, m))
        salvar("geometria.png", img_geometria(db, sprites, m["pecas_provavelmente_faltando"]))
        salvar("cobertura.png", img_cobertura(extra["q_S"], extra["pecas"], m))
        if extra["dep"] is not None:
            salvar("profundidade.png", img_profundidade(extra["q_S"], extra["dep"]))
        m["pasta"] = str(pasta)
        m["imagens"] = imagens
        (pasta / "medidas.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        return m
    finally:
        if fechar:
            db.close()


def resumo(m: dict) -> str:
    c = m["caixa"]
    linhas = [f"sprite: {m['sprite']}   material: {m['material']}   categoria: {m['categoria']}",
              f"direcoes: {', '.join(f'{k}={v}' for k, v in m['sprites'].items())}",
              f"geometria: {m['n_formas']} pecas {m['tipos']} (jogo: {m['n_formas_jogo']})   multi_tile: {m['multi_tile']}   fino: {m['fino']}   parede: {m['montado_na_parede']}"]
    if c:
        linhas.append(f"caixa: {c['largura']:.2f} x {c['profundidade']:.2f} x {c['altura']:.2f} m (larg x prof x alt)   menor medida de peca: {m['menor_medida_peca'] * 100:.1f} cm")
    f = lambda v: "-" if v is None else f"{v:.3f}"
    linhas.append(f"contorno_0: {f(m['contorno_0'])}   cobertura: {f(m['cobertura'])}   sobra: {f(m['sobra'])}")
    linhas.append(f"espelhado E~S: {f(m['espelhado_E_S'])} (silhueta {f(m['silhueta_espelho_E_S'])}, espelho: {m['E_e_espelho_de_S']})   "
                  f"W~N: {f(m['espelhado_W_N'])} (silhueta {f(m['silhueta_espelho_W_N'])}, espelho: {m['W_e_espelho_de_N']})")
    linhas.append(f"N igual a S: {f(m['N_igual_S'])}   tem_N: {m['tem_N']}")
    linhas.append(f"pecas sem par: {m['pecas_sem_par'] or 'nenhuma'}   provavelmente faltando: {len(m['pecas_provavelmente_faltando'])}")
    linhas.append(f"profundidade: {m['profundidade']}")
    linhas.append("sugestao:")
    linhas += [f"  - {s}" for s in m["sugestao"]]
    if "pasta" in m:
        linhas.append(f"saida: {m['pasta']}")
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Inspeção por script de um sprite (porte3d).")
    ap.add_argument("sprite_S")
    ap.add_argument("--saida", help=f"pasta de saída (padrão: {PADRAO})")
    ap.add_argument("--id", help="nome da subpasta (padrão: slug do sprite)")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    m = inspecionar(a.sprite_S, a.saida, id=a.id)
    print(resumo(m))
    return 0


if __name__ == "__main__":
    sys.exit(main())
