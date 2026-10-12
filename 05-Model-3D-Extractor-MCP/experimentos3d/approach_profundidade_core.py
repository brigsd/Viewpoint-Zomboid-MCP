"""Núcleo compartilhado das abordagens "profundidade": superfícies por mapa de profundidade (fusão) e
escultura por voxels com silhueta + profundidade (carving). Usado pelos arquivos approach_profundidade*.py.

Convenções (README do acervo): ponto na vista f -> referencial S = rot_y(p, -angle_f).
Profundidade da projeção: d = KX*(x+z) + 0.005225*y  (maior = mais perto); cinza = 190 - d.
"""
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import harness as H                                    # noqa: E402
from harness import FW, FH, KX, KY, KH, OX, OY, Mesh, rot_y, unproject   # noqa: E402

KD = 0.005225
_DB = None
_ASSIGN_CACHE = {}


# ---------------------------------------------------------------- profundidade (com atribuições)

def _db():
    global _DB
    if _DB is None:
        _DB = sqlite3.connect(H.DATA / "acervo.sqlite")
    return _DB


def resolve_depth(view):
    """Profundidade da vista; se faltar, usa a atribuída em depth_assignments (tileDepthTextureAssignments.txt)."""
    if view.depth is not None:
        return view.depth
    name = view.name
    if name in _ASSIGN_CACHE:
        return _ASSIGN_CACHE[name]
    db = _db()
    row = db.execute("select depth from depth_assignments where name=?", (name,)).fetchone()
    g = None
    if row:
        g = H.load_depth(db, row[0])
    _ASSIGN_CACHE[name] = g
    return g


def depth_iou(rgba, depth):
    """Quanto o mapa de profundidade coincide com a silhueta do sprite (IoU entre os dois)."""
    a = rgba[..., 3] >= 200
    m = np.isfinite(depth)
    return float((a & m).sum() / max(1, (a | m).sum()))


def get_depths(obj, train, use_assign=True, min_iou=0.0):
    """Profundidade por vista. Descarta (None) a que não bate com o sprite (IoU < min_iou): vira só silhueta."""
    out = {}
    for f in train:
        v = obj.views[f]
        d = resolve_depth(v) if use_assign else v.depth
        if d is not None and min_iou > 0 and depth_iou(v.rgba, d) < min_iou:
            d = None
        out[f] = d
    return out


def sprite_mask(rgba, thr=250):
    return rgba[..., 3] >= thr


# ---------------------------------------------------------------- vistas: direção da câmera no referencial S

def cam_dir_view():
    v = np.array([KX, KD, KX])
    return v / np.linalg.norm(v)


def cam_dir_S(angle):
    return rot_y(cam_dir_view()[None], -angle)[0]


# ---------------------------------------------------------------- 1) fusão de superfícies

def corner_depths(G, valid, thr):
    """Profundidade em cada canto de pixel (H+1,W+1) por pixel: (4,H,W) - média dos vizinhos contínuos."""
    Hh, Ww = G.shape
    Gp = np.full((Hh + 2, Ww + 2), np.nan, np.float32)
    Gp[1:-1, 1:-1] = np.where(valid, G, np.nan)
    out = np.zeros((4, Hh, Ww), np.float32)
    # cantos do pixel (y,x): (0,0) (0,1) (1,0) (1,1) -> pixels que compartilham o canto
    for k, (cy, cx) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
        acc = np.zeros((Hh, Ww), np.float32)
        cnt = np.zeros((Hh, Ww), np.float32)
        for oy in (cy - 1, cy):
            for ox in (cx - 1, cx):
                nb = Gp[1 + oy:1 + oy + Hh, 1 + ox:1 + ox + Ww]
                ok = np.isfinite(nb) & (np.abs(nb - np.where(valid, G, 0)) <= thr)
                acc += np.where(ok, nb, 0)
                cnt += ok
        out[k] = np.where(cnt > 0, acc / np.maximum(cnt, 1), np.where(valid, G, 0))
    return out


