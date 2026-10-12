"""Abordagem "silhueta" (visual hull): só as 4 imagens de sprite, sem mapa de profundidade nem caixas.

1. Grade de voxels cúbicos sobre o volume do tile (X,Z em -5000..5000; Y de 0 até a altura que a
   silhueta mais alta permite).
2. Um voxel sobrevive se o centro projeta dentro da silhueta opaca (alpha >= ALPHA) em TODAS as vistas
   de treino.
3. Cada face exposta é pintada pela vista de treino que a enxerga mais de frente, com teste de
   visibilidade (z-buffer por vista, feito com as próprias faces expostas).
4. Só faces expostas, coplanares de mesma cor (quantizada) fundidas por "greedy meshing".

`make_build(**params)` devolve uma função build; `build` é a configuração padrão.
Estatísticas de cada chamada ficam em STATS (triângulos, segundos).
"""
import time

import numpy as np

from dataclasses import replace

from harness import FACINGS, FH, FW, KH, KX, KY, OX, OY, Mesh, rot_y

STATS = []

# vetor unitário (no referencial da vista) do ponto de vista: o raio de visão da projeção do jogo
_D = np.array([1.0, 0.0064 / 0.007838, 1.0])
_D = _D / np.linalg.norm(_D)

DEFAULTS = dict(
    res=32,            # voxels ao longo de 10000 unidades (um tile)
    alpha=250,         # limiar de opacidade da silhueta
    quant=24,          # passo de quantização de cor para fundir quadros
    shadow=False,      # remover sombra de chão desenhada (pixels escuros semitransparentes)
    dilate=0,          # dilatação (px) da silhueta antes de esculpir
    ymargin=0,         # voxels de folga em Y
    fill="mean",       # cor das faces que nenhuma vista de treino enxerga: mean | front | neigh
    merge=True,
    bottom=False,      # emitir faces de baixo (nenhuma câmera de cima as vê)
    samples=1,         # 1 = só o centro; 5 = centro + 4 cantos (voto)
    minvotes=None,
    align=False,       # registra as vistas por deslocamento inteiro de pixels antes de esculpir
    alres=24, alrange=6,
    adapt=None,        # cobertura mínima da silhueta de treino; se menor, dilata a silhueta (1 px por passo)
    maxdil=3,
    adaptmode="dilate",
)


def _mask(view, p):
    a = view.rgba[..., 3] >= p["alpha"]
    if p["shadow"]:
        a = a & _not_shadow(view.rgba)
    return a


def _dilate(a, k):
    for _ in range(k):
        b = a.copy()
        b[1:] |= a[:-1]; b[:-1] |= a[1:]; b[:, 1:] |= a[:, :-1]; b[:, :-1] |= a[:, 1:]
        a = b
    return a


def _not_shadow(rgba):
    """Sombra de chão: escura e (quase) neutra. Só descarta se não tem cor própria."""
    rgb = rgba[..., :3].astype(np.int16)
    lum = rgb.mean(axis=2)
    return ~(lum < 40)


def _sample_px(P, ang, s):
    """Pontos no referencial S -> (px, py, depth) na vista de ângulo ang. P (...,3)."""
    q = rot_y(P, ang)
    x, y, z = q[..., 0], q[..., 1], q[..., 2]
    sx = OX + KX * (x - z)
    sy = OY + KY * (x + z) - KH * y
    d = KX * (x + z) + 0.005225 * y
    return sx, sy, d


def _blur_rgb(rgba, alpha):
    """Cor média 3x3 ponderada por opacidade (para amostrar a cor de uma face)."""
    a = (rgba[..., 3] >= alpha).astype(np.float32)
    rgb = rgba[..., :3].astype(np.float32) * a[..., None]
    def box(m):
        pm = np.pad(m, ((1, 1), (1, 1)) + ((0, 0),) * (m.ndim - 2))
        out = 0
        for dy in range(3):
            for dx in range(3):
                out = out + pm[dy:dy + m.shape[0], dx:dx + m.shape[1]]
        return out
    num, den = box(rgb), box(a)
    return num / np.maximum(den, 1e-6)[..., None], den


