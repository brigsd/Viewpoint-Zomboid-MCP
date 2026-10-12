"""Abordagem "blocos": a forma vem das formas de geometria da B42 (caixas e cilindros) e a cor vem das imagens.

Forma  : formas de todas as direções de treino, giradas para o referencial de S e fundidas.
         Lê direto do acervo.sqlite com translate e rotate (o carregador da bancada só pega caixas sem
         translate e sem rotação, e perde cerca de metade da geometria).
Cor    : cada face é subdividida em células; cada célula é projetada em TODAS as vistas de treino em que
         aparece (teste de oclusão por z-buffer das próprias formas + filtro alpha >= 250 contra a sombra
         desenhada) e pega a cor da vista mais frontal. Sem amostra: média da face, depois do objeto.
Sem formas: cai na lógica do "cartão" para a nota continuar comparável.
"""
import math
import re
import sqlite3

import numpy as np

from harness import ANGLE, DATA, FACINGS, KX, KY, KH, FW, FH, Mesh, project, rot_y
import approach_cartao

# ---------------------------------------------------------------- configuração (as variantes mexem aqui)
CONFIG = {
    "fusion": "union",       # union | one | vote
    "dedup": 120.0,          # tolerância (1/10000 tile) para considerar duas formas a mesma
    "min_h": 300.0,          # caixas com altura <= isto são a placa de sombra no chão
    "cell": 250.0,           # lado da célula de cor
    "blend": "wavg",         # best | wavg
    "ss": 2,                 # supersampling do z-buffer de oclusão
    "tol": 0.8,              # tolerância de profundidade no teste de oclusão
    "min_front": 0.12,       # frontalidade mínima para amostrar
    "bury": True,            # descarta células enterradas em outras formas
    "merge": True,           # funde células vizinhas de cor igual em retângulos
    "mergeq": 24,            # tolerância de cor ao fundir
    "cyl": True,             # usa cilindros
    "nseg": 12,              # lados do cilindro
    "vox": True,             # caminho por voxels (fusão por voto, recorte pela silhueta)
    "vres": 320.0,           # lado do voxel
    "vfuse": "union",        # union | vote | one (no caminho por voxels)
    "hull": True,            # recorta os voxels pela silhueta de cada vista de treino
    "hull_dil": 0,           # tolerância em pixels do recorte
    "hull_alpha": 200,       # alpha mínimo para contar como silhueta
    "vtol": 1.5,             # tolerância de profundidade da oclusão no caminho por voxels
    "shade": "held",        # none | held (corrige o brilho das faces para a orientação da vista de teste)
    "shade_bonus": 0.3,      # preferência por amostras com a mesma classe de sombreamento da vista de teste
    "vmin": 6,               # menos voxels que isto => cai no cartão
}
LOG = {}                     # (obj.key, held) -> info (preenchido a cada build)

RAY = np.array([1.0, 2 * KY / KH, 1.0])      # direção do raio de visão (pontos que caem no mesmo pixel)
CAM = RAY / np.linalg.norm(RAY)              # normal·CAM > 0 => face voltada para a câmera

_DB = {}
_SHAPES = {}


# ---------------------------------------------------------------- leitura das formas

def _rot_matrix(rx, ry, rz):
    def R(axis, a):
        c, s = math.cos(a), math.sin(a)
        if axis == 0:
            return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
        if axis == 1:
            return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
        return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    d = math.radians
    return R(0, d(rx / 1e4)) @ R(1, d(ry / 1e4)) @ R(2, d(rz / 1e4))


