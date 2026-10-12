"""Mesa ajustada à mão: medidas do tampo e dos pés refeitas para bater com o desenho do jogo.
Compara com a versão automática (caixas do jogo). Uso: python teste_manual_mesa.py"""
import sqlite3
import numpy as np
from PIL import Image, ImageDraw
import harness as h
import teste_adesivo2 as t2
from teste_adesivo import bleed

NAME = "furniture_tables_high_01_16"
# medidas ajustadas (1/10000 de tile): tampo 0,98 m x 0,98 m, de 0,58 a 0,72 m de altura; pés 8 cm, 1,6 cm mais à esquerda
TOP_HALF, TOP_LO, TOP_HI, SHIFT, LEG_HALF = 4900, 5800, 7200, -80, 400
LEGS = ((-3900, 4100), (3900, -4100), (3900, 4100), (-3900, -4100))


def manual_boxes():
    out = [(np.array([cx + SHIFT - LEG_HALF, 0, cz - SHIFT - LEG_HALF]),
            np.array([cx + SHIFT + LEG_HALF, TOP_LO, cz - SHIFT + LEG_HALF])) for cx, cz in LEGS]
    out.append((np.array([-TOP_HALF, TOP_LO, -TOP_HALF]), np.array([TOP_HALF, TOP_HI, TOP_HALF])))
    return out


def auto_boxes(db):
    b = t2.boxes_of(db, NAME)
    return b + [(np.minimum(h.rot_y(lo, 180), h.rot_y(hi, 180)), np.maximum(h.rot_y(lo, 180), h.rot_y(hi, 180))) for lo, hi in b]


def main():
    db = sqlite3.connect(h.DATA / "acervo.sqlite")
    spr = h.load_frame(db, NAME)
    views = [(bleed(spr), 0.0), (bleed(spr), 180.0)]
    ms = spr[..., 3] >= 200
    rows = [("automatico", auto_boxes(db)), ("ajustado a mao", manual_boxes())]
    Z, angles = 2, (0, 45, 90, 135, 180, 270)
    sheet = Image.new("RGBA", ((len(angles) + 1) * h.FW * Z, 2 * (h.FH * Z + 24)), (40, 42, 48, 255))
    dr = ImageDraw.Draw(sheet)
    for r, (label, boxes) in enumerate(rows):
        y = r * (h.FH * Z + 24)
        big = Image.fromarray(spr).resize((h.FW * Z, h.FH * Z), Image.NEAREST)
        sheet.paste(big, (0, y + 24), big)
        dr.text((6, y + 4), "jogo", fill=(255, 255, 0))
        for i, a in enumerate(angles):
            im = t2.render(boxes, views, float(a))
            if a == 0:
                mm = im[..., 3] >= 128
                iou = (ms & mm).sum() / (ms | mm).sum()
            big = Image.fromarray(im).resize((h.FW * Z, h.FH * Z), Image.NEAREST)
            sheet.paste(big, ((i + 1) * h.FW * Z, y + 24), big)
            dr.text(((i + 1) * h.FW * Z + 6, y + 4), f"{label} {a}" + (f"  (contorno {iou:.0%})" if a == 0 else ""), fill=(120, 255, 120))
    sheet.save(h.DATA / "exp" / "adesivo" / "mesa_auto_vs_manual.png")
    frames = []
    for k in range(36):
        im = Image.fromarray(t2.render(manual_boxes(), views, k * 10.0, scale=2))
        bg = Image.new("RGBA", im.size, (40, 42, 48, 255)); bg.paste(im, (0, 0), im)
        frames.append(bg.convert("P", palette=Image.ADAPTIVE))
    frames[0].save(h.DATA / "exp" / "adesivo" / "mesa_manual.gif", save_all=True, append_images=frames[1:], duration=110, loop=0)


if __name__ == "__main__":
    main()
