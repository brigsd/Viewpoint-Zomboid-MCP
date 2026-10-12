"""Prepara a pasta de entrada de um objeto: quadros do jogo, receita expandida e cores estimadas (ver CONTRATO.md).

Uso:  python -m porte3d.preparar <receita.json> <saida_dir>      (cria <saida_dir>/<id>/entrada/)
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.spatial import ConvexHull, QhullError

from . import acervo, receita
from .conferir_formas import arestas, projetar

FW, FH = acervo.FW, acervo.FH
PROF_Z = 0.8165      # profundidade na direção da câmera (+x, −y, +z): x − y + 0,8165·z


def _triangulos(p: dict) -> np.ndarray:
    """Triângulos 3D (M,3,3) da casca convexa da peça (o prisma não convexo fica com a casca)."""
    v = np.vstack(arestas(p))
    try:
        h = ConvexHull(v)
    except QhullError:      # peça achatada demais: sem volume
        return np.zeros((0, 3, 3))
    return v[h.simplices]


def mapa_de_pecas(pecas: list[dict]) -> np.ndarray:
    """Para cada pixel do quadro 128x256, o índice da peça mais perto da câmera (−1 se nenhuma cobre)."""
    prof = np.full((FH, FW), -np.inf)
    idx = np.full((FH, FW), -1, int)
    for k, p in enumerate(pecas):
        for tri in _triangulos(p):
            xy = projetar(tri)
            d = tri[:, 0] - tri[:, 1] + PROF_Z * tri[:, 2]
            (x0, y0), (x1, y1), (x2, y2) = xy
            area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
            if abs(area) < 1e-9:
                continue
            ax, bx = max(int(np.floor(xy[:, 0].min())), 0), min(int(np.ceil(xy[:, 0].max())), FW - 1)
            ay, by = max(int(np.floor(xy[:, 1].min())), 0), min(int(np.ceil(xy[:, 1].max())), FH - 1)
            if ax > bx or ay > by:
                continue
            xs, ys = np.meshgrid(np.arange(ax, bx + 1) + 0.5, np.arange(ay, by + 1) + 0.5)
            w0 = ((x1 - xs) * (y2 - ys) - (x2 - xs) * (y1 - ys)) / area
            w1 = ((x2 - xs) * (y0 - ys) - (x0 - xs) * (y2 - ys)) / area
            w2 = 1 - w0 - w1
            dentro = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
            z = w0 * d[0] + w1 * d[1] + w2 * d[2]
            sub_p = prof[ay:by + 1, ax:bx + 1]
            ganha = dentro & (z > sub_p)
            sub_p[ganha] = z[ganha]
            idx[ay:by + 1, ax:bx + 1][ganha] = k
    return idx


def estimar_cores(pecas: list[dict], frente: np.ndarray, ja_tem: dict | None = None) -> dict:
    """Cor sRGB (mediana dos pixels opacos) de cada material das peças que ainda não tem cor em `ja_tem`.
    Cada pixel vale para a peça mais perto da câmera; sem pixels próprios, usa a mediana do desenho todo."""
    ja_tem = ja_tem or {}
    opaco = frente[..., 3] >= 200
    todos = frente[opaco][:, :3]
    geral = [int(round(v)) for v in np.median(todos, axis=0)] if len(todos) else [128, 128, 128]
    idx = mapa_de_pecas(pecas)
    cores = {}
    for m in dict.fromkeys(p["material"] for p in pecas):
        if m in ja_tem:
            continue
        donas = [k for k, p in enumerate(pecas) if p["material"] == m]
        pix = frente[opaco & np.isin(idx, donas)][:, :3]
        cores[m] = [int(round(v)) for v in np.median(pix, axis=0)] if len(pix) else list(geral)
    return cores


def _salvar(rgba: np.ndarray, caminho: Path) -> None:
    Image.fromarray(rgba).save(caminho)


def preparar(receita_path: str | Path, saida_dir: str | Path, db: sqlite3.Connection | None = None) -> Path:
    """Cria `<saida_dir>/<id>/entrada/` com frente, tras (com e sem bleed) e a receita expandida com cores.
    Devolve a pasta `<saida_dir>/<id>/`."""
    r = receita.carregar(receita_path)
    db = db or acervo.abrir()
    s_nome = r["sprites"]["S"]
    frente = acervo.quadro(db, s_nome)
    if frente is None:
        raise FileNotFoundError(f"sprite S sem quadro de escala 2 no acervo: {s_nome}")
    if r.get("tras", "simetrico") == "N":
        tras = acervo.quadro(db, r["sprites"]["N"])
        if tras is None:
            raise FileNotFoundError(f"sprite N sem quadro de escala 2 no acervo: {r['sprites']['N']}")
    else:
        tras = frente
    exp = receita.expandir(r)
    exp["cores"] = {**exp.get("cores", {}), **estimar_cores(exp["pecas"], frente, exp.get("cores"))}

    pasta = Path(saida_dir) / r["id"]
    entrada = pasta / "entrada"
    entrada.mkdir(parents=True, exist_ok=True)
    _salvar(acervo.bleed(frente), entrada / "frente.png")
    _salvar(acervo.bleed(tras), entrada / "tras.png")
    _salvar(frente, entrada / "frente_original.png")
    # a folha do crítico compara sempre com o desenho de trás DE VERDADE do jogo (N, se existir),
    # mesmo quando a receita escolheu texturizar a traseira com a frente ('simetrico')
    n_nome = r["sprites"].get("N")
    n_real = acervo.quadro(db, n_nome) if n_nome else None
    _salvar(n_real if n_real is not None else tras, entrada / "tras_original.png")
    (entrada / "receita.json").write_text(json.dumps(exp, indent=2, ensure_ascii=False), encoding="utf-8")
    return pasta


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("uso: python -m porte3d.preparar <receita.json> <saida_dir>")
        return 2
    try:
        print(preparar(argv[1], argv[2]))
    except (receita.ReceitaInvalida, FileNotFoundError) as e:
        print(f"erro: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
