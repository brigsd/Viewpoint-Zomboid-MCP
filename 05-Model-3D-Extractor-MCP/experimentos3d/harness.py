"""Bancada de testes das abordagens de modelo 3D a partir do acervo.

Protocolo: para cada objeto de teste (1 tile, 4 direções S/E/N/W), a abordagem monta o modelo usando
3 direções e a bancada desenha o modelo na 4ª, que a abordagem não viu, comparando com a imagem real
do jogo. Repete deixando cada direção de fora (4 rodadas). A nota mede o quanto o 3D está certo.

Uso:
  python harness.py testset                      # escolhe os objetos de teste (testset.json)
  python harness.py run <abordagem> [--limit N]  # roda approach_<abordagem>.py e grava resultados
  python harness.py compare                      # tabela comparando as abordagens já rodadas

Interface de uma abordagem (arquivo approach_<nome>.py):
  def build(obj: Obj, train: list[str]) -> Mesh
    obj.views[f] para f em train: View com rgba (256,128,4) uint8 do quadro completo, depth (256,128)
    float ou None (cinza do mapa de profundidade; NaN onde vazio), boxes [(min3, max3), ...] da geometria
    dessa direção (no referencial da própria vista) e angle (rotação dessa vista em relação a S).
    Devolve a malha no referencial de S (a vista S tem angle 0).
"""
import json
import math
import random
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ACERVO = HERE.parent / "acervo"
DATA = ACERVO / "data"
OUT = DATA / "exp"
FACINGS = ("S", "E", "N", "W")

# Projeção do acervo (quadro 2x 128x256; unidades 1/10000 de tile; X direita-baixo, Z esquerda-baixo, Y cima)
KX, KY, KH = 0.0064, 0.0032, 0.007838
OX, OY = 64.0, 224.0
FW, FH = 128, 256
# Rotação de cada direção em relação a S, em graus (sentido conferido em calibrate())
ANGLE = {"S": 0.0, "E": -90.0, "N": 180.0, "W": 90.0}


def project(p: np.ndarray) -> np.ndarray:
    """(N,3) -> (N,3): x tela, y tela, profundidade (maior = mais perto da câmera)."""
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    return np.stack([OX + KX * (x - z), OY + KY * (x + z) - KH * y, KX * (x + z) + 0.005225 * y], axis=1)


def unproject(sx: np.ndarray, sy: np.ndarray, gray: np.ndarray) -> np.ndarray:
    """Pixel + cinza do mapa de profundidade -> ponto 3D (referencial da vista)."""
    a = (sx - OX) / KX                       # X - Z
    d = 190.0 - gray                         # = KX*(X+Z) + 0.005225*Y
    # sy - OY = KY*(X+Z) - KH*Y ; resolve (X+Z) e Y
    s_ = (sy - OY)
    det = KY * 0.005225 + KH * KX
    xz = (s_ * 0.005225 + KH * d) / det
    y = (KY * d - KX * s_) / det
    x = (a + xz) / 2
    z = (xz - a) / 2
    return np.stack([x, y, z], axis=-1)


def rot_y(points: np.ndarray, deg: float) -> np.ndarray:
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    x, y, z = points[..., 0], points[..., 1], points[..., 2]
    return np.stack([x * c - z * s, y, x * s + z * c], axis=-1)


@dataclass
class View:
    name: str
    rgba: np.ndarray
    depth: np.ndarray | None
    boxes: list
    angle: float


@dataclass
class Obj:
    key: str
    category: str
    views: dict = field(default_factory=dict)


@dataclass
class Mesh:
    vertices: np.ndarray                     # (N,3) float, referencial de S
    faces: np.ndarray                        # (M,3) int
    colors: np.ndarray                       # (M,3) uint8, cor por triângulo


def load_frame(db, name):
    row = db.execute("select png, offset_x, offset_y, scale from sprites where name=?", (name,)).fetchone()
    if not row or row[3] != 2:
        return None
    png, ox, oy, _ = row
    frame = Image.new("RGBA", (FW, FH))
    im = Image.open(DATA / png).convert("RGBA")
    frame.paste(im, (ox, oy))
    return np.asarray(frame).copy()


def load_depth(db, name):
    row = db.execute("select png from depth_maps where name=?", (name,)).fetchone()
    if not row:
        return None
    im = np.asarray(Image.open(DATA / row[0]).convert("LA")).astype(np.float32)
    g = im[..., 0].copy()
    g[im[..., 1] < 128] = np.nan
    return g


