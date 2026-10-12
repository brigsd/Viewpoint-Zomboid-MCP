"""Prévia rápida de uma receita, sem Blender: desenha as peças por cima do desenho do jogo (frente e trás)
e mede o quanto a silhueta bate. É a ferramenta do modelador para acertar medidas antes de gerar o modelo.

Uso: python -m porte3d.prever <receita.json> [--saida DIR]
Grava <saida>/<id>_previa.png (padrão: acervo/data/porte3d/previas/) e imprime:
  contorno_frente  IoU entre a silhueta das peças e o desenho de frente (0..1)
  contorno_tras    o mesmo com o desenho de trás (N, ou a frente se a receita usa 'simetrico')
  falta / sobra    fração do desenho sem peça, e de peça fora do desenho (na frente)
"""
from __future__ import annotations

import argparse
import colorsys
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from porte3d import acervo, receita
from porte3d.texturas import projetar

HERE = Path(__file__).resolve().parent
SAIDA = HERE.parent / "acervo" / "data" / "porte3d" / "previas"
Z = 3


def _rot(rx, ry, rz):
    """Euler XYZ do Blender: R = Rz·Ry·Rx (graus)."""
    a, b, c = (math.radians(v) for v in (rx, ry, rz))
    Rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    Ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
    Rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def malha(p: dict) -> tuple[np.ndarray, list[tuple[int, ...]]]:
    """Vértices e faces (polígonos) de uma peça da receita expandida, já com afinar e rot."""
    if p["forma"] == "caixa":
        lo, hi = p["min"], p["max"]
        v = np.array([[(hi if (i >> k) & 1 else lo)[k] for k in range(3)] for i in range(8)], float)
        af = p.get("afinar")
        if af:
            for x in v:
                if x[2] == lo[2]:
                    for lado in af["lados"]:
                        k, s = "xyz".index(lado[1]), (1 if lado[0] == "+" else -1)
                        if (x[k] == hi[k]) == (s > 0):
                            x[k] -= s * af["quanto"]
        f = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    elif p["forma"] == "prisma":
        n = len(p["perfil"])
        v = np.array([((a, t, z) if p["eixo"] == "y" else (t, a, z)) for t in (p["de"], p["ate"]) for a, z in p["perfil"]], float)
        f = [tuple(range(n)), tuple(range(n, 2 * n))] + [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    else:
        n, h = p.get("segmentos", 24), p["altura"]
        r0, r1 = p["raio"], p.get("raio_topo", p["raio"])
        ang = [2 * math.pi * i / n for i in range(n)]
        loc = [(r0 * math.cos(a), r0 * math.sin(a), 0.0) for a in ang] + [(r1 * math.cos(a), r1 * math.sin(a), h) for a in ang]
        perm = {"z": lambda x, y, z: (x, y, z), "x": lambda x, y, z: (z, x, y), "y": lambda x, y, z: (y, z, x)}[p.get("eixo", "z")]
        v = np.array([perm(*q) for q in loc], float) + np.array(p["centro"], float)
        f = [tuple(range(n)), tuple(range(n, 2 * n))] + [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    if p.get("rot"):
        c = (v.min(0) + v.max(0)) / 2
        v = (v - c) @ _rot(*p["rot"]).T + c
    return v, f


def silhueta(pecas: list[dict], ang: float) -> np.ndarray:
    img = Image.new("L", (128, 256), 0)
    dr = ImageDraw.Draw(img)
    for p in pecas:
        v, faces = malha(p)
        sx, sy = projetar(v, ang)
        for f in faces:
            dr.polygon([(sx[i], sy[i]) for i in f], fill=255)
    return np.asarray(img) >= 128


def prever(caminho: str | Path, saida: Path = SAIDA, db=None) -> dict:
    r = receita.expandir(receita.carregar(caminho))
    db = db or acervo.abrir()
    frente = acervo.quadro(db, r["sprites"]["S"])
    tras_nome = r["sprites"].get("N") if r.get("tras") == "N" else None
    tras = acervo.quadro(db, tras_nome) if tras_nome else frente
    if frente is None:
        raise SystemExit(f"sprite {r['sprites']['S']} não encontrado no acervo")
    medidas = {}
    folha = Image.new("RGBA", (2 * 128 * Z + 30, 256 * Z + 40 + 16 * (len(r["pecas"]) // 3 + 1)), (40, 42, 48, 255))
    dr = ImageDraw.Draw(folha)
    for k, (rot, quadro, ang) in enumerate((("frente (0 graus)", frente, 0.0), ("tras (180 graus)", tras, 180.0))):
        des = quadro[..., 3] >= 128
        sil = silhueta(r["pecas"], ang)
        iou = float((des & sil).sum() / max((des | sil).sum(), 1))
        medidas["contorno_" + ("frente" if k == 0 else "tras")] = round(iou, 3)
        if k == 0:
            medidas["falta"] = round(float((des & ~sil).sum() / max(des.sum(), 1)), 3)
            medidas["sobra"] = round(float((sil & ~des).sum() / max(sil.sum(), 1)), 3)
        base = Image.fromarray(quadro).resize((128 * Z, 256 * Z), Image.NEAREST)
        x0 = 10 + k * (128 * Z + 10)
        fundo = Image.new("RGBA", base.size, (40, 42, 48, 255))
        fundo.paste(base, (0, 0), base)
        folha.paste(fundo, (x0, 30))
        d2 = ImageDraw.Draw(folha)
        for i, p in enumerate(r["pecas"]):
            cor = tuple(int(c * 255) for c in colorsys.hsv_to_rgb((i * 0.618034) % 1.0, 0.8, 1.0))
            v, faces = malha(p)
            sx, sy = projetar(v, ang)
            for f in faces:
                pts = [(x0 + sx[j] * Z, 30 + sy[j] * Z) for j in f]
                d2.line(pts + [pts[0]], fill=cor, width=1)
        dr.text((x0, 8), f"{rot}  contorno {iou:.0%}", fill=(255, 255, 0))
    y = 256 * Z + 36
    for i, p in enumerate(r["pecas"]):
        cor = tuple(int(c * 255) for c in colorsys.hsv_to_rgb((i * 0.618034) % 1.0, 0.8, 1.0))
        x = 10 + (i % 3) * 250
        yy = y + (i // 3) * 16
        dr.rectangle([x, yy + 2, x + 10, yy + 12], fill=cor)
        dr.text((x + 14, yy), p["nome"], fill=(230, 230, 230))
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    arq = saida / f"{r['id']}_previa.png"
    folha.save(arq)
    return {"previa": str(arq), **medidas}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("receita")
    ap.add_argument("--saida", type=Path, default=SAIDA)
    a = ap.parse_args(argv)
    try:
        print(json.dumps(prever(a.receita, a.saida), ensure_ascii=False, indent=1))
    except receita.ReceitaInvalida as e:
        print("receita inválida:\n" + str(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