def height_field(rgba, depth, angle, thr=3.0, amin=250):
    """Malha de campo de altura: um quadrado (2 triângulos) por pixel; cantos suavizados entre vizinhos contínuos.
    Quebra nas descontinuidades (vizinhos além de `thr` níveis de cinza não se ligam).
    Devolve vértices (N,3) no referencial S, faces (M,3) e cores (M,3)."""
    valid = (rgba[..., 3] >= amin) & np.isfinite(depth)
    ys, xs = np.nonzero(valid)
    if len(ys) == 0:
        return np.zeros((0, 3)), np.zeros((0, 3), int), np.zeros((0, 3), np.uint8)
    G = np.where(valid, depth, 0)
    cd = corner_depths(G, valid, thr)
    n = len(ys)
    corners = []
    for k, (dy, dx) in enumerate(((0, 0), (0, 1), (1, 1), (1, 0))):      # sentido: (0,0)(1,0)(1,1)(0,1) em (x,y)
        kk = {(0, 0): 0, (0, 1): 1, (1, 0): 2, (1, 1): 3}[(dy, dx)]
        corners.append(unproject(xs + dx, ys + dy, cd[kk][ys, xs]))
    v = np.concatenate(corners)
    v = rot_y(v, -angle)
    i = np.arange(n)
    faces = np.concatenate([np.stack([i, i + n, i + 2 * n], 1), np.stack([i, i + 2 * n, i + 3 * n], 1)])
    colors = np.concatenate([rgba[ys, xs, :3]] * 2)
    return v, faces, colors.astype(np.uint8)


# ---------------------------------------------------------------- 2) escultura por voxels

class Carve:
    def __init__(self, vox=125.0, xz=5500.0):
        self.vox = vox
        self.xz = xz


def rot_y_each(p, deg):
    """rot_y com um ângulo (graus) por ponto."""
    t = np.radians(deg)
    c, s_ = np.cos(t), np.sin(t)
    return np.stack([p[:, 0] * c - p[:, 2] * s_, p[:, 1], p[:, 0] * s_ + p[:, 2] * c], axis=1)


def project_pts(p, angle):
    """p (N,3) no referencial S -> sx, sy, d (profundidade; maior = mais perto) da vista de ângulo `angle`."""
    q = rot_y(p, angle)
    x, y, z = q[:, 0], q[:, 1], q[:, 2]
    return OX + KX * (x - z), OY + KY * (x + z) - KH * y, KX * (x + z) + KD * y


def carve_voxels(views, vox=125.0, xz=5500.0, tol=3.0, dil=0, amin=200, ybound=None, q=None, tol_max=30.0):
    """views: lista de (rgba, depth|None, angle). Devolve (grid bool (nx,ny,nz), origem (3,), vox, tol usada).
    Cada voxel guarda `need` = o quanto ele fica à frente da superfície de profundidade na pior vista; ele
    sobrevive se need <= tol. Com q (0..1), tol é escolhida de modo que a fração q dos voxels da casca de
    silhueta sobreviva (profundidades inconsistentes entre vistas -> tolerância maior; limite tol_max)."""
    ymax = 28000.0
    for rgba, depth, ang in views:
        ys, xs = np.nonzero(rgba[..., 3] >= amin)
        if len(ys):
            ymax = min(ymax, (OY + KY * 2 * xz - ys.min()) / KH)
    if ybound is not None:
        ymax = min(ymax, ybound)
    xs_ = np.arange(-xz + vox / 2, xz, vox)
    ys_ = np.arange(vox / 2 - 300, ymax + 300, vox)
    zs_ = np.arange(-xz + vox / 2, xz, vox)
    X, Y, Z = np.meshgrid(xs_, ys_, zs_, indexing="ij")
    P = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)
    idx = np.arange(len(P))
    need = np.full(len(P), -np.inf)
    for rgba, depth, ang in views:
        sx, sy, d = project_pts(P[idx], ang)
        ix, iy = np.floor(sx).astype(int), np.floor(sy).astype(int)
        inside = (ix >= 0) & (ix < FW) & (iy >= 0) & (iy < FH)
        a = rgba[..., 3] >= amin
        if dil:
            from scipy.ndimage import binary_dilation
            a = binary_dilation(a, iterations=dil)
        ixc, iyc = np.clip(ix, 0, FW - 1), np.clip(iy, 0, FH - 1)
        ok = inside & a[iyc, ixc]
        if depth is not None:
            g = depth[iyc, ixc]
            nd = np.where(np.isfinite(g), d - (190.0 - g), -np.inf)   # >0: voxel à frente da superfície
            need[idx] = np.maximum(need[idx], nd)
        idx = idx[ok]
        if len(idx) == 0:
            break
    nn = need[idx]
    if q is not None and len(idx):
        fin = nn[np.isfinite(nn)]
        if len(fin):
            tol = float(np.clip(np.quantile(fin, q), tol, tol_max))
    keep = idx[nn <= tol]
    grid = np.zeros(len(P), bool)
    grid[keep] = True
    return grid.reshape(X.shape), np.array([xs_[0], ys_[0], zs_[0]]), vox, tol


