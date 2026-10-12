"""Conferência visual das formas do jogo: desenha o contorno das peças de `acervo.formas()` sobre o sprite.

Uso:  python -m porte3d.conferir_formas [sprite ...]     (sem argumentos, roda a lista de casos de teste)

Cada sprite vira um quadro 128x256 ampliado 3x, com o contorno amarelo das arestas projetadas pela câmera do
jogo (fórmula do CONTRATO.md). As folhas vão para acervo/data/exp/porte3d_formas/ (pasta de dados, fora do git).
"""
from __future__ import annotations

import math
import sys

import numpy as np
from PIL import Image, ImageDraw

from . import acervo

ESCALA = 3
SAIDA = acervo.ACERVO_DB.parent / "exp" / "porte3d_formas"
FIXOS = [
    "furniture_tables_high_01_16",
    "appliances_refrigeration_01_0", "appliances_refrigeration_01_1",
    "appliances_refrigeration_01_2", "appliances_refrigeration_01_3",
]


def projetar(p: np.ndarray) -> np.ndarray:
    """(N,3) em metros (receita) -> (N,2) pixels do quadro 128x256 (CONTRATO.md)."""
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    return np.stack([64 + 64 * (x + y), 224 + 32 * (x - y) - 78.38 * z], 1)


def _euler(rot) -> np.ndarray:
    a, b, c = (math.radians(v) for v in rot)
    rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
    rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    return rz @ ry @ rx


def arestas(p: dict) -> list[np.ndarray]:
    """Polilinhas 3D (em metros) do contorno da peça, já com `rot` aplicado em torno do centro da peça."""
    linhas: list[np.ndarray] = []
    if p["forma"] == "caixa":
        a, b = np.array(p["min"]), np.array(p["max"])
        v = np.array([[x, y, z] for x in (a[0], b[0]) for y in (a[1], b[1]) for z in (a[2], b[2])])
        for i in range(8):
            for j in range(i + 1, 8):
                if bin(i ^ j).count("1") == 1:
                    linhas.append(v[[i, j]])
        centro = (a + b) / 2
    elif p["forma"] == "cilindro":
        ax = "xyz".index(p.get("eixo", "z"))
        c0 = np.array(p["centro"], float)
        h = p["altura"]
        ra, rb = p["raio"], p.get("raio_topo", p["raio"])
        o = [i for i in range(3) if i != ax]
        t = np.linspace(0, 2 * math.pi, 25)
        for d, r in ((0.0, ra), (h, rb)):
            anel = np.tile(c0, (len(t), 1))
            anel[:, ax] += d
            anel[:, o[0]] += r * np.cos(t)
            anel[:, o[1]] += r * np.sin(t)
            linhas.append(anel)
        for k in (0, 6, 12, 18):
            lado = np.tile(c0, (2, 1))
            lado[1, ax] += h
            for i, (_, r) in enumerate(((0, ra), (1, rb))):
                lado[i, o[0]] += r * math.cos(t[k])
                lado[i, o[1]] += r * math.sin(t[k])
            linhas.append(lado)
        centro = c0.copy()
        centro[ax] += h / 2
    else:  # prisma
        ex = "xy".index(p["eixo"])
        ha = 1 - ex
        pts = []
        for d in (p["de"], p["ate"]):
            anel = np.zeros((len(p["perfil"]), 3))
            anel[:, ha] = [q[0] for q in p["perfil"]]
            anel[:, 2] = [q[1] for q in p["perfil"]]
            anel[:, ex] = d
            pts.append(anel)
            linhas.append(np.vstack([anel, anel[:1]]))
        for i in range(len(p["perfil"])):
            linhas.append(np.array([pts[0][i], pts[1][i]]))
        todos = np.vstack(pts)
        centro = (todos.min(0) + todos.max(0)) / 2
    if "rot" in p:
        r = _euler(p["rot"])
        linhas = [(l - centro) @ r.T + centro for l in linhas]
    return linhas


