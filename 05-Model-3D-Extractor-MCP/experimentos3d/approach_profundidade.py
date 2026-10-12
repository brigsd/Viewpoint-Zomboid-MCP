"""Abordagem "profundidade" (melhor variante): escultura por voxels com silhueta + mapa de profundidade.

Para cada vista de treino, um voxel só sobrevive se cair dentro da silhueta do sprite e estiver na superfície de
profundidade ou atrás dela. A tolerância de profundidade se adapta ao objeto (quando os mapas das vistas se
contradizem, ela sobe); mapas que não batem com o sprite (IoU < MIN_IOU) são descartados e a vista vira só silhueta;
mapas ausentes são completados por depth_assignments (e, sem nada, também viram só silhueta).
Cada face exposta é pintada pela vista que a enxerga de forma mais frontal (z-buffer do próprio modelo para oclusão);
a cor é convertida para "albedo" e reiluminada com o sombreamento do jogo (face direita ~17% mais escura que a
esquerda) usando normais suavizadas, o que tira a escada dos voxels. Faces coplanares de cor parecida são fundidas.
Parâmetros: ver approach_profundidade_carve.py (mesma coisa, com todos os botões)."""
import approach_profundidade_core as C

USE_ASSIGN = True
VOX = 200.0        # unidades de 1/10000 de tile: 50 voxels por tile
MIN_IOU = 0.3
Q = 0.6
TOL = 3.0
TOL_MAX = 30.0
BLUR = 2.0
SMOOTH = 3.5
TOLC = 30.0
RELIGHT = True


def build(obj, train):
    return C.carve_mesh(obj, train, use_assign=USE_ASSIGN, vox=VOX, tol=TOL, min_iou=MIN_IOU, q=Q, tol_max=TOL_MAX,
                        relight=RELIGHT, blur=BLUR, tolc=TOLC, smooth_r=SMOOTH)