def hull_coverage(grid, org, vox, views, amin=200):
    """Fração mínima (entre as vistas) da silhueta do sprite coberta pela projeção do volume esculpido.
    Volume coerente com as vistas -> perto de 1; vistas desalinhadas -> a interseção some e a cobertura cai."""
    from scipy.ndimage import binary_closing
    idx = np.argwhere(grid)
    if len(idx) == 0:
        return 0.0
    P = org + idx * vox
    worst = 1.0
    for rgba, depth, ang in views:
        sil = rgba[..., 3] >= amin
        sx, sy, _ = project_pts(P, ang)
        m = np.zeros((FH, FW), bool)
        ix, iy = np.floor(sx).astype(int), np.floor(sy).astype(int)
        ok = (ix >= 0) & (ix < FW) & (iy >= 0) & (iy < FH)
        m[iy[ok], ix[ok]] = True
        m = binary_closing(m, iterations=1)
        worst = min(worst, float((m & sil).sum() / max(1, sil.sum())))
    return worst


def carve_adaptive(views, dils=(0, 1, 2, 3), cov_min=0.85, **kw):
    """Esculpe com a menor dilatação de silhueta que deixe o volume coerente com todas as vistas."""
    best = None
    for dl in dils:
        g, org, vox, tol = carve_voxels(views, dil=dl, **kw)
        cov = hull_coverage(g, org, vox, views)
        if best is None or cov > best[0]:
            best = (cov, g, org, vox, tol, dl)
        if cov >= cov_min:
            break
    return best


# direções das faces: eixo, sinal
DIRS = [(0, 1), (0, -1), (1, 1), (1, -1), (2, 1), (2, -1)]


def exposed_faces(grid):
    """Lista de faces expostas: arrays (ijk (N,3), dir idx (N,))."""
    pad = np.pad(grid, 1)
    ijk_all, d_all = [], []
    for di, (ax, sg) in enumerate(DIRS):
        sh = [slice(1, -1)] * 3
        nb = list(sh)
        nb[ax] = slice(1 + sg, pad.shape[ax] - 1 + sg)
        m = grid & ~pad[tuple(nb)]
        ijk = np.argwhere(m)
        ijk_all.append(ijk)
        d_all.append(np.full(len(ijk), di))
    return np.concatenate(ijk_all), np.concatenate(d_all)


def face_geometry(ijk, dirs, org, vox):
    """Centro e normal de cada face."""
    normals = np.zeros((len(ijk), 3))
    for di, (ax, sg) in enumerate(DIRS):
        m = dirs == di
        normals[m, ax] = sg
    centre = org + ijk * vox + normals * vox / 2
    return centre, normals


