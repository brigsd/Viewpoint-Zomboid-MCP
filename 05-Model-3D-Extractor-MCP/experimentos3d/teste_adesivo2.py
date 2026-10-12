"""Teste "adesivo" com várias caixas (ex.: mesa = tampo + 4 pés).

Cada pixel da tela acha a caixa mais próxima da câmera e copia a cor do pixel correspondente na imagem
do jogo de uma vista que enxerga aquele ponto. Se o ponto estiver escondido atrás de outra caixa naquela
vista (ex.: o pé de trás), tenta outra vista; se nenhuma vê, usa a cor média do que se vê da mesma face.

Uso: python teste_adesivo2.py <sprite_frente> [<sprite_tras>|simetrico]
"""
import sqlite3
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from harness import DATA, FH, FW, KH, KX, KY, OX, OY, load_frame, project, rot_y
from teste_adesivo import bleed

D_CAM = np.array([1.0, 2 * KY / KH, 1.0])


def boxes_of(db, name, min_h=300):
    rows = db.execute("select tx,ty,tz,min_x,min_y,min_z,max_x,max_y,max_z from geometry "
                      "where name=? and shape='box' and rx=0 and ry=0 and rz=0", (name,)).fetchall()
    out = []
    for tx, ty, tz, a, b, c, d, e, f in rows:
        if e - b <= min_h and b + ty <= 0:      # placa de sombra no chão
            continue
        out.append((np.array([a + tx, b + ty, c + tz]), np.array([d + tx, e + ty, f + tz])))
    return out


def raycast(boxes, angle, sx, sy):
    """Para pixels (sx, sy) vistos com o objeto girado `angle`: ponto atingido (referencial do objeto),
    normal, índice da caixa e máscara de acerto."""
    a = (sx - OX) / KX
    p0 = np.stack([a / 2, (OY - sy) / KH, -a / 2], -1)
    o = rot_y(p0, -angle)
    d = rot_y(D_CAM, -angle)
    best_t = np.full(sx.shape, -np.inf)
    best_axis = np.zeros(sx.shape, int)
    best_box = np.full(sx.shape, -1)
    with np.errstate(divide="ignore", invalid="ignore"):
        for i, (lo, hi) in enumerate(boxes):
            t1, t2 = (lo - o) / d, (hi - o) / d
            tmin, far = np.minimum(t1, t2).max(-1), np.maximum(t1, t2)
            tmax = far.min(-1)
            hit = (tmax >= tmin) & (tmax > best_t)
            axis = np.argmin(np.abs(far - tmax[..., None]), -1)
            best_t = np.where(hit, tmax, best_t)
            best_axis = np.where(hit, axis, best_axis)
            best_box = np.where(hit, i, best_box)
    hit = best_box >= 0
    t = np.where(hit, best_t, 0.0)
    q = o + t[..., None] * d
    normal = np.zeros(q.shape)
    np.put_along_axis(normal, best_axis[..., None], np.sign(d[best_axis])[..., None], -1)
    return q, normal, best_box, best_axis, hit


