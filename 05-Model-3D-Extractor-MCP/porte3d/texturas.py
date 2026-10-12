"""Compõe as texturas finais do atlas a partir dos buffers assados no Blender (ver CONTRATO.md) e grava os
modelos finais (OBJ + MTL), um por nível gráfico.

  arte      — modo "adesivo": cada texel pega a cor do pixel do desenho do jogo onde ele aparece, na vista de
              frente (0°) ou de trás (180°), a que enxerga melhor; o que nenhuma vista enxerga recebe a cor média
              da mesma face da mesma peça. Modo "kit": recortes limpos do desenho, aplicados por face, com a
              diferença de luz entre faces; faces sem recorte caem no adesivo.
  realista  — cor do material (Blender) × oclusão de ambiente.

Uso: python -m porte3d.texturas <pasta_objeto>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

FACES = ("+x", "-x", "+y", "-y", "+z", "-z")
LUZ = {"+x": 0.83, "-x": 0.78, "-y": 1.0, "+y": 0.9, "+z": 1.0, "-z": 0.5}   # luz pintada por face no desenho do jogo
VIS_MIN = 0.02


def projetar(p: np.ndarray, ang: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Ponto da receita (metros) -> pixel no quadro 128x256 do jogo, com o objeto girado `ang` graus em z."""
    t = np.radians(ang)
    x = p[..., 0] * np.cos(t) - p[..., 1] * np.sin(t)
    y = p[..., 0] * np.sin(t) + p[..., 1] * np.cos(t)
    return 64 + 64 * (x + y), 224 + 32 * (x - y) - 78.38 * p[..., 2]


def face_de(normal: np.ndarray) -> np.ndarray:
    """Índice em FACES da direção dominante da normal."""
    k = np.abs(normal).argmax(-1)
    neg = np.take_along_axis(normal, k[..., None], -1)[..., 0] < 0
    return k * 2 + neg


def limites(p: dict) -> tuple[np.ndarray, np.ndarray]:
    if p["forma"] == "caixa":
        return np.array(p["min"], float), np.array(p["max"], float)
    if p["forma"] == "prisma":
        a = [q[0] for q in p["perfil"]]
        z = [q[1] for q in p["perfil"]]
        if p["eixo"] == "y":
            return np.array([min(a), p["de"], min(z)]), np.array([max(a), p["ate"], max(z)])
        return np.array([p["de"], min(a), min(z)]), np.array([p["ate"], max(a), max(z)])
    r = max(p["raio"], p.get("raio_topo", 0))
    c = np.array(p["centro"], float)
    k = "xyz".index(p.get("eixo", "z"))
    lo, hi = c - r, c + r
    lo[k], hi[k] = c[k], c[k] + p["altura"]
    return lo, hi


def uv_da_face(pos: np.ndarray, lo: np.ndarray, hi: np.ndarray, face: str) -> tuple[np.ndarray, np.ndarray, float]:
    """(u, v) de 0 a 1 dentro da face da caixa envolvente da peça, e o comprimento da face na direção u.
    Faces laterais: u na horizontal (coordenada crescente), v de cima para baixo. Topo/fundo: u em x, v de y alto a y baixo."""
    tam = hi - lo
    if face in ("+z", "-z"):
        return (pos[..., 0] - lo[0]) / tam[0], (hi[1] - pos[..., 1]) / tam[1], tam[0]
    k = 1 if face[1] == "x" else 0                      # face x varia em y; face y varia em x
    return (pos[..., k] - lo[k]) / tam[k], (hi[2] - pos[..., 2]) / tam[2], tam[k]


def retificar(quadro: np.ndarray, lo: np.ndarray, hi: np.ndarray, face: str, tam=(96, 96)) -> np.ndarray:
    """Desentorta uma face da caixa vista no desenho de frente numa imagem retangular (convenção de uv_da_face)."""
    w, h = tam
    u, v = np.meshgrid((np.arange(w) + 0.5) / w, (np.arange(h) + 0.5) / h)
    p = np.zeros((h, w, 3))
    k = "xyz".index(face[1])
    p[..., k] = hi[k] if face[0] == "+" else lo[k]
    if face in ("+z", "-z"):
        p[..., 0] = lo[0] + u * (hi[0] - lo[0])
        p[..., 1] = hi[1] - v * (hi[1] - lo[1])
    else:
        j = 1 if face[1] == "x" else 0
        p[..., j] = lo[j] + u * (hi[j] - lo[j])
        p[..., 2] = hi[2] - v * (hi[2] - lo[2])
    sx, sy = projetar(p)
    px = np.clip(np.floor(sx).astype(int), 0, quadro.shape[1] - 1)
    py = np.clip(np.floor(sy).astype(int), 0, quadro.shape[0] - 1)
    return quadro[py, px]


def recorte(quadro, receita, nome):
    rc = receita["arte"]["recortes"][nome]
    peca = next(p for p in receita["pecas"] if p["nome"] == rc["peca"])
    lo, hi = limites(peca)
    img = retificar(quadro, lo, hi, rc["face"])
    h, w = img.shape[:2]
    u0, v0, u1, v1 = rc["recorte"]
    img = img[int(v0 * h):max(int(v1 * h), int(v0 * h) + 1), int(u0 * w):max(int(u1 * w), int(u0 * w) + 1)]
    if rc.get("limpar_transparente"):
        img = img[:, (img[..., 3] >= 128).mean(0) > 0.9]
        img = img[(img[..., 3] >= 128).mean(1) > 0.9]
    if img.size == 0:
        raise ValueError(f"recorte {nome} ficou vazio")
    return img, rc["face"]