def sample_views(centre, normals, surf_centres, views, amin=250, tol=4.0, zs=2):
    """Para cada vista de treino: cor da face nessa vista (n,3), `ok` (opaca, voltada e visível pelo z-buffer do
    próprio modelo) e `front` (cosseno entre a normal e a direção da câmera)."""
    from scipy.ndimage import maximum_filter
    out = []
    for rgba, ang in views:
        cd = cam_dir_S(ang)
        front = normals @ cd
        sx, sy, d = project_pts(centre, ang)
        vsx, vsy, vd = project_pts(surf_centres, ang)
        W2, H2 = FW * zs, FH * zs
        zb = np.full((H2, W2), -np.inf, np.float32)
        px = np.clip((vsx * zs).astype(int), 0, W2 - 1)
        py = np.clip((vsy * zs).astype(int), 0, H2 - 1)
        np.maximum.at(zb, (py, px), vd.astype(np.float32))
        zb = maximum_filter(zb, size=3)
        ix, iy = np.floor(sx).astype(int), np.floor(sy).astype(int)
        ok_px = (ix >= 0) & (ix < FW) & (iy >= 0) & (iy < FH)
        ixc, iyc = np.clip(ix, 0, FW - 1), np.clip(iy, 0, FH - 1)
        opaque = ok_px & (rgba[iyc, ixc, 3] >= amin)
        pz = zb[np.clip((sy * zs).astype(int), 0, H2 - 1), np.clip((sx * zs).astype(int), 0, W2 - 1)]
        vis = d >= pz - tol
        out.append({"col": rgba[iyc, ixc, :3].astype(np.float32), "opaque": opaque, "vis": vis, "front": front})
    return out


# Sombreamento do jogo por papel da face na vista (fixo na câmera): [direita(+x), esquerda(+z), topo(+y)] x RGB.
# Calibrado em calibra_sombra() (mediana das razões de cor da mesma face vista por duas vistas com papéis diferentes).
SHADE = np.array([[0.836, 0.827, 0.811], [1, 1, 1], [1, 1, 1]], np.float32)   # direita é ~17% mais escura que a esquerda


def face_role(normals, angle):
    """Papel de cada face na vista de ângulo `angle`: 0 direita(+x), 1 esquerda(+z), 2 topo(+y), -1 não visível."""
    nv = rot_y(normals, angle)
    role = np.full(len(normals), -1)
    role[nv[:, 0] > 0.5] = 0
    role[nv[:, 2] > 0.5] = 1
    role[nv[:, 1] > 0.5] = 2
    return role


def color_faces(centre, normals, surf_centres, views, amin=250, tol=4.0, zs=2, relight_to=None, shade=None, smooth_r=0.0):
    """Cor de cada face: a vista que a enxerga de forma mais frontal, com checagem de oclusão pelo próprio modelo.
    relight_to: ângulo da vista de saída; se dado, converte para albedo (divide pelo sombreamento do papel na vista
    de origem) e reaplica o sombreamento do papel da face nessa vista (shade: matriz 3x3)."""
    n = len(centre)
    S = sample_views(centre, normals, surf_centres, views, amin, tol, zs)
    best = np.full(n, -1.0)
    col = np.zeros((n, 3), np.float32)
    got = np.zeros(n, bool)
    fb = np.full(n, -1.0)
    fcol = np.zeros((n, 3), np.float32)
    fgot = np.zeros(n, bool)
    src_role = np.full(n, -1)
    fsrc_role = np.full(n, -1)
    src_angle = np.zeros(n)
    fsrc_angle = np.zeros(n)
    for (rgba, ang), s in zip(views, S):
        score = np.where(s["front"] > 0.05, s["front"], -1)
        role = face_role(normals, ang)
        upd = s["opaque"] & s["vis"] & (score > best)
        best = np.where(upd, score, best)
        col[upd] = s["col"][upd]
        src_role[upd] = role[upd]
        src_angle[upd] = ang
        got |= upd
        updf = s["opaque"] & (s["front"] > fb)
        fb = np.where(updf, s["front"], fb)
        fcol[updf] = s["col"][updf]
        fsrc_role[updf] = role[updf]
        fsrc_angle[updf] = ang
        fgot |= updf
    use_f = ~got & fgot
    col[use_f] = fcol[use_f]
    src_role[use_f] = fsrc_role[use_f]
    src_angle[use_f] = fsrc_angle[use_f]
    got |= use_f
    if (~got).any():
        mean = col[got].mean(0) if got.any() else np.array([128, 128, 128])
        col[~got] = mean
    if relight_to is not None:
        sh = SHADE if shade is None else shade
        if smooth_r > 0:
            from scipy.spatial import cKDTree
            tree = cKDTree(centre)
            nb = tree.query_ball_point(centre, smooth_r)
            ns = np.stack([normals[ix].sum(0) for ix in nb])
            ns /= np.maximum(np.linalg.norm(ns, axis=1, keepdims=True), 1e-6)
        else:
            ns = normals
        # fonte: ângulo da vista que deu a cor de cada face
        alb = col / np.maximum(soft_gain(rot_y_each(ns, src_angle), sh), 1e-3)
        col = alb * soft_gain(rot_y(ns, relight_to), sh)
    return np.clip(col, 0, 255).astype(np.uint8), got


