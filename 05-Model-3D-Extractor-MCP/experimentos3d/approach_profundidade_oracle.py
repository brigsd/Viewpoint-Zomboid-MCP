"""DIAGNÓSTICO (trapaça): esculpe usando as 4 vistas, inclusive a de teste. Dá o teto do método de escultura."""
import approach_profundidade_core as C
from harness import FACINGS

VOX = 160.0
DIL = 0
Q = 0.7
TOL = 3.0

def build(obj, train):
    return C.carve_mesh(obj, list(FACINGS), vox=VOX, min_iou=0.3, q=Q, dil=DIL, tol=TOL)