def load_shapes(name):
    """Formas de um sprite no referencial da própria vista: caixas (lo, hi) e cilindros."""
    if name in _SHAPES:
        return _SHAPES[name]
    if "db" not in _DB:
        _DB["db"] = sqlite3.connect(f"file:{DATA / 'acervo.sqlite'}?mode=ro", uri=True)
    out = []
    rows = _DB["db"].execute("select shape,tx,ty,tz,rx,ry,rz,min_x,min_y,min_z,max_x,max_y,max_z,raw from geometry "
                             "where name=? order by shape_idx", (name,)).fetchall()
    for shape, tx, ty, tz, rx, ry, rz, x0, y0, z0, x1, y1, z1, raw in rows:
        M = _rot_matrix(rx, ry, rz)
        T = np.array([tx, ty, tz])
        if shape == "box":
            c = np.array([(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], float) @ M.T + T
            out.append({"kind": "box", "lo": c.min(0), "hi": c.max(0)})
        elif shape == "cylinder":
            g = dict(re.findall(r"(\w+) = ([-\d.]+)", raw))
            r1, r2, h = float(g["radius1"]), float(g["radius2"]), float(g["height"])
            axis = M @ np.array([0.0, 0.0, 1.0])
            out.append({"kind": "cyl", "c": T, "a": axis, "r1": r1, "r2": r2, "hh": h / 2, "M": M})
    _SHAPES[name] = out
    return out


# ---------------------------------------------------------------- sólidos (faces, dentro/fora)

def box_solid(lo, hi):
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    faces = [
        [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)],           # topo
        [(x1, y0, z0), (x1, y0, z1), (x1, y1, z1), (x1, y1, z0)],           # +x
        [(x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)],           # -x
        [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],           # +z
        [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)],           # -z
    ]
    return {"kind": "box", "lo": np.array(lo, float), "hi": np.array(hi, float),
            "faces": [np.array(f, float) for f in faces], "centre": (np.array(lo) + np.array(hi)) / 2.0}