def greedy_mesh(ijk, dirs, colors, org, vox, qbits=3, tolc=0.0):
    """Funde faces coplanares vizinhas em retângulos. Duas faces entram no mesmo retângulo se a cor for igual após
    quantizar `qbits` bits (tolc=0) ou, com tolc>0, se a cor ficar a menos de `tolc` (distância média por canal)
    da cor da primeira face do retângulo. O retângulo recebe a cor média."""
    cf = colors.astype(np.float32)
    q = (colors.astype(np.int32) >> qbits)
    qcol = (q[:, 0] << 16) | (q[:, 1] << 8) | q[:, 2]
    verts, faces, cols = [], [], []
    nv = 0
    for di, (ax, sg) in enumerate(DIRS):
        m = dirs == di
        if not m.any():
            continue
        a1, a2 = [k for k in range(3) if k != ax]
        pts, lab, cs = ijk[m], qcol[m], cf[m]
        order = np.argsort(pts[:, ax], kind="stable")
        pts, lab, cs = pts[order], lab[order], cs[order]
        bounds = np.flatnonzero(np.diff(pts[:, ax])) + 1
        for lo_i, hi_i in zip(np.r_[0, bounds], np.r_[bounds, len(pts)]):
            p, l, c = pts[lo_i:hi_i], lab[lo_i:hi_i], cs[lo_i:hi_i]
            sl = p[0, ax]
            u0, v0 = p[:, a1].min(), p[:, a2].min()
            nu, nvv = p[:, a1].max() - u0 + 1, p[:, a2].max() - v0 + 1
            grid = np.full((nu, nvv), -1, np.int64)
            cg = np.zeros((nu, nvv, 3), np.float32)
            have = np.zeros((nu, nvv), bool)
            grid[p[:, a1] - u0, p[:, a2] - v0] = l
            cg[p[:, a1] - u0, p[:, a2] - v0] = c
            have[p[:, a1] - u0, p[:, a2] - v0] = True
            used = ~have
            for u in range(nu):
                for v in range(nvv):
                    if used[u, v]:
                        continue
                    if tolc > 0:
                        seed = cg[u, v]
                        okrow = lambda uu, vv, w=1: (~used[uu:uu + w, vv]).all() and                             (np.abs(cg[uu:uu + w, vv] - seed).mean(1) <= tolc).all()
                        w = 1
                        while u + w < nu and okrow(u + w, v):
                            w += 1
                        h = 1
                        while v + h < nvv and (~used[u:u + w, v + h]).all() and                                 (np.abs(cg[u:u + w, v + h] - seed).mean(1) <= tolc).all():
                            h += 1
                    else:
                        L = grid[u, v]
                        w = 1
                        while u + w < nu and not used[u + w, v] and grid[u + w, v] == L:
                            w += 1
                        h = 1
                        while v + h < nvv and (grid[u:u + w, v + h] == L).all() and not used[u:u + w, v + h].any():
                            h += 1
                    used[u:u + w, v:v + h] = True
                    colr = cg[u:u + w, v:v + h].reshape(-1, 3).mean(0).astype(np.uint8)
                    lo = np.zeros(3)
                    hi = np.zeros(3)
                    lo[ax] = hi[ax] = (sl + (0.5 if sg > 0 else -0.5)) * vox
                    lo[a1], hi[a1] = (u + u0 - 0.5) * vox, (u + u0 + w - 0.5) * vox
                    lo[a2], hi[a2] = (v + v0 - 0.5) * vox, (v + v0 + h - 0.5) * vox
                    c0, c1, c2, c3 = lo.copy(), lo.copy(), hi.copy(), lo.copy()
                    c1[a1] = hi[a1]
                    c3[a2] = hi[a2]
                    verts.extend([c0 + org, c1 + org, c2 + org, c3 + org])
                    faces.extend([[nv, nv + 1, nv + 2], [nv, nv + 2, nv + 3]])
                    cols.extend([colr, colr])
                    nv += 4
    if not verts:
        return np.zeros((0, 3)), np.zeros((0, 3), int), np.zeros((0, 3), np.uint8)
    return np.array(verts), np.array(faces), np.array(cols, np.uint8)


