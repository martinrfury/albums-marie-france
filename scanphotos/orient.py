"""Remet une photo dans le bon sens d'après les visages (YuNet, OpenCV, hors ligne).
Pas de visage net -> on laisse tel quel (sens où la photo était posée)."""
import os, sys
import numpy as np
import cv2

# dans le .exe PyInstaller, les fichiers embarqués sont sous sys._MEIPASS
_BASE = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                     "scanphotos")
MODEL = os.path.join(_BASE, "models", "face_detection_yunet_2023mar.onnx")
ROTS = {0: None, 90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
        270: cv2.ROTATE_90_COUNTERCLOCKWISE}
_det = None


def faces_score(img):
    """Somme des confiances des visages DROITS (yeux au-dessus de la bouche)."""
    global _det
    h, w = img.shape[:2]
    s = 1024 / max(h, w)
    small = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    if _det is None:
        _det = cv2.FaceDetectorYN.create(MODEL, "", (0, 0), 0.8, 0.3, 5000)
    _det.setInputSize((small.shape[1], small.shape[0]))
    _, f = _det.detect(small)
    if f is None:
        return 0.0
    score = 0.0
    for r in f:
        eyes_y = (r[5] + r[7]) / 2
        mouth_y = (r[11] + r[13]) / 2
        if mouth_y - eyes_y > 0.15 * r[3]:  # visage à l'endroit
            score += float(r[14])
    return score


def best_rotation(img):
    scores = {a: faces_score(img if k is None else cv2.rotate(img, k)) for a, k in ROTS.items()}
    best = max(scores, key=scores.get)
    second = sorted(scores.values())[-2]
    # décision seulement si un sens domine nettement
    if scores[best] >= 0.8 and scores[best] >= 1.5 * second + 0.1:
        return best, scores
    return 0, scores


def upright(img):
    """Renvoie l'image remise dans le bon sens (inchangée si aucun visage net)."""
    rot, _ = best_rotation(img)
    return img if rot == 0 else cv2.rotate(img, ROTS[rot])