def cyl_solid(c, a, r1, r2, hh, nseg):
    a = a / np.linalg.norm(a)
    ref = np.array([1.0, 0, 0]) if abs(a[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(a, ref)
    u /= np.linalg.norm(u)
    w = np.cross(a, u)
    ang = np.linspace(0, 2 * math.pi, nseg, endpoint=False)
    ring = lambda r, s: np.array([c + s * hh * a + r * (math.cos(t) * u + math.sin(t) * w) for t in ang])
    bot, top = ring(r1, -1), ring(r2, +1)
    faces = []
    for i in range(nseg):
        j = (i + 1) % nseg
        faces.append(np.array([bot[i], bot[j], top[j], top[i]]))
    for ring_, s in ((top, +1), (bot, -1)):
        cc = c + s * hh * a
        for i in range(0, nseg, 2):
            faces.append(np.array([cc, ring_[i], ring_[(i + 1) % nseg], ring_[(i + 2) % nseg]]))
    if a[1] < 0:        # só interessa quem vê: a face de baixo (de um cilindro vertical) sai depois por normal
        pass
    return {"kind": "cyl", "c": np.array(c, float), "a": a, "r": (r1 + r2) / 2, "hh": hh, "r1": r1, "r2": r2,
            "faces": faces, "centre": np.array(c, float)}


def solid_inside(s, pts, margin=1.0):
    if s["kind"] == "box":
        return np.all((pts > s["lo"] + margin) & (pts < s["hi"] - margin), axis=1)
    d = pts - s["c"]
    ax = d @ s["a"]
    rad = np.linalg.norm(d - ax[:, None] * s["a"], axis=1)
    rr = min(s["r1"], s["r2"])
    return (np.abs(ax) < s["hh"] - margin) & (rad < rr - margin)


def shapes_in_S(obj, train, cfg):
    """Formas de cada vista de treino, no referencial de S: [(solid_dict, view)]."""
    out = []
    for f in train:
        v = obj.views[f]
        for sh in load_shapes(v.name):
            if sh["kind"] == "box":
                if sh["hi"][1] - sh["lo"][1] <= cfg["min_h"]:
                    continue
                q = rot_y(np.array([sh["lo"], sh["hi"]], float), -v.angle)
                out.append(({"kind": "box", "lo": q.min(0), "hi": q.max(0)}, f))
            elif cfg["cyl"]:
                c = rot_y(sh["c"], -v.angle)
                a = rot_y(sh["a"], -v.angle)
                out.append(({"kind": "cyl", "c": c, "a": a, "r1": sh["r1"], "r2": sh["r2"], "hh": sh["hh"]}, f))
    return out


def same_shape(a, b, tol):
    if a["kind"] != b["kind"]:
        return False
    if a["kind"] == "box":
        return np.all(np.abs(a["lo"] - b["lo"]) < tol) and np.all(np.abs(a["hi"] - b["hi"]) < tol)
    return (np.all(np.abs(a["c"] - b["c"]) < tol) and abs(a["hh"] - b["hh"]) < tol and abs(a["r1"] - b["r1"]) < tol
            and abs(abs(a["a"] @ b["a"]) - 1) < 0.02)


def fuse(shapes, train, cfg, held_angle):
    if not shapes:
        return []
    tol = cfg["dedup"]
    mode = cfg["fusion"]
    if mode == "one":
        cnt = {f: sum(1 for b in shapes if b[1] == f) for f in train}
        best = max(train, key=lambda f: (cnt[f], -abs(((ANGLE[f] - held_angle + 180) % 360) - 180)))
        shapes = [b for b in shapes if b[1] == best]
    groups = []
    for s, f in shapes:
        for g in groups:
            if same_shape(g["s"], s, tol):
                g["views"].add(f)
                break
        else:
            groups.append({"s": s, "views": {f}})
    if mode == "vote":
        nviews_with = len({b[1] for b in shapes})
        need = 2 if nviews_with >= 2 else 1
        kept = [g for g in groups if len(g["views"]) >= need]
        groups = kept or groups
    out = []
    for g in groups:
        s = g["s"]
        out.append(box_solid(s["lo"], s["hi"]) if s["kind"] == "box"
                   else cyl_solid(s["c"], s["a"], s["r1"], s["r2"], s["hh"], cfg["nseg"]))
    return out


# ---------------------------------------------------------------- z-buffer de oclusão por vista

def raster_depth(tris, W, H):
    """tris (M,3,3) em pixels de tela (x,y,profundidade). Devolve z-buffer (maior = mais perto)."""
    zbuf = np.full((H, W), -np.inf, np.float32)
    for (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) in tris:
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
        z = w0 * z0 + w1 * z1 + w2 * z2
        sub = zbuf[miny:maxy + 1, minx:maxx + 1]
        win = inside & (z > sub)
        sub[win] = z[win]
    return zbuf


def view_zbuffer(solids, angle, ss):
    tris = []
    for s in solids:
        for corners in s["faces"]:
            p = project(rot_y(corners, angle))
            p[:, :2] *= ss
            tris.append(p[[0, 1, 2]])
            tris.append(p[[0, 2, 3]])
    return raster_depth(np.array(tris), FW * ss, FH * ss) if tris else np.full((FH * ss, FW * ss), -np.inf, np.float32)


# ---------------------------------------------------------------- células

def face_normal(corners, centre):
    n = np.cross(corners[1] - corners[0], corners[3] - corners[0])
    ln = np.linalg.norm(n)
    if ln < 1e-9:
        n = np.cross(corners[2] - corners[0], corners[3] - corners[0])
        ln = np.linalg.norm(n)
    n = n / max(ln, 1e-9)
    if n @ (corners.mean(0) - centre) < 0:
        n = -n
    return n


def make_cells(solids, cfg):
    cell = cfg["cell"]
    cs, ns, fids, faces = [], [], [], []
    for b, s in enumerate(solids):
        for fi, P in enumerate(s["faces"]):
            n = face_normal(P, s["centre"])
            if s["kind"] == "box" and n[1] < -0.5:
                continue
            lu = np.linalg.norm(P[1] - P[0])
            lv = np.linalg.norm(P[3] - P[0])
            if lu < 1 or lv < 1:
                continue
            nu, nv = max(1, int(round(lu / cell))), max(1, int(round(lv / cell)))
            fid = len(faces)
            faces.append((b, fi, nu, nv))
            uu = np.arange(nu + 1) / nu
            vv = np.arange(nv + 1) / nv
            G = ((1 - uu)[:, None, None] * (1 - vv)[None, :, None] * P[0] + uu[:, None, None] * (1 - vv)[None, :, None] * P[1]
                 + uu[:, None, None] * vv[None, :, None] * P[2] + (1 - uu)[:, None, None] * vv[None, :, None] * P[3])
            for i in range(nu):
                for j in range(nv):
                    cs.append((G[i, j], G[i + 1, j], G[i + 1, j + 1], G[i, j + 1]))
                    ns.append(n)
                    fids.append(fid)
    return np.array(cs), np.array(ns), np.array(fids), faces


def build_blocks(solids, train, obj, cfg):
    corners, normal, fid, faces = make_cells(solids, cfg)
    if len(corners) == 0:
        return None
    centre = corners.mean(1)
    N = len(corners)
    keep = np.ones(N, bool)
    if cfg["bury"]:
        pos = centre + normal * 25.0
        for s in solids:
            keep &= ~solid_inside(s, pos)
    ss = cfg["ss"]
    best_score = np.full(N, -1.0)
    col_acc = np.zeros((N, 3))
    w_acc = np.zeros(N)
    best_col = np.zeros((N, 3))
    have = np.zeros(N, bool)
    pos = centre + normal * 30.0
    for f in train:
        ang = obj.views[f].angle
        zb = view_zbuffer(solids, ang, ss)
        pf = rot_y(pos, ang)
        nf = rot_y(normal, ang)
        fr = nf @ CAM
        pr = project(pf)
        sx, sy = pr[:, 0], pr[:, 1]
        ix, iy = np.floor(sx).astype(int), np.floor(sy).astype(int)
        ok = (fr > cfg["min_front"]) & (ix >= 0) & (ix < FW) & (iy >= 0) & (iy < FH)
        jx = np.clip(np.floor(sx * ss).astype(int), 0, FW * ss - 1)
        jy = np.clip(np.floor(sy * ss).astype(int), 0, FH * ss - 1)
        ok &= pr[:, 2] >= zb[jy, jx] - cfg["tol"]
        px = obj.views[f].rgba[np.clip(iy, 0, FH - 1), np.clip(ix, 0, FW - 1)]
        ok &= px[:, 3] >= 250
        colour = px[:, :3].astype(float)
        if cfg["blend"] == "best":
            upd = ok & (fr > best_score)
            best_score[upd] = fr[upd]
            best_col[upd] = colour[upd]
        else:
            col_acc[ok] += colour[ok] * (fr[ok] ** 4)[:, None]
            w_acc[ok] += fr[ok] ** 4
        have |= ok
    cols = best_col if cfg["blend"] == "best" else col_acc / np.maximum(w_acc, 1e-9)[:, None]
    allm = cols[have & keep].mean(0) if (have & keep).any() else np.array([128.0, 128.0, 128.0])
    for fi in range(len(faces)):
        m = fid == fi
        mk = m & have
        cols[m & ~have] = cols[mk].mean(0) if mk.any() else allm
    return corners, normal, fid, keep, cols, faces, have


def to_mesh(corners, keep, cols):
    idx = np.nonzero(keep)[0]
    v = corners[idx].reshape(-1, 3)
    base = np.arange(len(idx)) * 4
    tri = np.concatenate([np.stack([base, base + 1, base + 2], 1), np.stack([base, base + 2, base + 3], 1)])
    c = np.concatenate([cols[idx], cols[idx]]).clip(0, 255).astype(np.uint8)
    return Mesh(v, tri, c)


def merge_cells(corners, keep, cols, faces, cfg):
    """Funde, por face, células vizinhas de cor quase igual em retângulos (guloso)."""
    q = cfg["mergeq"]
    verts, tris, colors = [], [], []
    off = 0
    for (b, fo, nu, nv) in faces:
        grid_keep = keep[off:off + nu * nv].reshape(nu, nv)
        grid_col = cols[off:off + nu * nv].reshape(nu, nv, 3)
        grid_cor = corners[off:off + nu * nv].reshape(nu, nv, 4, 3)
        off += nu * nv
        used = ~grid_keep
        for i in range(nu):
            for j in range(nv):
                if used[i, j]:
                    continue
                ref = grid_col[i, j]
                j2 = j + 1
                while j2 < nv and not used[i, j2] and np.abs(grid_col[i, j2] - ref).max() <= q:
                    j2 += 1
                i2 = i + 1
                while i2 < nu and all((not used[i2, jj]) and np.abs(grid_col[i2, jj] - ref).max() <= q for jj in range(j, j2)):
                    i2 += 1
                used[i:i2, j:j2] = True
                base = len(verts)
                verts.extend([grid_cor[i, j, 0], grid_cor[i2 - 1, j, 1], grid_cor[i2 - 1, j2 - 1, 2], grid_cor[i, j2 - 1, 3]])
                tris.append((base, base + 1, base + 2))
                tris.append((base, base + 2, base + 3))
                mean = grid_col[i:i2, j:j2].reshape(-1, 3).mean(0)
                colors.extend([mean, mean])
    if not verts:
        return None
    return Mesh(np.array(verts), np.array(tris, int), np.clip(np.array(colors), 0, 255).astype(np.uint8))


# ---------------------------------------------------------------- caminho por voxels

XZ, YMAX = 10000.0, 26000.0


def grid_dims(r):
    return int(math.ceil(2 * XZ / r)), int(math.ceil(YMAX / r)), int(math.ceil(2 * XZ / r))


def axis_centres(r, n, lo):
    return lo + (np.arange(n) + 0.5) * r


def raster_shape(s, r, dims):
    """Voxels (nx,ny,nz) ocupados por uma forma no referencial de S."""
    nx, ny, nz = dims
    cx, cy, cz = axis_centres(r, nx, -XZ), axis_centres(r, ny, 0.0), axis_centres(r, nz, -XZ)
    if s["kind"] == "box":
        def ov(c, lo, hi):
            o = np.minimum(c + r / 2, hi) - np.maximum(c - r / 2, lo)
            return o >= 0.5 * min(r, max(hi - lo, 1e-6))
        return (ov(cx, s["lo"][0], s["hi"][0])[:, None, None] & ov(cy, s["lo"][1], s["hi"][1])[None, :, None]
                & ov(cz, s["lo"][2], s["hi"][2])[None, None, :])
    c, a, r1, r2, hh = s["c"], s["a"] / np.linalg.norm(s["a"]), s["r1"], s["r2"], s["hh"]
    ext = hh * abs(a) + max(r1, r2)
    sl = []
    for k, cc in enumerate((cx, cy, cz)):
        sl.append(np.nonzero((cc > c[k] - ext[k] - r) & (cc < c[k] + ext[k] + r))[0])
    out = np.zeros(dims, bool)
    if any(len(q) == 0 for q in sl):
        return out
    X, Y, Z = np.meshgrid(cx[sl[0]], cy[sl[1]], cz[sl[2]], indexing="ij")
    d = np.stack([X - c[0], Y - c[1], Z - c[2]], -1)
    ax = d @ a
    rad = np.linalg.norm(d - ax[..., None] * a, axis=-1)
    lim = r1 + (r2 - r1) * (ax + hh) / (2 * hh)
    inside = (np.abs(ax) <= hh + r * 0.25) & (rad <= lim + r * 0.25)
    out[np.ix_(*sl)] = inside
    return out


def alpha_mask(rgba, thr, dil):
    m = rgba[..., 3] >= thr
    for _ in range(dil):
        n = m.copy()
        n[1:] |= m[:-1]
        n[:-1] |= m[1:]
        n[:, 1:] |= m[:, :-1]
        n[:, :-1] |= m[:, 1:]
        m = n
    return m


def voxel_model(obj, train, cfg, held_angle):
    r = cfg["vres"]
    dims = grid_dims(r)
    occs = {}
    for f in train:
        v = obj.views[f]
        acc = None
        for sh in load_shapes(v.name):
            if sh["kind"] == "box":
                if sh["hi"][1] - sh["lo"][1] <= cfg["min_h"]:
                    continue
                q = rot_y(np.array([sh["lo"], sh["hi"]], float), -v.angle)
                s = {"kind": "box", "lo": q.min(0), "hi": q.max(0)}
            elif cfg["cyl"]:
                s = {"kind": "cyl", "c": rot_y(sh["c"], -v.angle), "a": rot_y(sh["a"], -v.angle),
                     "r1": sh["r1"], "r2": sh["r2"], "hh": sh["hh"]}
            else:
                continue
            o = raster_shape(s, r, dims)
            acc = o if acc is None else (acc | o)
        if acc is not None:
            occs[f] = acc
    if not occs:
        return None
    mode = cfg["vfuse"]
    fs = list(occs)
    if mode == "one":
        best = max(fs, key=lambda f: (int(occs[f].sum()), -abs(((ANGLE[f] - held_angle + 180) % 360) - 180)))
        O = occs[best]
    elif mode == "vote" and len(fs) >= 2:
        cnt = sum(occs[f].astype(np.int8) for f in fs)
        O = cnt >= 2
    else:
        O = np.zeros(dims, bool)
        for f in fs:
            O |= occs[f]
    if cfg["hull"] and O.any():
        idx = np.argwhere(O)
        pts = np.stack([-XZ + (idx[:, 0] + .5) * r, (idx[:, 1] + .5) * r, -XZ + (idx[:, 2] + .5) * r], 1)
        ok = np.ones(len(idx), bool)
        for f in train:
            m = alpha_mask(obj.views[f].rgba, cfg["hull_alpha"], cfg["hull_dil"])
            pr = project(rot_y(pts, obj.views[f].angle))
            ix, iy = np.floor(pr[:, 0]).astype(int), np.floor(pr[:, 1]).astype(int)
            inb = (ix >= 0) & (ix < FW) & (iy >= 0) & (iy < FH)
            ok &= inb & m[np.clip(iy, 0, FH - 1), np.clip(ix, 0, FW - 1)]
        O = np.zeros(dims, bool)
        O[tuple(idx[ok].T)] = True
    return O


def surface_cells(O, r):
    """Faces expostas dos voxels (sem a de baixo): corners (N,4,3), normal (N,3), grupo (N,), u, v."""
    cs, ns, gs, us, vs = [], [], [], [], []
    lo = (-XZ, 0.0, -XZ)
    inplane = {0: (2, 1), 1: (0, 2), 2: (0, 1)}
    gid = {}
    for ax in range(3):
        for sg in (+1, -1):
            if ax == 1 and sg == -1:
                continue
            nb = np.zeros_like(O)
            sl_a = [slice(None)] * 3
            sl_b = [slice(None)] * 3
            if sg > 0:
                sl_a[ax] = slice(0, -1)
                sl_b[ax] = slice(1, None)
            else:
                sl_a[ax] = slice(1, None)
                sl_b[ax] = slice(0, -1)
            nb[tuple(sl_a)] = O[tuple(sl_b)]
            idx = np.argwhere(O & ~nb)
            if len(idx) == 0:
                continue
            au, av = inplane[ax]
            plane = lo[ax] + (idx[:, ax] + (1 if sg > 0 else 0)) * r
            u0 = lo[au] + idx[:, au] * r
            v0 = lo[av] + idx[:, av] * r
            C = np.zeros((len(idx), 4, 3))
            for k, (du, dv) in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))):
                C[:, k, ax] = plane
                C[:, k, au] = u0 + du * r
                C[:, k, av] = v0 + dv * r
            n = np.zeros(3)
            n[ax] = sg
            slices = idx[:, ax]
            for sv in np.unique(slices):
                gid[(ax, sg, int(sv))] = len(gid)
            g = np.array([gid[(ax, sg, int(sv))] for sv in slices])
            cs.append(C)
            ns.append(np.tile(n, (len(idx), 1)))
            gs.append(g)
            us.append(idx[:, au])
            vs.append(idx[:, av])
    if not cs:
        return None
    return (np.concatenate(cs), np.concatenate(ns), np.concatenate(gs), np.concatenate(us), np.concatenate(vs))