def blur_texture(rgba, sigma):
    """Suaviza a cor do sprite (convolução normalizada pela máscara opaca) para reduzir o serrilhado ao reamostrar."""
    if sigma <= 0:
        return rgba
    from scipy.ndimage import gaussian_filter
    m = (rgba[..., 3] >= 250).astype(np.float32)
    den = gaussian_filter(m, sigma)
    out = rgba.copy()
    for c in range(3):
        num = gaussian_filter(rgba[..., c].astype(np.float32) * m, sigma)
        v = np.where(den > 1e-4, num / np.maximum(den, 1e-4), rgba[..., c])
        out[..., c] = np.clip(np.where(m > 0, v, rgba[..., c]), 0, 255).astype(np.uint8)
    return out


def carve_mesh(obj, train, use_assign=True, vox=125.0, tol=3.0, dil=0, merge=True, qbits=3, xz=5500.0, min_iou=0.0, q=None, tol_max=30.0, relight=False, blur=0.0, cov_min=0.0, tolc=0.0, amin=200, smooth_r=0.0):
    depths = get_depths(obj, train, use_assign, min_iou)
    vws = [(obj.views[f].rgba, depths[f], obj.views[f].angle) for f in train]
    if cov_min:
        _, grid, org, vox, _, _ = carve_adaptive(vws, cov_min=cov_min, vox=vox, xz=xz, tol=tol, q=q, tol_max=tol_max, amin=amin)
    else:
        grid, org, vox, _ = carve_voxels(vws, vox=vox, xz=xz, tol=tol, dil=dil, q=q, tol_max=tol_max, amin=amin)
    if not grid.any():
        return Mesh(np.zeros((0, 3)), np.zeros((0, 3), int), np.zeros((0, 3), np.uint8))
    ijk, dirs = exposed_faces(grid)
    centre, normals = face_geometry(ijk, dirs, org, vox)
    surf = np.argwhere(grid)
    # centros de voxels que têm alguma face exposta
    surf_c = org + np.unique(ijk, axis=0) * vox
    held = [f for f in H.FACINGS if f not in train]
    rl = obj.views[held[0]].angle if (relight and held) else None
    col, _ = color_faces(centre, normals, surf_c, [(blur_texture(obj.views[f].rgba, blur), obj.views[f].angle) for f in train], relight_to=rl, smooth_r=smooth_r * vox)
    if merge:
        v, f, c = greedy_mesh(ijk, dirs, col, org, vox, qbits, tolc)
    else:
        # um quad por face (sem fusão)
        v, f, c = greedy_mesh(ijk, dirs, col, org, vox, 0)
    return Mesh(v, f, c)


def calibra_sombra(objs, vox=200.0):
    """Estima SHADE a partir de faces vistas por 2+ vistas com papéis diferentes (usa as 4 vistas)."""
    diffs = {(0, 1): [], (0, 2): [], (1, 2): []}
    for obj in objs:
        tr = list(H.FACINGS)
        depths = get_depths(obj, tr, True, 0.3)
        vws = [(obj.views[f].rgba, depths[f], obj.views[f].angle) for f in tr]
        grid, org, vox_, _ = carve_voxels(vws, vox=vox, q=0.7)
        if not grid.any():
            continue
        ijk, dirs = exposed_faces(grid)
        centre, normals = face_geometry(ijk, dirs, org, vox_)
        sc = org + np.unique(ijk, axis=0) * vox_
        S = sample_views(centre, normals, sc, [(obj.views[f].rgba, obj.views[f].angle) for f in tr])
        roles = [face_role(normals, obj.views[f].angle) for f in tr]
        for i in range(4):
            for j in range(i + 1, 4):
                m = (S[i]["opaque"] & S[i]["vis"] & S[j]["opaque"] & S[j]["vis"] & (S[i]["front"] > 0.5) & (S[j]["front"] > 0.5)
                     & (roles[i] != roles[j]) & (roles[i] >= 0) & (roles[j] >= 0))
                if not m.any():
                    continue
                ci, cj = S[i]["col"][m], S[j]["col"][m]
                ok = (ci.min(1) > 20) & (cj.min(1) > 20)
                for a, b, ca, cb in zip(roles[i][m][ok], roles[j][m][ok], ci[ok], cj[ok]):
                    key = (a, b) if a < b else (b, a)
                    r = np.log(ca / cb) if a < b else np.log(cb / ca)
                    diffs[key].append(r)
    return diffs