def _grid(n, ny):
    s = 10000.0 / n
    ax = (np.arange(n) + 0.5) * s - 5000.0
    ay = (np.arange(ny) + 0.5) * s
    X, Y, Z = np.meshgrid(ax, ay, ax, indexing="ij")
    return np.stack([X, Y, Z], axis=-1), s


def _shift(a, dx, dy):
    out = np.zeros_like(a)
    H_, W_ = a.shape[:2]
    ys, yd = (slice(max(0, -dy), H_ - max(0, dy)), slice(max(0, dy), H_ - max(0, -dy)))
    xs, xd = (slice(max(0, -dx), W_ - max(0, dx)), slice(max(0, dx), W_ - max(0, -dx)))
    out[yd, xd] = a[ys, xs]
    return out


def _consistency(masks, angles, C, s):
    """Casco das máscaras (já deslocadas) e média do IoU entre a projeção do casco e cada máscara."""
    n, ny = C.shape[0], C.shape[1]
    occ = np.ones((n, ny, n), bool)
    pix = []
    for m, ang in zip(masks, angles):
        sx, sy, _ = _sample_px(C, ang, s)
        ix, iy = np.floor(sx).astype(int), np.floor(sy).astype(int)
        ok = (ix >= 0) & (ix < FW) & (iy >= 0) & (iy < FH)
        ins = np.zeros_like(occ)
        ins[ok] = m[iy[ok], ix[ok]]
        occ &= ins
        pix.append((ix, iy, ok))
    r = max(1, int(round(KX * s * 0.7)))
    tot = 0.0
    for m, (ix, iy, ok) in zip(masks, pix):
        sel = occ & ok
        pm = np.zeros((FH, FW), bool)
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                pm[np.clip(iy[sel] + dy, 0, FH - 1), np.clip(ix[sel] + dx, 0, FW - 1)] = True
        tot += (pm & m).sum() / max((pm | m).sum(), 1)
    return tot / len(masks)


def _align(views, p, ny):
    """Acha deslocamentos inteiros (dx, dy) de cada vista (a primeira fica fixa) que tornam as silhuetas
    mais consistentes entre si. Busca por coordenadas: dx e depois dy, 2 rodadas."""
    C, s = _grid(p["alres"], ny)
    masks = [_mask(v, p) for v in views]
    angles = [v.angle for v in views]
    sh = [(0, 0)] * len(views)

    def ev(sh_):
        return _consistency([_shift(m, *d) for m, d in zip(masks, sh_)], angles, C, s)
    best = ev(sh)
    base_score = best
    for _ in range(2):
        for i in range(1, len(views)):
            for axis, rng in ((0, range(-p["alrange"], p["alrange"] + 1)), (1, range(-2, 3))):
                cand = []
                for d in rng:
                    t = list(sh); t[i] = (d, sh[i][1]) if axis == 0 else (sh[i][0], d)
                    cand.append((ev(t) - 1e-4 * abs(d), t))
                sc, t = max(cand, key=lambda c: c[0])
                if sc > best:
                    best, sh = sc, t
    return sh, base_score, best


_DIRS = [(0, 1), (0, -1), (1, 1), (1, -1), (2, 1), (2, -1)]   # (eixo, sinal): 0=X 1=Y 2=Z