def zbuffer_from_cells(corners, angle, ss):
    """z-buffer de oclusão por espalhamento de pontos de cada célula (mais rápido que rasterizar triângulos)."""
    W, H = FW * ss, FH * ss
    zb = np.full(W * H, -np.inf, np.float32)
    ts = (1 / 6, 3 / 6, 5 / 6)
    for a in ts:
        for b in ts:
            p = ((1 - a) * (1 - b) * corners[:, 0] + a * (1 - b) * corners[:, 1] + a * b * corners[:, 2]
                 + (1 - a) * b * corners[:, 3])
            pr = project(rot_y(p, angle))
            ix = np.floor(pr[:, 0] * ss).astype(int)
            iy = np.floor(pr[:, 1] * ss).astype(int)
            ok = (ix >= 0) & (ix < W) & (iy >= 0) & (iy < H)
            np.maximum.at(zb, iy[ok] * W + ix[ok], pr[ok, 2].astype(np.float32))
    return zb.reshape(H, W)


def fill_missing(cols, have, g, u, v, normal):
    """Preenche células sem amostra com vizinhos do mesmo plano; depois média do plano, da orientação, global."""
    cols = cols.copy()
    known = have.copy()
    for gi in np.unique(g[~have]):
        m = np.nonzero(g == gi)[0]
        uu, vv = u[m] - u[m].min(), v[m] - v[m].min()
        nu, nv = uu.max() + 1, vv.max() + 1
        G = np.zeros((nu, nv, 3))
        K = np.zeros((nu, nv), bool)
        M = np.zeros((nu, nv), bool)
        G[uu, vv] = cols[m]
        K[uu, vv] = known[m]
        M[uu, vv] = True
        for _ in range(60):
            if (M & ~K).sum() == 0:
                break
            acc = np.zeros((nu, nv, 3))
            cnt = np.zeros((nu, nv))
            for du, dv in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                Gs = np.roll(G, (du, dv), (0, 1))
                Ks = np.roll(K, (du, dv), (0, 1))
                if du == 1:
                    Ks[0] = False
                if du == -1:
                    Ks[-1] = False
                if dv == 1:
                    Ks[:, 0] = False
                if dv == -1:
                    Ks[:, -1] = False
                acc += Gs * Ks[..., None]
                cnt += Ks
            new = (M & ~K) & (cnt > 0)
            if not new.any():
                break
            G[new] = acc[new] / cnt[new][:, None]
            K[new] = True
        cols[m] = G[uu, vv]
        known[m] = K[uu, vv]
    if (~known).any():
        gm = cols[known].mean(0) if known.any() else np.array([128.0, 128.0, 128.0])
        for gi in np.unique(g[~known]):
            m = (g == gi)
            mk = m & known
            if mk.any():
                cols[m & ~known] = cols[mk].mean(0)
                known |= m
        if (~known).any():
            for key in {tuple(n) for n in normal[~known]}:
                m = np.all(normal == key, axis=1)
                mk = m & known
                cols[m & ~known] = cols[mk].mean(0) if mk.any() else gm
    return cols