def soft_gain(n_view, shade=None):
    """Ganho de sombreamento do jogo para normais no referencial da vista (n_view (N,3) unitárias)."""
    sh = SHADE if shade is None else shade
    w = np.stack([np.maximum(n_view[:, 0], 0), np.maximum(n_view[:, 2], 0), np.maximum(n_view[:, 1], 0)], 1) ** 2
    tot = w.sum(1, keepdims=True)
    g = (w / np.maximum(tot, 1e-6)) @ sh
    return np.where(tot > 1e-4, g, sh.mean(0)[None])             # sem face voltada: sombreamento médio


def height_field_lit(rgba, depth, angle, held_angle=None, thr=3.0, amin=250, blur=0.0):
    """height_field + normal por pixel (no referencial da vista) para reiluminar: devolve também o albedo."""
    from scipy.ndimage import gaussian_filter
    valid = (rgba[..., 3] >= amin) & np.isfinite(depth)
    ys, xs = np.nonzero(valid)
    if len(ys) == 0:
        return np.zeros((0, 3)), np.zeros((0, 3), int), np.zeros((0, 3), np.uint8), np.zeros((0, 3))
    G = np.where(valid, depth, 0)
    cd = corner_depths(G, valid, thr)
    n = len(ys)
    corners = [unproject(xs + dx, ys + dy, cd[kk][ys, xs])
               for (dy, dx), kk in zip(((0, 0), (0, 1), (1, 1), (1, 0)), (0, 1, 3, 2))]
    v_own = np.concatenate(corners)
    # normal por pixel pelas diagonais do quadrado (referencial da vista), voltada para a câmera
    d1 = corners[2] - corners[0]
    d2 = corners[3] - corners[1]
    nrm = np.cross(d1, d2)
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
    cd_ = cam_dir_view()
    nrm *= np.where((nrm @ cd_)[:, None] < 0, -1, 1)
    # suaviza a normal sobre a grade de pixels
    N = np.zeros((FH, FW, 3), np.float32)
    N[ys, xs] = nrm
    M = valid.astype(np.float32)
    den = gaussian_filter(M, 1.5)
    for c in range(3):
        N[..., c] = gaussian_filter(N[..., c] * M, 1.5) / np.maximum(den, 1e-4)
    nrm = N[ys, xs]
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
    col = rgba[ys, xs, :3].astype(np.float32)
    alb = col / np.maximum(soft_gain(nrm), 1e-3)
    v = rot_y(v_own, -angle)
    i = np.arange(n)
    faces = np.concatenate([np.stack([i, i + n, i + 2 * n], 1), np.stack([i, i + 2 * n, i + 3 * n], 1)])
    if held_angle is not None:
        nS = rot_y(nrm, -angle)
        nh = rot_y(nS, held_angle)
        col = alb * soft_gain(nh)
    return v, faces, np.clip(np.concatenate([col, col]), 0, 255).astype(np.uint8), alb


def clip_to_hull(v, faces, colors, grid, org, vox, grow=1):
    """Mantém só os triângulos cujo centro cai no volume esculpido (dilatado `grow` voxels)."""
    from scipy.ndimage import binary_dilation
    g = binary_dilation(grid, iterations=grow) if grow else grid
    c = v[faces].mean(1)
    ijk = np.floor((c - org) / vox + 0.5).astype(int)
    ok = (ijk >= 0).all(1) & (ijk < np.array(g.shape)).all(1)
    keep = np.zeros(len(faces), bool)
    keep[ok] = g[ijk[ok, 0], ijk[ok, 1], ijk[ok, 2]]
    return faces[keep], colors[keep]
