#!/usr/bin/env python3
"""Prova de alinhamento: a geometria do tileGeometry.txt desenhada na projecao isometrica do jogo por cima do sprite.

Projecao (medida; ver `python align_check.py --fit`), em px do quadro 128x256 de 2x, origem no centro do tile
(64, 224) (o diamante do chao ocupa os 64 px de baixo do quadro):

    sx = 64  + K   * (X - Z)
    sy = 224 + K/2 * (X + Z) - H * Y         K = 128/2/10000 = 0,0064 px/unidade,  H = cos(30 graus) * lado_px/10000
                                              lado_px = 128/raiz(2) = 90,5 px  ->  H = 0,007838 px/unidade

X aponta para a direita-baixo da tela (leste), Z para a esquerda-baixo (sul) e Y para cima: a camera esta em
+X +Y +Z olhando para -X -Y -Z, a 30 graus de elevacao (diamante 2:1). Unidades: 1/10000 de tile.

Formas: box (min/max + rotate/translate), cylinder (eixo local Z, centrado em translate, altura = height),
polygon (pontos 2D em plane = XY|XZ|YZ, sem espessura). Rotacao em 1/10000 de grau, R = Rx·Ry·Rz (Z primeiro)
(sinal e ordem so tem efeito nos tiles com rotacao composta; medido: sinal + e melhor que -).

Saidas em data/align/:
    <nome>.png             sprite colorido no quadro cheio (x4) + caixas da geometria + silhueta de profundidade
    <nome>_lado_a_lado.png cor | profundidade | profundidade + geometria
    resultado.json         IoU por objeto e por mapeamento de eixos, varredura de escala e amostra por categoria

Uso:
  python align_check.py                       # os 5 objetos do gate (cama, mesa, geladeira, prateleira, caixa)
  python align_check.py --names a_1 b_2       # outros sprites
  python align_check.py --sample 60           # + amostra de 60 tiles com geometria por categoria
  python align_check.py --fit                 # + varredura da escala de altura e da origem
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import random
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import extract_depth as ed  # noqa: E402

FRAME_W, FRAME_H = ed.FRAME_W, ed.FRAME_H
K = ed.K_PX                      # px por unidade em X e Z
H = ed.H_PX                      # px por unidade em Y
ORIGIN = (64.0, 224.0)           # centro do tile no quadro 2x
GATE = ["furniture_bedding_01_0", "furniture_tables_high_01_0", "appliances_refrigeration_01_0",
        "furniture_shelving_01_0", "carpentry_01_16"]
GATE_LABEL = {"furniture_bedding_01_0": "cama", "furniture_tables_high_01_0": "mesa",
              "appliances_refrigeration_01_0": "geladeira", "furniture_shelving_01_0": "prateleira",
              "carpentry_01_16": "caixa"}
SHAPE_COLORS = [(255, 64, 64), (64, 255, 64), (64, 160, 255), (255, 220, 0), (255, 0, 255), (0, 255, 255),
                (255, 140, 0), (160, 100, 255)]
SHAPE_COLS = "shape,tx,ty,tz,rx,ry,rz,min_x,min_y,min_z,max_x,max_y,max_z,raw"


# --------------------------------------------------------------------------- mapeamentos de eixos

def _dirs():
    return [(1, 1), (-1, -1), (1, -1), (-1, 1)]


def candidate_mappings():
    """8 mapeamentos isometricos 2:1: X vai para uma das 4 diagonais da tela, Z para uma diagonal nao paralela."""
    out = []
    for ex, ez in itertools.product(_dirs(), _dirs()):
        if ex == ez or ex == (-ez[0], -ez[1]):
            continue
        out.append((ex, ez))
    return out


CHOSEN = ((1, 1), (-1, 1))       # X -> direita-baixo, Z -> esquerda-baixo (medido)


def mapping_label(m) -> str:
    def d(v):
        return ("direita" if v[0] > 0 else "esquerda") + "-" + ("baixo" if v[1] > 0 else "cima")
    return f"X->{d(m[0])}, Z->{d(m[1])}"


def project(P, mapping=CHOSEN, h=H, origin=ORIGIN):
    """Pontos Nx3 (X,Y,Z em unidades do tileGeometry) -> Nx2 (sx, sy) no quadro 2x."""
    P = np.asarray(P, float)
    ex, ez = mapping
    sx = origin[0] + K * (ex[0] * P[:, 0] + ez[0] * P[:, 2])
    sy = origin[1] + K / 2 * (ex[1] * P[:, 0] + ez[1] * P[:, 2]) - h * P[:, 1]
    return np.c_[sx, sy]


# --------------------------------------------------------------------------- formas 3D

def rot_matrix(rx, ry, rz):
    d = math.pi / 180 / 10000
    rx, ry, rz = rx * d, ry * d, rz * d
    Rx = np.array([[1, 0, 0], [0, math.cos(rx), -math.sin(rx)], [0, math.sin(rx), math.cos(rx)]])
    Ry = np.array([[math.cos(ry), 0, math.sin(ry)], [0, 1, 0], [-math.sin(ry), 0, math.cos(ry)]])
    Rz = np.array([[math.cos(rz), -math.sin(rz), 0], [math.sin(rz), math.cos(rz), 0], [0, 0, 1]])
    return Rx @ Ry @ Rz


def _num(raw, key):
    m = re.search(key + r"\s*=\s*(-?[\d.]+)", raw or "")
    return float(m.group(1)) if m else 0.0


def load_shapes(conn, name):
    """Linhas de `geometry` do sprite, na ordem do tile."""
    return conn.execute(f"SELECT {SHAPE_COLS} FROM geometry WHERE name=? ORDER BY shape_idx", (name,)).fetchall()


def shape_geometry(row):
    """Devolve (pontos 3D que definem a forma, lista de polilinhas 3D para o arame, preenchimento_poligonal ou None).

    As polilinhas sao Nx3. `fill` e True para poligonos sem espessura (preenchidos na projecao em vez do casco)."""
    shape, tx, ty, tz, rx, ry, rz, x0, y0, z0, x1, y1, z1, raw = row
    R = rot_matrix(rx or 0, ry or 0, rz or 0)
    T = np.array([tx or 0, ty or 0, tz or 0], float)
    if shape == "box" and x0 is not None:
        c = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], float)
        c = c @ R.T + T
        lines = []
        for i, j in itertools.combinations(range(8), 2):
            if bin(i ^ j).count("1") == 1:
                lines.append(np.array([c[i], c[j]]))
        return c, lines, False
    if shape == "cylinder":
        r1, r2, hh = _num(raw, "radius1"), _num(raw, "radius2"), _num(raw, "height")
        th = np.linspace(0, 2 * math.pi, 28, endpoint=False)
        a = np.c_[r1 * np.cos(th), r1 * np.sin(th), np.full(len(th), -hh / 2)] @ R.T + T
        b = np.c_[r2 * np.cos(th), r2 * np.sin(th), np.full(len(th), hh / 2)] @ R.T + T
        lines = [np.vstack([a, a[:1]]), np.vstack([b, b[:1]])]
        for k in range(0, len(th), 7):
            lines.append(np.array([a[k], b[k]]))
        return np.vstack([a, b]), lines, False
    if shape == "polygon":
        plane = (re.search(r"plane\s*=\s*(\w+)", raw or "") or [None, "XY"])[1]
        pts = [tuple(map(float, t.split("x"))) for t in re.sub(r"[,\s]+", " ", (re.search(r"points\s*=\s*([^\n]+)", raw or "") or [None, ""])[1]).split() if "x" in t]
        if len(pts) < 3:
            return None
        p = np.array(pts)
        z = np.zeros(len(p))
        P = {"XY": np.c_[p[:, 0], p[:, 1], z], "XZ": np.c_[p[:, 0], z, p[:, 1]], "YZ": np.c_[z, p[:, 0], p[:, 1]]}.get(plane)
        if P is None:
            return None
        P = P @ R.T + T
        return P, [np.vstack([P, P[:1]])], True
    return None


def silhouette(rows, mapping=CHOSEN, h=H, origin=ORIGIN, shape=(FRAME_H, FRAME_W)):
    """Mascara booleana da projecao da geometria (casco convexo por forma; poligonos preenchidos)."""
    img = Image.new("L", (shape[1], shape[0]), 0)
    dr = ImageDraw.Draw(img)
    for r in rows:
        g = shape_geometry(r)
        if g is None:
            continue
        P, _, fill = g
        pr = project(P, mapping, h, origin)
        poly = [tuple(p) for p in pr] if fill else convex_hull(pr)
        if len(poly) >= 3:
            dr.polygon(poly, fill=255)
    return np.asarray(img) > 0


def convex_hull(pts):
    pts = sorted(set(map(tuple, np.round(np.asarray(pts, float), 3))))
    if len(pts) < 3:
        return pts

    def cr(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lo = []
    for p in pts:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    up = []
    for p in reversed(pts):
        while len(up) >= 2 and cr(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def iou(a, b) -> float:
    return float((a & b).sum()) / max(1, int((a | b).sum()))


# --------------------------------------------------------------------------- mascaras dos dados do acervo

def colour_row(conn, name):
    return conn.execute("SELECT png,width,height,offset_x,offset_y,scale,frame_w,frame_h FROM sprites WHERE name=?",
                        (name,)).fetchone()


def colour_image(conn, data_dir, name):
    """Sprite colorido no quadro cheio 128x256 (RGBA), normalizado para 2x; None se faltar ou o quadro for estranho."""
    r = colour_row(conn, name)
    if not r:
        return None
    png, w, h, ox, oy, scale, fw, fh = r
    scale = scale or 2
    f = 2 // scale if scale in (1, 2) else 1
    if (fw * f, fh * f) != (FRAME_W, FRAME_H):
        return None
    full = Image.new("RGBA", (fw, fh), (0, 0, 0, 0))
    with Image.open(Path(data_dir) / png) as im:
        full.paste(im.convert("RGBA"), (ox, oy))
    if f == 2:
        full = full.resize((FRAME_W, FRAME_H), Image.NEAREST)
    return full


def depth_for(conn, name):
    """(png_relativo, nome_usado): mapa proprio ou, se nao houver, o atribuido em depth_assignments."""
    r = conn.execute("SELECT png FROM depth_maps WHERE name=?", (name,)).fetchone()
    if r:
        return r[0], name
    a = conn.execute("SELECT depth FROM depth_assignments WHERE name=?", (name,)).fetchone()
    if a:
        r = conn.execute("SELECT png FROM depth_maps WHERE name=?", (a[0],)).fetchone()
        if r:
            return r[0], a[0]
    return None, None


def depth_image(data_dir, rel):
    return Image.open(Path(data_dir) / rel).convert("LA")


# --------------------------------------------------------------------------- metricas

def best_shift(mask_a, mask_b, rng=6):
    """Deslocamento inteiro (dx, dy) de mask_a que maximiza o IoU com mask_b."""
    best = (iou(mask_a, mask_b), (0, 0))
    for dy in range(-rng, rng + 1):
        for dx in range(-rng, rng + 1):
            if dx == 0 and dy == 0:
                continue
            v = iou(np.roll(np.roll(mask_a, dy, 0), dx, 1), mask_b)
            if v > best[0] + 1e-9:
                best = (v, (dx, dy))
    return best


def measure(conn, data_dir, name, with_mappings=True):
    rows = load_shapes(conn, name)
    col = colour_image(conn, data_dir, name)
    cm = (np.asarray(col)[..., 3] > 0) if col is not None else None
    drel, dused = depth_for(conn, name)
    dm = (np.asarray(depth_image(data_dir, drel))[..., 1] > 0) if drel else None
    out = {"name": name, "shapes": len(rows),
           "shape_types": sorted({r[0] for r in rows}),
           "colour_px": int(cm.sum()) if cm is not None else None,
           "depth_px": int(dm.sum()) if dm is not None else None,
           "depth_from": dused}
    sil = silhouette(rows)
    out["sil_px"] = int(sil.sum())
    if cm is not None:
        out["iou_colour"] = round(iou(sil, cm), 4)
        out["colour_inside_geometry"] = round(float((sil & cm).sum()) / max(1, int(cm.sum())), 4)
        v, sh = best_shift(sil, cm)
        out["iou_colour_best_shift"] = round(v, 4)
        out["best_shift_px"] = sh
    if dm is not None:
        out["iou_depth"] = round(iou(sil, dm), 4)
    if cm is not None and dm is not None:
        out["iou_colour_vs_depth"] = round(iou(cm, dm), 4)
    if with_mappings:
        res = []
        for m in candidate_mappings():
            s = silhouette(rows, m)
            res.append({"mapping": mapping_label(m), "chosen": m == CHOSEN,
                        "iou_colour": round(iou(s, cm), 4) if cm is not None else None,
                        "iou_depth": round(iou(s, dm), 4) if dm is not None else None})
        res.sort(key=lambda r: -(r["iou_colour"] or 0))
        out["mappings"] = res
    return out


def fit_scale(conn, data_dir, names, scales=(0.80, 0.90, 0.95, 1.0, 1.05, 1.10, 1.20), dys=(-4, -2, 0, 2, 4)):
    """Media do IoU (geometria x mascara de profundidade e x cor) variando a escala de altura e a origem y."""
    pack = []
    for n in names:
        rows = load_shapes(conn, n)
        col = colour_image(conn, data_dir, n)
        drel, _ = depth_for(conn, n)
        if not rows or col is None or not drel:
            continue
        pack.append((rows, np.asarray(col)[..., 3] > 0, np.asarray(depth_image(data_dir, drel))[..., 1] > 0))
    res = {"scale": [], "origin_y": []}
    for s in scales:
        c = np.mean([iou(silhouette(r, h=H * s), cm) for r, cm, _ in pack])
        d = np.mean([iou(silhouette(r, h=H * s), dm) for r, _, dm in pack])
        res["scale"].append({"h_scale": s, "iou_colour": round(float(c), 4), "iou_depth": round(float(d), 4)})
    for dy in dys:
        o = (ORIGIN[0], ORIGIN[1] + dy)
        c = np.mean([iou(silhouette(r, origin=o), cm) for r, cm, _ in pack])
        d = np.mean([iou(silhouette(r, origin=o), dm) for r, _, dm in pack])
        res["origin_y"].append({"dy": dy, "iou_colour": round(float(c), 4), "iou_depth": round(float(d), 4)})
    res["objects"] = len(pack)
    return res


def sample_by_category(conn, data_dir, per_cat=60, seed=11):
    """Amostra de tiles com geometria (e sprite 2x) por categoria; IoU com a cor e com a profundidade."""
    rng = random.Random(seed)
    cats = [r[0] for r in conn.execute(
        "SELECT DISTINCT t.category FROM tiles t JOIN geometry g ON g.name=t.name WHERE t.category IS NOT NULL ORDER BY 1")]
    out = {}
    per_map: dict[str, list] = {}
    for cat in cats:
        names = [r[0] for r in conn.execute(
            """SELECT DISTINCT t.name FROM tiles t JOIN geometry g ON g.name=t.name
               JOIN sprites s ON s.name=t.name WHERE t.category=?""", (cat,))]
        rng.shuffle(names)
        ic, idp, wins, n = [], [], 0, 0
        for nm in names[:per_cat]:
            m = measure(conn, data_dir, nm, with_mappings=True)
            if m.get("iou_colour") is None:
                continue
            n += 1
            for mp in m["mappings"]:
                per_map.setdefault(mp["mapping"], []).append((mp["iou_colour"], mp["iou_depth"]))
            ic.append(m["iou_colour"])
            if m.get("iou_depth") is not None:
                idp.append(m["iou_depth"])
            if m["mappings"][0]["chosen"] or m["mappings"][0]["iou_colour"] <= m["iou_colour"] + 1e-9:
                wins += 1
        if n:
            out[cat] = {"n": n, "iou_colour_mediana": round(float(np.median(ic)), 3),
                        "iou_colour_media": round(float(np.mean(ic)), 3),
                        "iou_colour_ge_0.6": round(float(np.mean(np.array(ic) >= 0.6)), 3),
                        "iou_depth_mediana": round(float(np.median(idp)), 3) if idp else None,
                        "mapeamento_escolhido_e_o_melhor": round(wins / n, 3)}
    out["_mapeamentos_media"] = {
        k: {"iou_colour": round(float(np.mean([a for a, _ in v])), 4),
            "iou_depth": round(float(np.mean([b for _, b in v if b is not None])), 4), "n": len(v)}
        for k, v in sorted(per_map.items(), key=lambda kv: -np.mean([a for a, _ in kv[1]]))}
    return out


# --------------------------------------------------------------------------- desenho

def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _checker(w, h, cell=16):
    a = np.zeros((h, w, 3), np.uint8)
    yy, xx = np.mgrid[0:h, 0:w]
    a[:] = np.where(((yy // cell + xx // cell) % 2 == 0)[..., None], 52, 44)
    return Image.fromarray(a, "RGB")


def draw_wire(dr, rows, scale, mapping=CHOSEN, width=2, colors=SHAPE_COLORS):
    for i, r in enumerate(rows):
        g = shape_geometry(r)
        if g is None:
            continue
        col = colors[i % len(colors)]
        for line in g[1]:
            pr = project(line, mapping) * scale
            dr.line([tuple(p) for p in pr], fill=col + (255,), width=width)


def draw_frame_guides(dr, scale):
    """Diamante do chao do tile (64 px de altura no fundo do quadro) e eixos X, Z, Y a partir do centro."""
    o = np.array(ORIGIN)
    d = np.array([[0, -32], [64, 0], [0, 32], [-64, 0], [0, -32]]) + o
    dr.line([tuple(p * scale) for p in d], fill=(200, 200, 200, 255), width=1)
    f = _font(max(12, scale * 3))
    for lab, v, col in (("X", (40, 20), (255, 120, 120)), ("Z", (-40, 20), (120, 255, 120)), ("Y", (0, -60), (120, 160, 255))):
        end = o + np.array(v)
        dr.line([tuple(o * scale), tuple(end * scale)], fill=col + (255,), width=2)
        dr.text(tuple(end * scale + (4, -4)), lab, fill=col + (255,), font=f)


def render_overlay(conn, data_dir, name, out_path, scale=4):
    rows = load_shapes(conn, name)
    col = colour_image(conn, data_dir, name)
    W, Hh = FRAME_W * scale, FRAME_H * scale
    base = _checker(W, Hh, 16 * scale // 2).convert("RGBA")
    if col is not None:
        base.alpha_composite(col.resize((W, Hh), Image.NEAREST))
    drel, _ = depth_for(conn, name)
    layer = Image.new("RGBA", (W, Hh), (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    if drel:
        dm = np.asarray(depth_image(data_dir, drel))[..., 1] > 0
        edge = dm & ~(np.roll(dm, 1, 0) & np.roll(dm, -1, 0) & np.roll(dm, 1, 1) & np.roll(dm, -1, 1))
        ys, xs = np.where(edge)
        for y, x in zip(ys, xs):
            dr.rectangle([x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1], fill=(0, 255, 255, 110))
    draw_frame_guides(dr, scale)
    draw_wire(dr, rows, scale)
    base.alpha_composite(layer)
    m = measure(conn, data_dir, name, with_mappings=False)
    dr2 = ImageDraw.Draw(base)
    f = _font(14)
    lines = [name, f"formas: {m['shapes']} ({', '.join(m['shape_types'])})"]
    if "iou_colour" in m:
        lines.append(f"IoU geometria x cor: {m['iou_colour']:.3f}")
    if "iou_depth" in m:
        lines.append(f"IoU geometria x profundidade: {m['iou_depth']:.3f}")
    lines.append("ciano = silhueta da profundidade")
    dr2.rectangle([0, 0, W, 18 * len(lines) + 6], fill=(0, 0, 0, 170))
    for i, t in enumerate(lines):
        dr2.text((6, 4 + 18 * i), t, fill=(255, 255, 255, 255), font=f)
    base.convert("RGB").save(out_path)
    return m


def render_side_by_side(conn, data_dir, name, out_path, scale=3):
    rows = load_shapes(conn, name)
    col = colour_image(conn, data_dir, name)
    drel, dused = depth_for(conn, name)
    W, Hh = FRAME_W * scale, FRAME_H * scale
    panels = []
    p1 = _checker(W, Hh, 8 * scale).convert("RGBA")
    if col is not None:
        p1.alpha_composite(col.resize((W, Hh), Image.NEAREST))
    panels.append(("cor (quadro cheio)", p1))
    p2 = _checker(W, Hh, 8 * scale).convert("RGBA")
    if drel:
        la = depth_image(data_dir, drel)
        g = np.asarray(la)[..., 0]
        rgba = np.dstack([g, g, g, np.asarray(la)[..., 1]])
        p2.alpha_composite(Image.fromarray(rgba, "RGBA").resize((W, Hh), Image.NEAREST))
    panels.append((f"profundidade ({dused or 'nenhuma'})", p2))
    p3 = p2.copy()
    d3 = ImageDraw.Draw(p3)
    draw_wire(d3, rows, scale, width=1)
    panels.append(("profundidade + geometria", p3))
    f = _font(14)
    sheet = Image.new("RGB", (W * 3 + 20, Hh + 26), (24, 24, 24))
    dr = ImageDraw.Draw(sheet)
    for i, (t, im) in enumerate(panels):
        sheet.paste(im.convert("RGB"), (i * (W + 10), 26))
        dr.text((i * (W + 10) + 4, 4), t, fill=(255, 255, 255), font=f)
    sheet.save(out_path)


def contact_sheet(paths, out_path, labels):
    ims = [Image.open(p).convert("RGB") for p in paths]
    h = max(i.height for i in ims)
    w = sum(i.width for i in ims) + 10 * (len(ims) - 1)
    sheet = Image.new("RGB", (w, h), (24, 24, 24))
    x = 0
    for im in ims:
        sheet.paste(im, (x, 0))
        x += im.width + 10
    sheet.save(out_path)


# --------------------------------------------------------------------------- CLI

def run(conn, data_dir, names, out_dir, sample=0, fit=False, quiet=False):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {"projecao": {"K_px_por_unidade": K, "H_px_por_unidade": H, "origem": ORIGIN,
                           "mapeamento": mapping_label(CHOSEN)}, "objetos": []}
    side_paths = []
    for n in names:
        if not load_shapes(conn, n):
            print(f"AVISO: {n} nao tem geometria; ignorado", file=sys.stderr)
            continue
        m = render_overlay(conn, data_dir, n, out_dir / f"{n}.png")
        render_side_by_side(conn, data_dir, n, out_dir / f"{n}_lado_a_lado.png")
        side_paths.append(out_dir / f"{n}.png")
        full = measure(conn, data_dir, n)
        result["objetos"].append(full)
        if not quiet:
            best = full["mappings"][0]
            print(f"{n:34s} IoU cor {full.get('iou_colour')}  prof {full.get('iou_depth')}  "
                  f"desloc.otimo {full.get('best_shift_px')}  melhor mapeamento: {best['mapping']}"
                  f"{' (escolhido)' if best['chosen'] or best['iou_colour'] - (full.get('iou_colour') or 0) < 1e-3 else ' (DIFERENTE do escolhido)'}")
    if side_paths:
        contact_sheet(side_paths, out_dir / "painel.png", None)
    if fit:
        result["ajuste"] = fit_scale(conn, data_dir, names if len(names) >= 3 else GATE)
        if not quiet:
            print("ajuste:", json.dumps(result["ajuste"], ensure_ascii=False))
    if sample:
        result["amostra_por_categoria"] = sample_by_category(conn, data_dir, per_cat=sample)
        if not quiet:
            for cat, v in result["amostra_por_categoria"].items():
                if cat != "_mapeamentos_media":
                    print(f"  {cat:18s} {v}")
            print("  media do IoU por mapeamento (todas as categorias):")
            for k, v in result["amostra_por_categoria"]["_mapeamentos_media"].items():
                print(f"    {k:40s} cor {v['iou_colour']:.3f}  prof {v['iou_depth']:.3f}  n={v['n']}")
    (out_dir / "resultado.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-dir", default=str(HERE / "data"))
    ap.add_argument("--names", nargs="*", default=GATE)
    ap.add_argument("--sample", type=int, default=0, help="tiles por categoria na amostra estatistica")
    ap.add_argument("--fit", action="store_true", help="varre escala de altura e origem y")
    a = ap.parse_args(argv)
    data_dir = Path(a.data_dir)
    conn = sqlite3.connect(data_dir / "acervo.sqlite")
    run(conn, data_dir, a.names, data_dir / "align", sample=a.sample, fit=a.fit)
    conn.close()
    print(f"\nImagens em {data_dir / 'align'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