def merge_voxel_cells(corners, g, u, v, cols, q):
    verts, tris, colors = [], [], []
    for gi in np.unique(g):
        m = np.nonzero(g == gi)[0]
        u0, v0 = u[m].min(), v[m].min()
        uu, vv = u[m] - u0, v[m] - v0
        nu, nv = uu.max() + 1, vv.max() + 1
        ID = -np.ones((nu, nv), int)
        ID[uu, vv] = m
        used = ID < 0
        for i in range(nu):
            for j in range(nv):
                if used[i, j]:
                    continue
                ref = cols[ID[i, j]]
                j2 = j + 1
                while j2 < nv and not used[i, j2] and np.abs(cols[ID[i, j2]] - ref).max() <= q:
                    j2 += 1
                i2 = i + 1
                while i2 < nu and all((not used[i2, jj]) and np.abs(cols[ID[i2, jj]] - ref).max() <= q
                                      for jj in range(j, j2)):
                    i2 += 1
                used[i:i2, j:j2] = True
                base = len(verts)
                verts.extend([corners[ID[i, j], 0], corners[ID[i2 - 1, j], 1],
                              corners[ID[i2 - 1, j2 - 1], 2], corners[ID[i, j2 - 1], 3]])
                tris.append((base, base + 1, base + 2))
                tris.append((base, base + 2, base + 3))
                mean = cols[ID[i:i2, j:j2].ravel()].mean(0)
                colors.extend([mean, mean])
    return Mesh(np.array(verts), np.array(tris, int), np.clip(np.array(colors), 0, 255).astype(np.uint8))


