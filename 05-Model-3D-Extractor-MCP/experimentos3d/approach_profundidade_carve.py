"""Variante 2 - escultura por voxels com silhueta + profundidade."""
import approach_profundidade_core as C

USE_ASSIGN = True
VOX = 125.0
TOL = 3.0
DIL = 0
QBITS = 3
MIN_IOU = 0.0
Q = None
TOL_MAX = 30.0
RELIGHT = False
BLUR = 0.0
COV_MIN = 0.0
TOLC = 0.0
AMIN = 200
SMOOTH = 0.0


def build(obj, train):
    return C.carve_mesh(obj, train, use_assign=USE_ASSIGN, vox=VOX, tol=TOL, dil=DIL, qbits=QBITS, min_iou=MIN_IOU, q=Q, tol_max=TOL_MAX, relight=RELIGHT, blur=BLUR, cov_min=COV_MIN, tolc=TOLC, amin=AMIN, smooth_r=SMOOTH)