def desenhar(db, nome: str, rotulo: bool = True) -> Image.Image:
    q = acervo.quadro(db, nome)
    fundo = Image.new("RGBA", (acervo.FW, acervo.FH), (58, 60, 70, 255))
    if q is not None:
        im = Image.fromarray(q)
        fundo.alpha_composite(im)
    img = fundo.resize((acervo.FW * ESCALA, acervo.FH * ESCALA), Image.NEAREST)
    d = ImageDraw.Draw(img)
    ign: list = []
    pecas = acervo.formas(db, nome, ign)
    cores = [(255, 230, 0), (0, 255, 255), (255, 80, 255), (120, 255, 80), (255, 140, 0)]
    for k, p in enumerate(pecas):
        for l in arestas(p):
            xy = projetar(l) * ESCALA
            d.line([tuple(v) for v in xy], fill=cores[k % len(cores)] + (255,), width=1)
    if rotulo:
        formas_n = ",".join(sorted({p["forma"][:3] for p in pecas})) or "-"
        d.text((3, 3), f"{nome[-34:]}", fill=(255, 255, 255, 255))
        d.text((3, 15), f"{len(pecas)} pecas [{formas_n}] ign {len(ign)}", fill=(255, 255, 255, 255))
    return img


def folha(db, nomes: list[str], arquivo: str, colunas: int = 5) -> str:
    SAIDA.mkdir(parents=True, exist_ok=True)
    tiles = [desenhar(db, n) for n in nomes]
    w, h = tiles[0].size
    linhas = (len(tiles) + colunas - 1) // colunas
    f = Image.new("RGBA", (w * min(colunas, len(tiles)), h * linhas), (0, 0, 0, 255))
    for i, t in enumerate(tiles):
        f.paste(t, ((i % colunas) * w, (i // colunas) * h))
    caminho = SAIDA / arquivo
    f.convert("RGB").save(caminho)
    return str(caminho)


def _achar(db, consulta: str, n: int, extra: str = "") -> list[str]:
    return [r[0] for r in db.execute(consulta + f" limit {n}")]


def main(argv: list[str]) -> int:
    db = acervo.abrir()
    if len(argv) > 1:
        print(folha(db, argv[1:], "sprites.png"))
        return 0
    esc = "join sprites s on s.name = g.name and s.scale = 2"
    print(folha(db, FIXOS, "01_mesa_e_geladeiras.png"))
    cil = _achar(db, f"select g.name from geometry g {esc} group by g.name having sum(shape = 'cylinder') > 0 "
                     f"and count(*) <= 3 order by random()", 5)
    print(folha(db, cil, "02_cilindros.png"))
    cil_rot = _achar(db, f"select g.name from geometry g {esc} where shape = 'cylinder' and "
                         f"(abs(ry) > 20000 or (abs(rx) > 20000 and abs(rx - 2700000) > 20000 and "
                         f"abs(rx + 900000) > 20000)) order by random()", 5)
    print(folha(db, cil_rot, "03_cilindros_inclinados.png"))
    poli = _achar(db, f"select g.name from geometry g {esc} group by g.name having sum(shape = 'polygon') > 0 "
                      f"and sum(shape != 'polygon') = 0 and count(*) <= 4 order by random()", 5)
    print(folha(db, poli, "04_poligonos.png"))
    poli_misto = _achar(db, f"select g.name from geometry g {esc} where raw like '%plane = YZ%' "
                            f"group by g.name order by random()", 5)
    print(folha(db, poli_misto, "05_poligonos_yz.png"))
    varias = _achar(db, f"select g.name from geometry g {esc} where shape = 'box' group by g.name "
                        f"having count(*) between 5 and 12 order by random()", 5)
    print(folha(db, varias, "06_varias_caixas.png"))
    girada = _achar(db, f"select g.name from geometry g {esc} where shape = 'box' and "
                        f"((abs(ry) > 100000 and abs(ry) < 800000) or (abs(rx) > 100000 and abs(rx) < 800000) "
                        f"or (abs(rz) > 100000 and abs(rz) < 800000)) group by g.name order by random()", 10)
    print(folha(db, girada, "07_caixas_giradas.png"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