def shade_class(nv):
    """Classe de sombreamento da face na vista: 0 topo, 1 voltada para +x, 2 voltada para +z, -1 de costas."""
    return np.where(nv[:, 1] > 0.5, 0, np.where(nv[:, 0] > 0.5, 1, np.where(nv[:, 2] > 0.5, 2, -1)))


def estimate_gain(samples):
    """Razão de brilho (canal a canal) da classe 2 sobre a classe 1, vista nas mesmas células por vistas diferentes."""
    diffs = []
    for i in range(len(samples)):
        for j in range(len(samples)):
            if i == j:
                continue
            oki, ci, ki, _ = samples[i]
            okj, cj, kj, _ = samples[j]
            m = oki & okj & (ki == 2) & (kj == 1)
            if m.any():
                diffs.append(np.log(ci[m] + 8.0) - np.log(cj[m] + 8.0))
    if not diffs:
        return None
    d = np.concatenate(diffs)
    if len(d) < 12:
        return None
    return np.exp(np.median(d, axis=0))             # k2 / k1


def convert_shade(colour, cls_f, cls_h, rho):
    out = colour.copy()
    up = (cls_f == 1) & (cls_h == 2)
    dn = (cls_f == 2) & (cls_h == 1)
    out[up] = (colour[up] + 8.0) * rho - 8.0
    out[dn] = (colour[dn] + 8.0) / rho - 8.0
    return out.clip(0, 255)


