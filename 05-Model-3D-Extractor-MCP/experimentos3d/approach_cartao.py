"""Base de comparação: "cartão 2D". Mostra a imagem de uma direção conhecida sempre de frente para a câmera,
como um sprite chapado. Não sabe nada de 3D: é o piso que qualquer abordagem precisa superar."""
import numpy as np

from harness import FACINGS, Mesh, rot_y, unproject


def pixel_mesh(rgba, gray=190.0):
    """Um quadradinho por pixel opaco, num plano de frente para a câmera, que reproduz a imagem."""
    ys, xs = np.nonzero(rgba[..., 3] >= 128)
    corners = []
    for dx, dy in ((0, 0), (1, 0), (1, 1), (0, 1)):
        corners.append(unproject(xs + dx, ys + dy, np.full(len(xs), gray)))
    v = np.concatenate(corners)               # 4 blocos de N vértices
    n = len(xs)
    i = np.arange(n)
    faces = np.concatenate([np.stack([i, i + n, i + 2 * n], 1), np.stack([i, i + 2 * n, i + 3 * n], 1)])
    colors = np.concatenate([rgba[ys, xs, :3]] * 2)
    return v, faces, colors


def build(obj, train):
    held = next(f for f in FACINGS if f not in train)
    order = {"S": ("E", "W", "N"), "E": ("S", "N", "W"), "N": ("E", "W", "S"), "W": ("S", "N", "E")}[held]
    src = next(f for f in order if f in train)          # a direção vizinha conhecida
    v, faces, colors = pixel_mesh(obj.views[src].rgba)
    # a malha está no referencial da vista "held"; leva para o referencial de S
    v = rot_y(v, -obj.views[held].angle)
    return Mesh(v, faces, colors.astype(np.uint8))
