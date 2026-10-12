"""Teste "adesivo": caixa do jogo + imagem original colada nas faces, desenhada pixel a pixel.

Para cada pixel da tela, acha o ponto da caixa que ele enxerga e copia a cor do pixel correspondente
na imagem do jogo da direção que vê aquela face (S para frente/lado direito, N para trás/lado esquerdo).
No ângulo 0 tem que reproduzir a imagem S; se não reproduzir, a ideia está errada.

Uso: python teste_adesivo.py <sprite_base> [saida_dir]
     sprite_base sem o índice, ex. appliances_refrigeration_01 (usa _0=S e _2=N)
"""
import sqlite3
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from harness import DATA, FH, FW, KH, KX, KY, OX, OY, load_frame, project, rot_y

D_CAM = np.array([1.0, 2 * KY / KH, 1.0])        # direção para a câmera (não muda o pixel na tela)


def bleed(rgba, passes=12):
    """Estica a cor das bordas do desenho para os pixels vazios vizinhos (cantos arredondados viram quina)."""
    out = rgba.copy()
    solid = out[..., 3] >= 200
    for _ in range(passes):
        grow = np.zeros_like(solid)
        acc = np.zeros(out.shape[:2] + (3,), np.float32)
        cnt = np.zeros(out.shape[:2], np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            sh = np.roll(np.roll(solid, dy, 0), dx, 1)
            col = np.roll(np.roll(out[..., :3], dy, 0), dx, 1).astype(np.float32)
            add = sh & ~solid
            acc[add] += col[add]
            cnt[add] += 1
            grow |= add
        out[grow, :3] = (acc[grow] / cnt[grow, None]).astype(np.uint8)
        out[grow, 3] = 255
        solid |= grow
    return out


def box_of(db, name):
    rows = db.execute("select tx,ty,tz,min_x,min_y,min_z,max_x,max_y,max_z from geometry "
                      "where name=? and shape='box' and rx=0 and ry=0 and rz=0", (name,)).fetchall()
    tx, ty, tz, a, b, c, d, e, f = rows[0]
    return np.array([a + tx, b + ty, c + tz]), np.array([d + tx, e + ty, f + tz])


def render_box(lo, hi, views, angle, scale=1):
    """views: lista de (rgba, ângulo da vista). Devolve RGBA (FH*scale, FW*scale)."""
    H, W = FH * scale, FW * scale
    ys, xs = np.mgrid[0:H, 0:W]
    sx, sy = (xs + 0.5) / scale, (ys + 0.5) / scale
    a = (sx - OX) / KX
    p0 = np.stack([a / 2, (OY - sy) / KH, -a / 2], -1)          # ponto da tela com profundidade 0
    # leva o raio para o referencial do objeto
    o = rot_y(p0, -angle)
    d = rot_y(D_CAM, -angle)
    with np.errstate(divide="ignore", invalid="ignore"):
        t1 = (lo - o) / d
        t2 = (hi - o) / d
    tmin = np.minimum(t1, t2).max(-1)                          # entrada na caixa
    tmax = np.maximum(t1, t2).min(-1)
    hit = tmax >= tmin
    t = tmax                                                    # ponto mais perto da câmera
    t = np.where(hit, t, 0.0)
    q = o + t[..., None] * d
    # face atingida: o eixo onde tmax foi decidido
    far = np.maximum(t1, t2)
    axis = np.argmin(np.abs(far - t[..., None]), -1)
    sign = np.sign(d[axis])                                     # normal aponta para a câmera
    normal = np.zeros(q.shape)
    np.put_along_axis(normal, axis[..., None], sign[..., None], -1)
    out = np.zeros((H, W, 4), np.uint8)
    for rgba, ang in views:                                     # primeira vista que vê a face, ganha
        dv = rot_y(D_CAM, -ang)
        sees = hit & ((normal * dv).sum(-1) > 1e-6) & (out[..., 3] == 0)
        if not sees.any():
            continue
        pv = project(rot_y(q[sees], ang))
        px, py = np.floor(pv[:, 0]).astype(int), np.floor(pv[:, 1]).astype(int)
        ok = (px >= 0) & (px < FW) & (py >= 0) & (py < FH)
        col = np.zeros((len(px), 4), np.uint8)
        col[ok] = rgba[py[ok], px[ok]]
        col[col[:, 3] < 128] = 0                                # fora do desenho esticado: fica vazio
        idx = np.nonzero(sees)
        out[idx[0], idx[1]] = col
    return out


def main():
    base = sys.argv[1]
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else DATA / "exp" / "adesivo"
    out_dir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA / "acervo.sqlite")
    s_name, n_name = f"{base}_0", f"{base}_2"
    lo, hi = box_of(db, s_name)
    s_rgba, n_rgba = load_frame(db, s_name), load_frame(db, n_name)
    views = [(bleed(s_rgba), 0.0), (bleed(n_rgba), 180.0)]
    print("caixa S:", lo, hi)

    # 1) no ângulo 0 tem que bater com a imagem S
    r0 = render_box(lo, hi, views, 0.0)
    m_r, m_p = s_rgba[..., 3] >= 200, r0[..., 3] >= 128
    iou = (m_r & m_p).sum() / max((m_r | m_p).sum(), 1)
    both = m_r & m_p
    mae = np.abs(r0[..., :3].astype(int) - s_rgba[..., :3].astype(int))[both].mean()
    print(f"angulo 0: iou {iou:.3f}  diferenca media de cor {mae:.1f} (0 = identico)")

    # 2) folha: original S | modelo 0 | original N | modelo 180 | modelo 45 | 90 | 135
    tiles = [("jogo S", s_rgba), ("modelo 0", r0), ("jogo N", n_rgba), ("modelo 180", render_box(lo, hi, views, 180.0))]
    tiles += [(f"modelo {a}", render_box(lo, hi, views, float(a))) for a in (45, 90, 135, 225, 270, 315)]
    Z = 2
    sheet = Image.new("RGBA", (5 * FW * Z, 2 * (FH * Z + 20)), (40, 42, 48, 255))
    dr = ImageDraw.Draw(sheet)
    for i, (label, im) in enumerate(tiles):
        x, y = (i % 5) * FW * Z, (i // 5) * (FH * Z + 20)
        big = Image.fromarray(im).resize((FW * Z, FH * Z), Image.NEAREST)
        sheet.paste(big, (x, y + 20), big)
        dr.text((x + 6, y + 4), label, fill=(255, 255, 0) if "jogo" in label else (120, 255, 120))
    sheet.save(out_dir / f"{base}.png")
    frames = []
    for k in range(36):
        im = Image.fromarray(render_box(lo, hi, views, k * 10.0, scale=2))
        bg = Image.new("RGBA", im.size, (40, 42, 48, 255))
        bg.paste(im, (0, 0), im)
        frames.append(bg.convert("P", palette=Image.ADAPTIVE))
    frames[0].save(out_dir / f"{base}.gif", save_all=True, append_images=frames[1:], duration=110, loop=0)
    print(out_dir / f"{base}.png")


if __name__ == "__main__":
    main()