def adesivo(buf: dict, vistas: list[tuple[np.ndarray, float, np.ndarray]]) -> tuple[np.ndarray, np.ndarray]:
    """Cor por texel tirada da vista que melhor o enxerga. Devolve (rgb float, máscara de texels resolvidos)."""
    pos, peca = buf["posicao"], buf["peca"]
    valido = peca >= 0
    out = np.zeros(pos.shape[:2] + (3,), np.float32)
    melhor = np.zeros(pos.shape[:2], np.float32)
    for quadro, ang, vis in vistas:
        sx, sy = projetar(pos, ang)
        px, py = np.floor(sx).astype(int), np.floor(sy).astype(int)
        dentro = (px >= 0) & (px < quadro.shape[1]) & (py >= 0) & (py < quadro.shape[0])
        pxc, pyc = np.clip(px, 0, quadro.shape[1] - 1), np.clip(py, 0, quadro.shape[0] - 1)
        cor = quadro[pyc, pxc]
        bom = valido & dentro & (cor[..., 3] >= 128) & (vis > VIS_MIN) & (vis > melhor)
        out[bom] = cor[bom][:, :3]
        melhor[bom] = vis[bom]
    return out, melhor > 0


def preencher(out: np.ndarray, ok: np.ndarray, buf: dict) -> np.ndarray:
    """Texels que nenhuma vista enxerga: média da mesma face da mesma peça; senão da peça; senão de tudo."""
    peca, face = buf["peca"], face_de(buf["normal"])
    falta = (peca >= 0) & ~ok
    if not falta.any():
        return out
    geral = out[ok].mean(0) if ok.any() else np.full(3, 128.0)
    chave = peca.astype(np.int64) * 6 + face
    for c in np.unique(chave[falta]):
        m = falta & (chave == c)
        vistos = ok & (chave == c)
        if not vistos.any():
            vistos = ok & (peca == c // 6)
        out[m] = out[vistos].mean(0) if vistos.any() else geral
    return out


def kit(buf: dict, receita: dict, quadro: np.ndarray, out: np.ndarray, ok: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    arte = receita["arte"]
    cache = {n: recorte(quadro, receita, n) for n in arte["recortes"]}
    pos, peca, face = buf["posicao"], buf["peca"], face_de(buf["normal"])
    pecas = receita["pecas"]
    for i, p in enumerate(pecas):
        mapa = arte["faces"].get(p.get("origem", p["nome"]), {})
        lo, hi = limites(p)
        for fi, f in enumerate(FACES):
            nome = mapa.get(f) or (mapa.get("lados") if f[1] != "z" else None)
            if not nome:
                continue
            m = (peca == i) & (face == fi)
            if not m.any():
                continue
            img, f_origem = cache[nome]
            u, v, comp = uv_da_face(pos[m], lo, hi, f)
            rep = arte.get("repetir", {}).get(nome)
            if rep:
                u = u * max(1.0, comp / rep) % 1.0
            h, w = img.shape[:2]
            x = np.clip((np.clip(u, 0, 0.9999) * w).astype(int), 0, w - 1)
            y = np.clip((np.clip(v, 0, 0.9999) * h).astype(int), 0, h - 1)
            out[m] = img[y, x, :3] * (LUZ[f] / LUZ[f_origem])
            ok[m] = True
    return out, ok


def srgb(lin: np.ndarray) -> np.ndarray:
    c = np.clip(lin, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def gravar_obj(pasta: Path, ident: str, nivel: str) -> None:
    linhas = (pasta / "malha.obj").read_text(encoding="utf-8").splitlines()
    corpo = [l for l in linhas if not l.startswith(("mtllib", "usemtl"))]
    k = next(i for i, l in enumerate(corpo) if l.startswith("f "))
    corpo.insert(k, f"usemtl {ident}_{nivel}")
    (pasta / f"{ident}_{nivel}.obj").write_text(f"mtllib {ident}_{nivel}.mtl\n" + "\n".join(corpo) + "\n", encoding="utf-8")
    (pasta / f"{ident}_{nivel}.mtl").write_text(
        f"newmtl {ident}_{nivel}\nKa 1 1 1\nKd 1 1 1\nKs 0 0 0\nd 1\nillum 1\nmap_Kd {nivel}.png\n", encoding="utf-8")


def compor(pasta: Path) -> dict:
    pasta = Path(pasta)
    receita = json.loads((pasta / "entrada" / "receita.json").read_text(encoding="utf-8"))
    b = pasta / "buffers"
    buf = {k: np.load(b / f"{k}.npy") for k in ("posicao", "normal", "peca", "vis_0", "vis_180", "ao", "albedo")}
    frente = np.asarray(Image.open(pasta / "entrada" / "frente.png").convert("RGBA"))
    tras = np.asarray(Image.open(pasta / "entrada" / "tras.png").convert("RGBA"))

    out, ok = adesivo(buf, [(frente, 0.0, buf["vis_0"]), (tras, 180.0, buf["vis_180"])])
    vistos = float(ok[buf["peca"] >= 0].mean())
    if receita["arte"]["modo"] == "kit":
        out, ok = kit(buf, receita, frente, out, ok)
    out = preencher(out, ok, buf)
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB").save(pasta / "arte.png")

    real = buf["albedo"] * (0.30 + 0.70 * np.clip(buf["ao"], 0, 1)[..., None] ** 0.9)
    Image.fromarray((srgb(real) * 255 + 0.5).astype(np.uint8), "RGB").save(pasta / "realista.png")
    for nivel in ("arte", "realista"):
        gravar_obj(pasta, receita["id"], nivel)
    return {"texels_vistos_no_desenho": round(vistos, 3)}


if __name__ == "__main__":
    print(compor(Path(sys.argv[1])))