def build_with(obj, train, p):
    t0 = time.time()
    n = p["res"]
    s = 10000.0 / n
    views = [obj.views[f] for f in train]
    shifts = None
    # ---- altura máxima a partir do topo das silhuetas (ponto mais perto da câmera é o mais alto possível)
    tops = []
    for v in views:
        ys = np.nonzero(_mask(v, p).any(axis=1))[0]
        if len(ys):
            tops.append(ys.min())
    if not tops:
        return Mesh(np.zeros((0, 3)), np.zeros((0, 3), int), np.zeros((0, 3), np.uint8))
    ymax = max(0.0, (OY + KY * 10000 - min(tops)) / KH)
    ny = int(np.ceil(ymax / s)) + p["ymargin"]
    ny = max(1, min(ny, int(30000 / s)))
    if p["align"]:
        nya = max(1, min(int(np.ceil(ymax / (10000.0 / p["alres"]))) + 1, 30000 // (10000 // p["alres"])))
        shifts, sc0, sc1 = _align(views, p, nya)
        views = [replace(v, rgba=_shift(v.rgba, *d)) for v, d in zip(views, shifts)]
    C, _ = _grid(n, ny)
    base = {v.name: _mask(v, {**p, "dilate": 0}) for v in views}
    if p["samples"] == 1:
        offs = [(0, 0, 0)]
    else:
        h = s * 0.4
        offs = [(0, 0, 0), (h, 0, h), (-h, 0, h), (h, 0, -h), (-h, 0, -h)]
    minv = p["minvotes"] if p["minvotes"] is not None else 1
    pix = []
    for v in views:
        lst = []
        for o in offs:
            sx, sy, _ = _sample_px(C + np.array(o), v.angle, s)
            ix, iy = np.floor(sx).astype(int), np.floor(sy).astype(int)
            lst.append((ix, iy, (ix >= 0) & (ix < FW) & (iy >= 0) & (iy < FH)))
        pix.append(lst)

    def carve(k, quorum=None):
        occ = np.ones((n, ny, n), bool)
        cnt = 0
        for v, lst in zip(views, pix):
            m = _dilate(base[v.name], k)
            votes = 0
            for ix, iy, ok in lst:
                ins = np.zeros_like(occ)
                ins[ok] = m[iy[ok], ix[ok]]
                votes = votes + ins
            hit = votes >= (minv if len(offs) > 1 else 1)
            if quorum is None:
                occ &= hit
            else:
                cnt = cnt + hit
        if quorum is not None:
            occ = cnt >= quorum
        return occ

    def coverage(occ):
        """Fração da silhueta de cada vista de treino que o casco consegue reproduzir (pior vista)."""
        r = max(1, int(round(KX * s * 0.7)))
        worst = 1.0
        for v, lst in zip(views, pix):
            ix, iy, ok = lst[0]
            sel = occ & ok
            pm = np.zeros((FH, FW), bool)
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    pm[np.clip(iy[sel] + dy, 0, FH - 1), np.clip(ix[sel] + dx, 0, FW - 1)] = True
            m = base[v.name]
            worst = min(worst, (pm & m).sum() / max(m.sum(), 1))
        return worst

    k = p["dilate"]
    occ = carve(k)
    if p["adapt"]:
        if p["adaptmode"] == "dilate":
            while k < p["maxdil"] and coverage(occ) < p["adapt"]:
                k += 1
                occ = carve(k)
        elif coverage(occ) < p["adapt"]:             # "quorum": N-1 de N vistas bastam
            occ = carve(k, quorum=len(views) - 1)
    if not occ.any():
        return Mesh(np.zeros((0, 3)), np.zeros((0, 3), int), np.zeros((0, 3), np.uint8))

    # ---- faces expostas
    pad = np.pad(occ, 1)
    faces = []        # (eixo, sinal, i, j, k)
    for ax_, sg in _DIRS:
        sl = [slice(1, -1)] * 3
        sl[ax_] = slice(2, None) if sg > 0 else slice(0, -2)
        nb = pad[tuple(sl)]
        ex = occ & ~nb
        if sg < 0 and ax_ == 1 and not p["bottom"]:
            ex = ex & False
        idx = np.argwhere(ex)
        if len(idx):
            faces.append((ax_, sg, idx))
    # centros e normais
    cen, nor, key = [], [], []
    for ax_, sg, idx in faces:
        c = C[idx[:, 0], idx[:, 1], idx[:, 2]].copy()
        c[:, ax_] += sg * s / 2
        nv = np.zeros((len(idx), 3)); nv[:, ax_] = sg
        cen.append(c); nor.append(nv)
        key.append(np.concatenate([np.full((len(idx), 1), ax_ * 2 + (sg > 0)), idx], axis=1))
    cen, nor, key = np.concatenate(cen), np.concatenate(nor), np.concatenate(key)
    F = len(cen)

    # ---- cor por face: melhor vista (mais frontal) entre as que a enxergam
    best_front = np.full(F, -1.0)
    best_col = np.zeros((F, 3), np.float32)
    seen = np.zeros(F, bool)
    any_front = np.full(F, -1.0)
    any_col = np.zeros((F, 3), np.float32)
    for v in views:
        blur, den = _blur_rgb(v.rgba, p["alpha"])
        sx, sy, d = _sample_px(cen, v.angle, s)
        nv = rot_y(nor, v.angle)
        front = nv @ _D
        # z-buffer da vista com as faces voltadas para a câmera
        fr = front > 1e-6
        zb = np.full((FH, FW), -np.inf, np.float32)
        # pegada de cada face na tela: 4 cantos; usa bounding box (pequena)
        u1 = np.zeros((F, 3)); u2 = np.zeros((F, 3))
        for ax_ in range(3):
            sel = np.abs(nor[:, ax_]) > 0
            # eixos tangentes
            t = [a for a in range(3) if a != ax_]
            u1[sel, t[0]] = s / 2
            u2[sel, t[1]] = s / 2
        corners = [cen + a * u1 + b * u2 for a in (-1, 1) for b in (-1, 1)]
        cs = [_sample_px(c, v.angle, s) for c in corners]
        csx = np.stack([c[0] for c in cs]); csy = np.stack([c[1] for c in cs])
        x0, x1 = np.floor(csx.min(0)).astype(int), np.floor(csx.max(0) - 1e-6).astype(int)
        y0, y1 = np.floor(csy.min(0)).astype(int), np.floor(csy.max(0) - 1e-6).astype(int)
        x1 = np.maximum(x0, x1); y1 = np.maximum(y0, y1)
        W_, H_ = int((x1 - x0).max()), int((y1 - y0).max())
        for dy in range(H_ + 1):
            for dx in range(W_ + 1):
                px, py = x0 + dx, y0 + dy
                ok = fr & (px <= x1) & (py <= y1) & (px >= 0) & (px < FW) & (py >= 0) & (py < FH)
                np.maximum.at(zb, (py[ok], px[ok]), d[ok].astype(np.float32))
        ix, iy = np.floor(sx).astype(int), np.floor(sy).astype(int)
        inb = (ix >= 0) & (ix < FW) & (iy >= 0) & (iy < FH)
        ixc, iyc = np.clip(ix, 0, FW - 1), np.clip(iy, 0, FH - 1)
        tol = KX * s * 1.2
        vis = fr & inb & (d >= zb[iyc, ixc] - tol) & (den[iyc, ixc] > 0)
        col = blur[iyc, iyc * 0 + ixc]
        upd = vis & (front > best_front)
        best_front[upd] = front[upd]; best_col[upd] = col[upd]; seen |= vis
        upd2 = fr & inb & (den[iyc, ixc] > 0) & (front > any_front)
        any_front[upd2] = front[upd2]; any_col[upd2] = col[upd2]
    colors = best_col.copy()
    if (~seen).any():
        if p["fill"] == "front":
            colors[~seen] = any_col[~seen]
        elif p["fill"] == "mean":
            colors[~seen] = best_col[seen].mean(0) if seen.any() else 128
        elif p["fill"] == "neigh":
            colors = _fill_neighbours(key, colors, seen, any_col)
    colors = np.clip(colors, 0, 255)

    mesh = _emit(key, colors, C, s, p)
    STATS.append(dict(shifts=shifts, dil=k, tris=len(mesh.faces), faces=F, voxels=int(occ.sum()), seconds=time.time() - t0))
    return mesh


def _fill_neighbours(key, colors, seen, any_col):
    """Faces não vistas recebem a média das faces vistas do mesmo voxel/vizinhas (3x3x3), senão a média global."""
    out = colors.copy()
    vox = key[:, 1:4]
    coords = {}
    for i in np.nonzero(seen)[0]:
        coords.setdefault(tuple(vox[i]), []).append(i)
    glob = colors[seen].mean(0) if seen.any() else np.array([128.0] * 3)
    for i in np.nonzero(~seen)[0]:
        c = vox[i]
        acc = []
        for r in (0, 1, 2):
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    for dz in range(-r, r + 1):
                        for j in coords.get((c[0] + dx, c[1] + dy, c[2] + dz), []):
                            acc.append(colors[j])
            if acc:
                break
        out[i] = np.mean(acc, 0) if acc else glob
    return out


def _emit(key, colors, C, s, p):
    """Greedy meshing por plano. key: (F, 4) = [dir, i, j, k]; colors (F,3)."""
    n, ny = C.shape[0], C.shape[1]
    q = p["quant"]
    qc = (np.round(colors / q)).astype(np.int32) if q else colors.astype(np.int32)
    verts, tris, cols = [], [], []
    base = 0
    x0, y0, z0 = -5000.0, 0.0, -5000.0
    org = np.array([x0, y0, z0])
    for d in range(6):
        ax_, sg = d // 2, 1 if d % 2 else -1
        sel = np.nonzero(key[:, 0] == d)[0]
        if not len(sel):
            continue
        t = [a for a in range(3) if a != ax_]
        dims = (n, ny, n)
        # planos por índice na dimensão ax_
        planes = {}
        for f in sel:
            planes.setdefault(int(key[f, 1 + ax_]), []).append(f)
        for pl, fs in planes.items():
            fs = np.array(fs)
            gu = key[fs, 1 + t[0]]; gv = key[fs, 1 + t[1]]
            U, V = dims[t[0]], dims[t[1]]
            grid = -np.ones((U, V), np.int64)
            grid[gu, gv] = fs
            used = np.zeros((U, V), bool)
            for a in range(U):
                for b in range(V):
                    f0 = grid[a, b]
                    if f0 < 0 or used[a, b]:
                        continue
                    ck = qc[f0]
                    w = 1
                    if p["merge"]:
                        while a + w < U and grid[a + w, b] >= 0 and not used[a + w, b] and (qc[grid[a + w, b]] == ck).all():
                            w += 1
                        h = 1
                        while b + h < V:
                            row = grid[a:a + w, b + h]
                            if (row < 0).any() or used[a:a + w, b + h].any() or not (qc[row] == ck).all():
                                break
                            h += 1
                    else:
                        h = 1
                    used[a:a + w, b:b + h] = True
                    members = grid[a:a + w, b:b + h].ravel()
                    col = colors[members].mean(0)
                    # quadrilátero
                    pos = np.zeros(3)
                    pos[ax_] = (pl + (1 if sg > 0 else 0)) * s
                    pos[t[0]] = a * s; pos[t[1]] = b * s
                    e1 = np.zeros(3); e1[t[0]] = w * s
                    e2 = np.zeros(3); e2[t[1]] = h * s
                    o = org + pos
                    quad = np.array([o, o + e1, o + e1 + e2, o + e2])
                    verts.append(quad)
                    # orientação: normal para fora
                    nrm = np.cross(e1, e2)
                    if (nrm[ax_] > 0) == (sg > 0):
                        tris.append([base, base + 1, base + 2]); tris.append([base, base + 2, base + 3])
                    else:
                        tris.append([base, base + 2, base + 1]); tris.append([base, base + 3, base + 2])
                    cols += [col, col]
                    base += 4
    return Mesh(np.concatenate(verts), np.array(tris, int), np.array(cols).round().astype(np.uint8))


def make_build(**kw):
    p = {**DEFAULTS, **kw}

    def build(obj, train):
        return build_with(obj, train, p)
    return build


build = make_build()
