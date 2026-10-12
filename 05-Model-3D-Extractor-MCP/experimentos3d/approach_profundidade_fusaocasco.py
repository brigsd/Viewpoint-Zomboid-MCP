"""Variante 1b - fusão de superfícies recortada pelo volume esculpido: o campo de altura de cada vista de treino
(textura nítida, sem escada de voxel) só fica onde o casco silhueta+profundidade confirma que há matéria."""
import numpy as np
from harness import Mesh, FACINGS
import approach_profundidade_core as C

VOX = 160.0
MIN_IOU = 0.3
Q = 0.6
GROW = 1
RELIGHT = True
USE_ASSIGN = True
WITH_BASE = True


def build(obj, train):
    depths = C.get_depths(obj, train, USE_ASSIGN, MIN_IOU)
    vws = [(obj.views[f].rgba, depths[f], obj.views[f].angle) for f in train]
    grid, org, vox, _ = C.carve_voxels(vws, vox=VOX, q=Q)
    held = [f for f in FACINGS if f not in train]
    hang = obj.views[held[0]].angle if (RELIGHT and held) else None
    vs, fs, cs, off = [], [], [], 0
    for f in train:
        d = C.resolve_depth(obj.views[f]) if USE_ASSIGN else obj.views[f].depth
        if d is None or depths[f] is None:
            continue                                    # sem profundidade confiável: só o casco cobre essa vista
        v, fa, c, _ = C.height_field_lit(obj.views[f].rgba, d, obj.views[f].angle, hang)
        fa, c = C.clip_to_hull(v, fa, c, grid, org, vox, GROW)
        vs.append(v); fs.append(fa + off); cs.append(c); off += len(v)
    base = C.carve_mesh(obj, train, vox=VOX, min_iou=MIN_IOU, q=Q, relight=RELIGHT, blur=2.0, smooth_r=3.5, tolc=30)
    if vs and not WITH_BASE:
        return Mesh(np.concatenate(vs), np.concatenate(fs), np.concatenate(cs))
    if vs:
        # superfícies nítidas por cima; o casco esculpido preenche o que nenhuma vista com profundidade cobre
        faces_b = base.faces + off
        return Mesh(np.concatenate(vs + [base.vertices]), np.concatenate(fs + [faces_b]),
                    np.concatenate(cs + [base.colors]))
    return base