def build_voxel(obj, train, cfg, held_angle):
    r = cfg["vres"]
    O = voxel_model(obj, train, cfg, held_angle)
    if O is None or O.sum() < cfg["vmin"]:
        return None, {}
    sc = surface_cells(O, r)
    if sc is None:
        return None, {}
    corners, normal, g, u, v = sc
    N = len(corners)
    pos = corners.mean(1) + normal * 30.0
    ss = cfg["ss"]
    samples = []                       # por vista: (ok, cor, classe de sombreamento, frontalidade)
    have = np.zeros(N, bool)
    for f in train:
        ang = obj.views[f].angle
        zb = zbuffer_from_cells(corners, ang, ss)
        nf = rot_y(normal, ang)
        fr = nf @ CAM
        pr = project(rot_y(pos, ang))
        ix, iy = np.floor(pr[:, 0]).astype(int), np.floor(pr[:, 1]).astype(int)
        ok = (fr > cfg["min_front"]) & (ix >= 0) & (ix < FW) & (iy >= 0) & (iy < FH)
        jx = np.clip(np.floor(pr[:, 0] * ss).astype(int), 0, FW * ss - 1)
        jy = np.clip(np.floor(pr[:, 1] * ss).astype(int), 0, FH * ss - 1)
        ok &= pr[:, 2] >= zb[jy, jx] - cfg["vtol"]
        px = obj.views[f].rgba[np.clip(iy, 0, FH - 1), np.clip(ix, 0, FW - 1)]
        ok &= px[:, 3] >= 250
        samples.append((ok, px[:, :3].astype(float), shade_class(nf), fr))
        have |= ok
    cls_h = shade_class(rot_y(normal, held_angle))
    gain = estimate_gain(samples) if cfg["shade"] == "held" else None
    best_score = np.full(N, -1e9)
    cols = np.zeros((N, 3))
    w_acc = np.zeros(N)
    for ok, colour, cls, fr in samples:
        c = colour
        score = fr.copy()
        if gain is not None:
            c = convert_shade(colour, cls, cls_h, gain)
            score = score + cfg["shade_bonus"] * (cls == cls_h)
        if cfg["blend"] == "best":
            upd = ok & (score > best_score)
            best_score[upd] = score[upd]
            cols[upd] = c[upd]
        else:
            wgt = np.where(ok, np.maximum(score, 0) ** 4, 0.0)
            cols += c * wgt[:, None]
            w_acc += wgt
    if cfg["blend"] != "best":
        cols = cols / np.maximum(w_acc, 1e-9)[:, None]
    cols = fill_missing(cols, have, g, u, v, normal)
    mesh = (merge_voxel_cells(corners, g, u, v, cols, cfg["mergeq"]) if cfg["merge"]
            else to_mesh(corners, np.ones(N, bool), cols))
    return mesh, {"voxels": int(O.sum()), "cells": N, "sampled": float(have.mean())}


