"""Mesa refeita à mão "como artista": textura em kit (pedaços limpos recortados do desenho do jogo)
aplicada de forma consistente em todas as faces, mais iluminação simples por face.

Kit: TAMPO (centro da superfície, sem as bordas desenhadas), FAIXA (lateral do tampo, sem o ornamento
do canto) e PE (frente de um pé). Uso: python teste_manual_mesa2.py
"""
import sqlite3

import numpy as np
from PIL import Image, ImageDraw

import harness as h
import teste_adesivo2 as t2
from teste_manual_mesa import NAME, manual_boxes

LIGHT = {(1, 0): 0.83, (0, 1): 1.0, (-1, 0): 0.78, (0, -1): 0.9}   # lado direito do jogo é ~17% mais escuro


def rectify(spr, lo, hi, axis, sign, size=(64, 64)):
    """Desentorta uma face de caixa vista na imagem S numa textura retangular (u, v)."""
    W, H = size
    u, v = np.meshgrid((np.arange(W) + 0.5) / W, (np.arange(H) + 0.5) / H)
    p = np.zeros((H, W, 3))
    fixed = hi[axis] if sign > 0 else lo[axis]
    others = [a for a in range(3) if a != axis]
    a0, a1 = others if axis != 1 else (0, 2)
    p[..., axis] = fixed
    p[..., a0] = lo[a0] + u * (hi[a0] - lo[a0])
    p[..., a1] = (hi[a1] - v * (hi[a1] - lo[a1])) if a1 == 1 else lo[a1] + v * (hi[a1] - lo[a1])
    pv = h.project(p.reshape(-1, 3))
    px = np.clip(np.floor(pv[:, 0]).astype(int), 0, h.FW - 1)
    py = np.clip(np.floor(pv[:, 1]).astype(int), 0, h.FH - 1)
    return spr[py, px].reshape(H, W, 4)


def kit(spr, boxes):
    top_lo, top_hi = boxes[-1]
    leg_lo, leg_hi = boxes[2]                         # pé da frente (o mais perto da câmera)
    tampo = rectify(spr, top_lo, top_hi, 1, 1, (96, 96))[14:82, 14:82]          # sem as bordas
    faixa = rectify(spr, top_lo, top_hi, 2, 1, (96, 24))[:, 30:66]               # sem o ornamento do canto
    pe = rectify(spr, leg_lo, leg_hi, 2, 1, (16, 96))
    pe = pe[:, (pe[..., 3] >= 128).mean(0) > 0.9]                                # tira colunas transparentes da borda
    pe = pe[(pe[..., 3] >= 128).mean(1) > 0.9]                                   # e linhas (sombra no pé)
    return {"tampo": tampo, "faixa": faixa, "pe": pe}


def sample(tex, u, v, tile_u=1.0):
    H, W = tex.shape[:2]
    x = np.floor((u * tile_u % 1.0) * W).astype(int).clip(0, W - 1)
    y = np.floor(v * H).astype(int).clip(0, H - 1)
    return tex[y, x]


def render(boxes, k, angle, scale=1):
    H, W = h.FH * scale, h.FW * scale
    ys, xs = np.mgrid[0:H, 0:W]
    q, normal, box, axis, hit = t2.raycast(boxes, angle, (xs + 0.5) / scale, (ys + 0.5) / scale)
    out = np.zeros((H, W, 4), np.uint8)
    n_top = len(boxes) - 1
    for i, (lo, hi) in enumerate(boxes):
        size = hi - lo
        for ax in range(3):
            for sg in (-1, 1):
                m = hit & (box == i) & (axis == ax) & (np.sign(normal[..., ax]) == sg)
                if not m.any():
                    continue
                p = q[m]
                if ax == 1:                                   # tampo (ou fundo)
                    u = (p[:, 0] - lo[0]) / size[0]
                    v = (p[:, 2] - lo[2]) / size[2]
                    col = sample(k["tampo"], u, v)[:, :3].astype(float)
                    shade = 1.0 if sg > 0 else 0.5
                else:                                         # laterais
                    along = 2 if ax == 0 else 0
                    u = (p[:, along] - lo[along]) / size[along]
                    v = (hi[1] - p[:, 1]) / size[1]
                    if i == n_top:
                        col = sample(k["faixa"], u, v, tile_u=max(1.0, size[along] / 3000))[:, :3].astype(float)
                    else:
                        col = sample(k["pe"], u, v)[:, :3].astype(float)
                    key = (sg, 0) if ax == 0 else (0, sg)
                    shade = LIGHT[key]
                out[m, :3] = np.clip(col * shade, 0, 255).astype(np.uint8)
                out[m, 3] = 255
    return out


def main():
    db = sqlite3.connect(h.DATA / "acervo.sqlite")
    spr = h.load_frame(db, NAME)
    boxes = manual_boxes()
    k = kit(spr, boxes)
    # o que o kit recortou, para conferir
    kit_img = Image.new("RGBA", (300, 110), (40, 42, 48, 255))
    x = 4
    for name, t in k.items():
        im = Image.fromarray(t).resize((t.shape[1] * 1, t.shape[0] * 1), Image.NEAREST)
        kit_img.paste(im, (x, 4), im)
        ImageDraw.Draw(kit_img).text((x, 98), name, fill=(255, 255, 0))
        x += t.shape[1] + 20
    kit_img.save(h.DATA / "exp" / "adesivo" / "mesa_kit.png")

    Z, angles = 2, (0, 45, 90, 135, 180, 270)
    rows = [("adesivo (antes)", lambda a: t2.render(boxes, [(t2.bleed(spr), 0.0), (t2.bleed(spr), 180.0)], a)),
            ("kit a mao (depois)", lambda a: render(boxes, k, a))]
    sheet = Image.new("RGBA", ((len(angles) + 1) * h.FW * Z, 2 * (h.FH * Z + 24)), (40, 42, 48, 255))
    dr = ImageDraw.Draw(sheet)
    for r, (label, fn) in enumerate(rows):
        y = r * (h.FH * Z + 24)
        big = Image.fromarray(spr).resize((h.FW * Z, h.FH * Z), Image.NEAREST)
        sheet.paste(big, (0, y + 24), big)
        dr.text((6, y + 4), "jogo", fill=(255, 255, 0))
        for i, a in enumerate(angles):
            big = Image.fromarray(fn(float(a))).resize((h.FW * Z, h.FH * Z), Image.NEAREST)
            sheet.paste(big, ((i + 1) * h.FW * Z, y + 24), big)
            dr.text(((i + 1) * h.FW * Z + 6, y + 4), f"{label} {a}", fill=(120, 255, 120))
    sheet.save(h.DATA / "exp" / "adesivo" / "mesa_kit_comparacao.png")
    frames = []
    for kk in range(36):
        im = Image.fromarray(render(boxes, k, kk * 10.0, scale=2))
        bg = Image.new("RGBA", im.size, (40, 42, 48, 255)); bg.paste(im, (0, 0), im)
        frames.append(bg.convert("P", palette=Image.ADAPTIVE))
    frames[0].save(h.DATA / "exp" / "adesivo" / "mesa_kit.gif", save_all=True, append_images=frames[1:], duration=110, loop=0)


if __name__ == "__main__":
    main()