def load_obj(db, entry) -> Obj:
    obj = Obj(entry["key"], entry["category"])
    for f, name in entry["names"].items():
        boxes = [((a, b, c), (d, e, g)) for a, b, c, d, e, g in db.execute(
            "select min_x,min_y,min_z,max_x,max_y,max_z from geometry where name=? and shape='box' and rx=0 and ry=0 and rz=0",
            (name,))]
        obj.views[f] = View(name, load_frame(db, name), load_depth(db, name), boxes, ANGLE[f])
    return obj


# ---------------------------------------------------------------- renderizador

def render(mesh: Mesh, angle: float, ss: int = 2) -> np.ndarray:
    """Desenha a malha girada por `angle` na projeção do jogo. Devolve RGBA (256,128)."""
    W, H = FW * ss, FH * ss
    color = np.zeros((H, W, 4), np.uint8)
    zbuf = np.full((H, W), -np.inf, np.float32)
    if len(mesh.faces) == 0:
        return color[::ss, ::ss]
    pv = project(rot_y(mesh.vertices.astype(np.float64), angle))
    pv[:, :2] *= ss
    tri = pv[mesh.faces]                     # (M,3,3)
    # descarta degenerados e fora da tela
    for t in range(len(tri)):
        (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = tri[t]
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-9:
            continue
        minx, maxx = int(max(0, math.floor(min(x0, x1, x2)))), int(min(W - 1, math.ceil(max(x0, x1, x2))))
        miny, maxy = int(max(0, math.floor(min(y0, y1, y2)))), int(min(H - 1, math.ceil(max(y0, y1, y2))))
        if minx > maxx or miny > maxy:
            continue
        xs, ys = np.meshgrid(np.arange(minx, maxx + 1) + 0.5, np.arange(miny, maxy + 1) + 0.5)
        w0 = ((x1 - xs) * (y2 - ys) - (x2 - xs) * (y1 - ys)) / area
        w1 = ((x2 - xs) * (y0 - ys) - (x0 - xs) * (y2 - ys)) / area
        w2 = 1 - w0 - w1
        inside = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not inside.any():
            continue
        z = w0 * z0 + w1 * z1 + w2 * z2
        sub = zbuf[miny:maxy + 1, minx:maxx + 1]
        win = inside & (z > sub)
        if win.any():
            sub[win] = z[win]
            color[miny:maxy + 1, minx:maxx + 1][win] = (*mesh.colors[t], 255)
    if ss > 1:
        c = color.reshape(FH, ss, FW, ss, 4).astype(np.float32)
        a = c[..., 3:4] / 255.0
        rgb = (c[..., :3] * a).sum(axis=(1, 3)) / np.maximum(a.sum(axis=(1, 3)), 1e-6)
        alpha = c[..., 3].mean(axis=(1, 3))
        return np.dstack([rgb, alpha]).clip(0, 255).astype(np.uint8)
    return color


# ---------------------------------------------------------------- nota

def score(pred: np.ndarray, real: np.ndarray) -> dict:
    pm, rm = pred[..., 3] >= 128, real[..., 3] >= 200
    inter, union = (pm & rm).sum(), (pm | rm).sum()
    iou = float(inter / union) if union else 0.0
    if inter:
        diff = np.abs(pred[..., :3].astype(np.int16) - real[..., :3].astype(np.int16))[pm & rm]
        mae = float(diff.mean())
    else:
        mae = 255.0
    return {"iou": round(iou, 4), "mae": round(mae, 2), "nota": round(iou * max(0.0, 1 - mae / 128), 4)}


# ---------------------------------------------------------------- conjunto de teste

def choose_testset(n_per_cat=6, seed=11):
    db = sqlite3.connect(DATA / "acervo.sqlite")
    rows = db.execute("""
        with g as (select t.name, t.tileset, t.category,
            max(case when p.key='Facing' then p.value end) f,
            max(case when p.key='CustomName' then p.value end) cn,
            max(case when p.key='GroupName' then p.value end) gn,
            max(case when p.key='SpriteGridPos' then p.value end) gp
          from tiles t join tile_props p on p.name = t.name group by t.name)
        select g.tileset, g.cn, g.gn, g.category, g.f, g.name from g
        join sprites s on s.name = g.name and s.scale = 2
        where g.f in ('S','E','N','W') and g.gp is null""").fetchall()
    groups = {}
    for ts, cn, gn, cat, f, name in rows:
        groups.setdefault((ts, cn, gn, cat), {})[f] = name
    full = [(k, v) for k, v in groups.items() if len(v) == 4]
    rnd = random.Random(seed)
    chosen = []
    wanted = ["eletrodomesticos", "cozinha", "moveis", "containers", "banheiro", "iluminacao", "decoracao", "vegetacao"]
    for cat in wanted:
        pool = [x for x in full if x[0][3] == cat]
        rnd.shuffle(pool)
        chosen += pool[:n_per_cat]
    entries = [{"key": f"{ts} | {cn} | {gn}", "category": cat, "names": names} for (ts, cn, gn, cat), names in chosen]
    (HERE / "testset.json").write_text(json.dumps(entries, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(entries)} objetos de teste ({len(full)} candidatos com 4 direções)")


# ---------------------------------------------------------------- execução

def run(approach: str, limit: int | None = None):
    mod = __import__(f"approach_{approach}")
    db = sqlite3.connect(DATA / "acervo.sqlite")
    entries = json.loads((HERE / "testset.json").read_text(encoding="utf-8"))[:limit]
    out = OUT / approach
    out.mkdir(parents=True, exist_ok=True)
    results, t0 = [], time.time()
    for i, entry in enumerate(entries):
        obj = load_obj(db, entry)
        if any(v.rgba is None for v in obj.views.values()):
            continue
        tiles = []
        per = {}
        for held in FACINGS:
            train = [f for f in FACINGS if f != held]
            try:
                mesh = mod.build(obj, train)
                pred = render(mesh, obj.views[held].angle)
            except Exception as e:                       # abordagem quebrou nesse objeto
                print(f"  ! {entry['key']} [{held}]: {e}")
                pred = np.zeros((FH, FW, 4), np.uint8)
            per[held] = score(pred, obj.views[held].rgba)
            tiles.append((obj.views[held].rgba, pred))
        mean = {k: round(float(np.mean([p[k] for p in per.values()])), 4) for k in ("iou", "mae", "nota")}
        results.append({"key": entry["key"], "category": entry["category"], "por_direcao": per, **mean})
        sheet = Image.new("RGBA", (FW * 4, FH * 2), (40, 42, 48, 255))
        for j, (real, pred) in enumerate(tiles):
            for k, im in enumerate((real, pred)):
                tile = Image.fromarray(im)
                sheet.paste(tile, (j * FW, k * FH), tile)
        ImageDraw.Draw(sheet).text((4, 4), f"{entry['key'][:60]}  nota {mean['nota']}", fill=(255, 255, 0))
        sheet.save(out / f"{i:02d}.png")
        print(f"[{i + 1}/{len(entries)}] {entry['key'][:50]:<50} iou {mean['iou']:.3f}  mae {mean['mae']:6.1f}  nota {mean['nota']:.3f}")
    summary = {"abordagem": approach, "objetos": len(results), "segundos": round(time.time() - t0, 1),
               **{k: round(float(np.mean([r[k] for r in results])), 4) for k in ("iou", "mae", "nota")},
               "por_categoria": {}}
    for cat in sorted({r["category"] for r in results}):
        rs = [r for r in results if r["category"] == cat]
        summary["por_categoria"][cat] = {k: round(float(np.mean([r[k] for r in rs])), 4) for k in ("iou", "mae", "nota")}
    (out / "resultado.json").write_text(json.dumps({"resumo": summary, "objetos": results}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=1, ensure_ascii=False))


def compare():
    rows = []
    for d in sorted(OUT.glob("*/resultado.json")):
        s = json.loads(d.read_text(encoding="utf-8"))["resumo"]
        rows.append(s)
    cats = sorted({c for s in rows for c in s["por_categoria"]})
    print(f"{'abordagem':<14}{'nota':>7}{'iou':>7}{'mae':>7}  " + "".join(f"{c[:9]:>10}" for c in cats))
    for s in sorted(rows, key=lambda s: -s["nota"]):
        print(f"{s['abordagem']:<14}{s['nota']:>7.3f}{s['iou']:>7.3f}{s['mae']:>7.1f}  "
              + "".join(f"{s['por_categoria'].get(c, {}).get('nota', float('nan')):>10.3f}" for c in cats))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    cmd = sys.argv[1]
    if cmd == "testset":
        choose_testset()
    elif cmd == "run":
        lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
        run(sys.argv[2], lim)
    elif cmd == "compare":
        compare()