# ---------------------------------------------------------------- interface

def build(obj, train):
    cfg = CONFIG
    held = next(f for f in FACINGS if f not in train)
    if cfg["vox"]:
        mesh, extra = build_voxel(obj, train, cfg, obj.views[held].angle)
        if mesh is None:
            mesh = approach_cartao.build(obj, train)
            LOG[(obj.key, held)] = {"fallback": True, "tris": len(mesh.faces)}
        else:
            LOG[(obj.key, held)] = {"fallback": False, "tris": len(mesh.faces), **extra}
        return mesh
    solids = fuse(shapes_in_S(obj, train, cfg), train, cfg, obj.views[held].angle)
    info = {"boxes": len(solids), "fallback": False}
    res = build_blocks(solids, train, obj, cfg) if solids else None
    mesh = None
    if res is not None:
        corners, normal, fid, keep, cols, faces, have = res
        mesh = merge_cells(corners, keep, cols, faces, cfg) if cfg["merge"] else to_mesh(corners, keep, cols)
    if mesh is None:
        mesh = approach_cartao.build(obj, train)
        info.update(fallback=True, tris=len(mesh.faces))
    else:
        info.update(tris=len(mesh.faces), sampled=float(have[keep].mean()) if keep.any() else 0.0)
    LOG[(obj.key, held)] = info
    return mesh