def render(boxes, views, angle, scale=1, tol=250):
    H, W = FH * scale, FW * scale
    ys, xs = np.mgrid[0:H, 0:W]
    q, normal, box, axis, hit = raycast(boxes, angle, (xs + 0.5) / scale, (ys + 0.5) / scale)
    out = np.zeros((H, W, 4), np.uint8)
    done = ~hit
    for rgba, ang in views:
        dv = rot_y(D_CAM, -ang)
        cand = ~done & ((normal * dv).sum(-1) > 1e-6)
        if not cand.any():
            continue
        pv = project(rot_y(q[cand], ang))
        # está visível nessa vista? lança o raio da vista naquele pixel e compara o ponto da frente
        qf, _, _, _, hf = raycast(boxes, ang, pv[:, 0], pv[:, 1])
        visible = hf & (np.linalg.norm(qf - q[cand], axis=-1) < tol)
        px, py = np.floor(pv[:, 0]).astype(int), np.floor(pv[:, 1]).astype(int)
        inside = visible & (px >= 0) & (px < FW) & (py >= 0) & (py < FH)
        col = np.zeros((len(px), 4), np.uint8)
        col[inside] = rgba[py[inside], px[inside]]
        good = col[:, 3] >= 128
        idx = np.nonzero(cand)
        sel = (idx[0][good], idx[1][good])
        out[sel] = col[good]
        done[sel] = True
    # o que nenhuma vista enxerga: média do que se vê na mesma face da mesma caixa
    miss = hit & ~done
    if miss.any():
        key = box * 6 + axis * 2 + (normal.sum(-1) > 0)
        for k in np.unique(key[miss]):
            seen = done & hit & (key == k)
            m = miss & (key == k)
            src = out[seen][:, :3] if seen.any() else out[done & hit][:, :3]
            out[m, :3] = src.mean(0).astype(np.uint8) if len(src) else 128
            out[m, 3] = 255
    return out


def main():
    front = sys.argv[1]
    back = sys.argv[2] if len(sys.argv) > 2 else "simetrico"
    out_dir = DATA / "exp" / "adesivo"
    out_dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA / "acervo.sqlite")
    boxes = boxes_of(db, front)
    if back == "simetrico":
        # o jogo só descreve o que se vê na vista isométrica (ex.: o pé de trás não existe);
        # se o objeto é igual dos dois lados, completa com a cópia girada 180 graus
        boxes += [(np.minimum(rot_y(lo, 180), rot_y(hi, 180)), np.maximum(rot_y(lo, 180), rot_y(hi, 180)))
                  for lo, hi in list(boxes)]
    f_rgba = load_frame(db, front)
    b_rgba = f_rgba if back == "simetrico" else load_frame(db, back)
    views = [(bleed(f_rgba), 0.0), (bleed(b_rgba), 180.0)]
    print(f"{front}: {len(boxes)} caixas")

    r0 = render(boxes, views, 0.0)
    m_r, m_p = f_rgba[..., 3] >= 200, r0[..., 3] >= 128
    both = m_r & m_p
    iou = both.sum() / max((m_r | m_p).sum(), 1)
    mae = np.abs(r0[..., :3].astype(int) - f_rgba[..., :3].astype(int))[both].mean()
    print(f"angulo 0: iou {iou:.3f}  diferenca media de cor {mae:.1f}")

    tiles = [("jogo", f_rgba), ("modelo 0", r0)]
    tiles += [(f"modelo {a}", render(boxes, views, float(a))) for a in (45, 90, 135, 180, 225, 270, 315)]
    Z = 2
    sheet = Image.new("RGBA", (5 * FW * Z, 2 * (FH * Z + 20)), (40, 42, 48, 255))
    dr = ImageDraw.Draw(sheet)
    for i, (label, im) in enumerate(tiles):
        x, y = (i % 5) * FW * Z, (i // 5) * (FH * Z + 20)
        big = Image.fromarray(im).resize((FW * Z, FH * Z), Image.NEAREST)
        sheet.paste(big, (x, y + 20), big)
        dr.text((x + 6, y + 4), label, fill=(255, 255, 0) if label == "jogo" else (120, 255, 120))
    sheet.save(out_dir / f"{front}.png")
    frames = []
    for k in range(36):
        im = Image.fromarray(render(boxes, views, k * 10.0, scale=2))
        bg = Image.new("RGBA", im.size, (40, 42, 48, 255))
        bg.paste(im, (0, 0), im)
        frames.append(bg.convert("P", palette=Image.ADAPTIVE))
    frames[0].save(out_dir / f"{front}.gif", save_all=True, append_images=frames[1:], duration=110, loop=0)
    print(out_dir / f"{front}.png")


if __name__ == "__main__":
    main()
