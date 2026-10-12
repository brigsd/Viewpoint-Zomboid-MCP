"""Variante 1 - fusão de superfícies: campo de altura por vista de treino, girado para S e unido."""
import numpy as np
from harness import Mesh
import approach_profundidade_core as C

USE_ASSIGN = True


def build(obj, train):
    depths = C.get_depths(obj, train, USE_ASSIGN)
    vs, fs, cs, off = [], [], [], 0
    for f in train:
        if depths[f] is None:
            continue
        v, fa, c = C.height_field(obj.views[f].rgba, depths[f], obj.views[f].angle)
        vs.append(v); fs.append(fa + off); cs.append(c); off += len(v)
    if not vs:                                           # nenhuma profundidade: esculpe só pela silhueta
        return C.carve_mesh(obj, train, use_assign=False)
    return Mesh(np.concatenate(vs), np.concatenate(fs), np.concatenate(cs))
