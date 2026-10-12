"""Dois níveis gráficos para a mesma mesa:
  ARTE      — textura em kit recortada do desenho do jogo (fiel ao estilo pixel do Zomboid);
  REALISTA  — textura de material em alta resolução gerada por código (veio de madeira), nas cores
              tiradas da arte, com sombra de contato pintada. O Viewpoint só aceita uma textura de cor
              (map_Kd), então todo o "volume" tem que estar pintado na textura ou na geometria.
Uso: python teste_realista_mesa.py
"""
import sqlite3

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter

import harness as h
import teste_manual_mesa2 as m2
from teste_manual_mesa import NAME, manual_boxes

RNG = np.random.default_rng(7)


def mean_color(tex):
    a = tex[..., 3] >= 128
    return tex[a][:, :3].astype(float).mean(0)


def wood(w, hgt, base, along="u", rings=7.0, contrast=0.22, planks=0):
    """Veio de madeira procedural: faixas onduladas + poros + variação por tábua, em torno da cor base."""
    v, u = np.mgrid[0:hgt, 0:w] / np.array([hgt, w])[:, None, None]
    across, length = (v, u) if along == "u" else (u, v)
    warp = gaussian_filter(RNG.standard_normal((hgt, w)), 18) * 9
    grain = np.sin((across * rings * 6.283) + warp + 2.5 * np.sin(length * 3.1))
    fine = gaussian_filter(RNG.standard_normal((hgt, w)), (0.6, 6) if along == "u" else (6, 0.6))
    shade = 1.0 + contrast * 0.5 * grain + 0.10 * fine / max(fine.std(), 1e-6) * 0.5
    if planks:
        idx = np.floor(across * planks)
        shade *= 1.0 + 0.06 * (RNG.random(planks + 1)[idx.astype(int)] - 0.5) * 2
        seam = np.abs((across * planks) % 1.0 - 0.0) < 0.012
        shade[seam] *= 0.6
    col = base[None, None, :] * shade[..., None]
    return np.dstack([col.clip(0, 255), np.full((hgt, w), 255)]).astype(np.uint8)


def contact_shadow(tex, top=0.0, bottom=0.0, sides=0.0, strength=0.35):
    """Escurece as bordas onde a peça encosta em outra (sombra de contato pintada)."""
    hgt, w = tex.shape[:2]
    v, u = np.mgrid[0:hgt, 0:w] / np.array([hgt, w])[:, None, None]
    f = np.ones((hgt, w))
    if top:
        f *= 1 - strength * np.exp(-v / top)
    if bottom:
        f *= 1 - strength * np.exp(-(1 - v) / bottom)
    if sides:
        f *= 1 - strength * 0.5 * (np.exp(-u / sides) + np.exp(-(1 - u) / sides))
    out = tex.copy()
    out[..., :3] = (tex[..., :3] * f[..., None]).clip(0, 255).astype(np.uint8)
    return out


def realistic_kit(art_kit):
    top_c, band_c, leg_c = (mean_color(art_kit[k]) for k in ("tampo", "faixa", "pe"))
    tampo = contact_shadow(wood(512, 512, top_c * 1.05, "u", rings=9, planks=4), sides=0.03, strength=0.25)
    faixa = contact_shadow(wood(512, 96, band_c, "u", rings=3, contrast=0.15), top=0.12, strength=0.45)
    pe = contact_shadow(wood(64, 512, leg_c, "v", rings=2, contrast=0.12), top=0.05, bottom=0.03, strength=0.5)
    return {"tampo": tampo, "faixa": faixa, "pe": pe}


def main():
    db = sqlite3.connect(h.DATA / "acervo.sqlite")
    spr = h.load_frame(db, NAME)
    boxes = manual_boxes()
    arte = m2.kit(spr, boxes)
    real = realistic_kit(arte)
    S, angles = 4, (0, 60, 180)
    crop = (0, 110, 128, 256)
    cw, ch = (crop[2] - crop[0]) * S, (crop[3] - crop[1]) * S
    sheet = Image.new("RGBA", ((len(angles) + 1) * cw, 2 * (ch + 26)), (40, 42, 48, 255))
    dr = ImageDraw.Draw(sheet)
    for r, (label, k) in enumerate((("nivel ARTE", arte), ("nivel REALISTA", real))):
        y = r * (ch + 26)
        orig = Image.fromarray(spr).crop(crop).resize((cw, ch), Image.NEAREST)
        sheet.paste(orig, (0, y + 26), orig)
        dr.text((6, y + 6), "jogo (original)", fill=(255, 255, 0))
        for i, a in enumerate(angles):
            im = Image.fromarray(m2.render(boxes, k, float(a), scale=S)).crop(tuple(c * S for c in crop))
            sheet.paste(im, ((i + 1) * cw, y + 26), im)
            dr.text(((i + 1) * cw + 6, y + 6), f"{label}  {a} graus", fill=(120, 255, 120))
    sheet.save(h.DATA / "exp" / "adesivo" / "mesa_dois_niveis.png")
    frames = []
    for kk in range(36):
        im = Image.fromarray(m2.render(boxes, real, kk * 10.0, scale=3)).crop(tuple(c * 3 for c in crop))
        bg = Image.new("RGBA", im.size, (40, 42, 48, 255)); bg.paste(im, (0, 0), im)
        frames.append(bg.convert("P", palette=Image.ADAPTIVE))
    frames[0].save(h.DATA / "exp" / "adesivo" / "mesa_realista.gif", save_all=True, append_images=frames[1:], duration=110, loop=0)


if __name__ == "__main__":
    main()
