"""Converte um pixel do desenho do jogo (quadro 128x256) em ponto 3D da receita (metros), sobre um plano.

Serve para achar onde uma marca do desenho (botão, mancha, linha) fica no modelo: o pixel sozinho não dá o ponto,
porque o desenho é uma projeção; é preciso dizer em que plano a marca está (uma face da peça).

Uso (a partir de 05-Model-3D-Extractor-MCP/):
    python -m porte3d.pixel3d <plano> <valor> <u> <v> [--ang 0]

  plano   eixo fixo da face: x, y ou z. `x 0.4865` é a face direita de uma peça que termina em x = 0.4865.
  u v     pixel no quadro 128x256 do `entrada/frente_original.png` (u para a direita, v para baixo).
  --ang   giro do objeto em graus; 0 é a frente, 180 é a traseira.

Exemplo: o botão preto do industrial_bake_o_matic, na face direita da tampa, no pixel (92, 109):
    python -m porte3d.pixel3d x 0.4865 92 109      ->  y = -0.05, z = 1.685

Imprime as duas coordenadas livres e o erro em pixels. Erro acima de 1 px quer dizer que o ponto não cai naquele
plano; teste outro plano (outra face) ou outro valor.
"""
from __future__ import annotations

import argparse

import numpy as np

from porte3d.texturas import projetar

EIXOS = {"x": 0, "y": 1, "z": 2}


def _pixel(p: np.ndarray, ang: float) -> tuple[float, float]:
    u, v = projetar(np.asarray([p], dtype=float), ang)
    return float(np.ravel(u)[0]), float(np.ravel(v)[0])


def achar(plano: str, valor: float, u: float, v: float, ang: float = 0.0) -> dict:
    fixo = EIXOS[plano]
    livres = [i for i in range(3) if i != fixo]
    faixas = {0: (-1.2, 1.2), 1: (-1.2, 1.2), 2: (0.0, 2.6)}

    def erro(a: float, b: float) -> float:
        p = [0.0, 0.0, 0.0]
        p[fixo], p[livres[0]], p[livres[1]] = valor, a, b
        pu, pv = _pixel(np.array(p), ang)
        return (pu - u) ** 2 + (pv - v) ** 2

    # busca em grade grossa e refinamento em duas passagens
    (a0, a1), (b0, b1) = faixas[livres[0]], faixas[livres[1]]
    melhor = None
    passo = 0.02
    for _ in range(3):
        for a in np.arange(a0, a1 + passo, passo):
            for b in np.arange(b0, b1 + passo, passo):
                e = erro(a, b)
                if melhor is None or e < melhor[0]:
                    melhor = (e, float(a), float(b))
        _, a, b = melhor
        a0, a1, b0, b1 = a - passo, a + passo, b - passo, b + passo
        passo /= 10
    e, a, b = melhor
    return {plano: valor, "xyz"[livres[0]]: round(a, 3), "xyz"[livres[1]]: round(b, 3), "erro_px": round(e ** 0.5, 2)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plano", choices=EIXOS)
    ap.add_argument("valor", type=float)
    ap.add_argument("u", type=float)
    ap.add_argument("v", type=float)
    ap.add_argument("--ang", type=float, default=0.0)
    a = ap.parse_args()
    print(achar(a.plano, a.valor, a.u, a.v, a.ang))
