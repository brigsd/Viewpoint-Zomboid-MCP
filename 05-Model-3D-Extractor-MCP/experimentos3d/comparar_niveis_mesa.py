"""Folha com os três níveis da mesa lado a lado (jogo, ARTE, REALISTA, ESCULPIDO/nível 3) e o giro do nível 3.
Rodar depois de blender_mesa_nivel3.py. Uso: python comparar_niveis_mesa.py"""
import sqlite3

from PIL import Image, ImageDraw

import harness as h
import teste_manual_mesa2 as m2
import teste_realista_mesa as r
from teste_manual_mesa import NAME, manual_boxes

N3 = h.DATA / "exp" / "nivel3"
BG = (40, 42, 48, 255)


def main():
    db = sqlite3.connect(h.DATA / "acervo.sqlite")
    spr = h.load_frame(db, NAME)
    boxes = manual_boxes()
    arte = m2.kit(spr, boxes)
    real = r.realistic_kit(arte)
    S, angles = 4, (0, 60, 180)
    crop = tuple(c * S for c in (0, 110, 128, 256))
    cw, ch = crop[2] - crop[0], crop[3] - crop[1]
    rows = [("1 ARTE", lambda a: Image.fromarray(m2.render(boxes, arte, float(a), scale=S))),
            ("2 REALISTA", lambda a: Image.fromarray(m2.render(boxes, real, float(a), scale=S))),
            ("3 ESCULPIDO", lambda a: Image.open(N3 / f"vista_{a:03d}.png").convert("RGBA"))]
    sheet = Image.new("RGBA", ((len(angles) + 1) * cw, len(rows) * (ch + 26)), BG)
    dr = ImageDraw.Draw(sheet)
    orig = Image.fromarray(spr).resize((128 * S, 256 * S), Image.NEAREST).crop(crop)
    for i, (label, fn) in enumerate(rows):
        y = i * (ch + 26)
        sheet.paste(orig, (0, y + 26), orig)
        dr.text((6, y + 6), "jogo (original)", fill=(255, 255, 0))
        for j, a in enumerate(angles):
            im = fn(a).crop(crop)
            sheet.paste(im, ((j + 1) * cw, y + 26), im)
            dr.text(((j + 1) * cw + 6, y + 6), f"nivel {label}  {a} graus", fill=(120, 255, 120))
    sheet.save(N3 / "mesa_tres_niveis.png")

    wires = Image.new("RGBA", (3 * cw, ch + 26), BG)
    dr = ImageDraw.Draw(wires)
    for j, (label, path) in enumerate((("0 graus", N3 / "vista_000.png"), ("wireframe 0", N3 / "wire_000.png"), ("wireframe 60", N3 / "wire_060.png"))):
        im = Image.open(path).convert("RGBA").crop(crop)
        wires.paste(im, (j * cw, 26), im)
        dr.text((j * cw + 6, 6), label, fill=(120, 255, 120))
    wires.save(N3 / "mesa_n3_wireframe.png")

    frames = []
    c3 = tuple(c * 3 for c in (0, 110, 128, 256))
    for k in range(36):
        im = Image.open(N3 / "giro" / f"{k:02d}.png").convert("RGBA").crop(c3)
        bg = Image.new("RGBA", im.size, BG); bg.paste(im, (0, 0), im)
        frames.append(bg.convert("P", palette=Image.ADAPTIVE))
    frames[0].save(N3 / "mesa_n3.gif", save_all=True, append_images=frames[1:], duration=110, loop=0)


if __name__ == "__main__":
    main()
