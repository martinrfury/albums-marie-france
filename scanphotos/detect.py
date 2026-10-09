"""Détourage de tirages posés sur fond blanc (capot du scanner), sans format imposé."""
import numpy as np
import cv2

WORK = 1000  # hauteur de travail (px) pour la détection


def photo_mask(small):
    """Pixels qui ne sont pas du fond blanc : couleur, sombre, ou texturé."""
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype(np.float32)
    # fond = mode des pixels très clairs du bord de l'image
    border = np.concatenate([lab[:8].reshape(-1, 3), lab[-8:].reshape(-1, 3),
                             lab[:, :8].reshape(-1, 3), lab[:, -8:].reshape(-1, 3)])
    bg = np.median(border[border[:, 0] >= np.percentile(border[:, 0], 50)], axis=0)
    dist = np.linalg.norm(lab - bg, axis=2)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
    mu = cv2.blur(gray, (7, 7))
    std = np.sqrt(np.maximum(cv2.blur(gray * gray, (7, 7)) - mu * mu, 0))
    m = ((dist > 10) | (std > 4)).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    e = 10  # liseré sombre du bord de vitre : il relierait toutes les photos
    m[:e] = 0; m[-e:] = 0; m[:, :e] = 0; m[:, -e:] = 0
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    # remplir les trous (ciels blancs à l'intérieur d'une photo)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(m)
    cv2.drawContours(filled, cnts, -1, 255, -1)
    return filled


def split_concave(sub, min_area, depth=0):
    """Coupe un bloc de tirages collés entre ses 2 coins rentrants les plus profonds."""
    cs, _ = cv2.findContours(sub, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cs = [c for c in cs if cv2.contourArea(c) > min_area]
    out = []
    for c in cs:
        rect = cv2.minAreaRect(c)
        if cv2.contourArea(c) / max(rect[1][0] * rect[1][1], 1) >= 0.9 or depth > 3:
            out.append(rect); continue
        d = cv2.convexityDefects(c, cv2.convexHull(c, returnPoints=False))
        if d is None or len(d) < 2:
            out.append(rect); continue
        d = d.reshape(-1, 4)  # (N,1,4) en OpenCV 4, (N,4) en OpenCV 5
        d = d[np.argsort(-d[:, 3])][:2]
        c = c.reshape(-1, 2)
        p1 = tuple(int(v) for v in c[d[0][2]]); p2 = tuple(int(v) for v in c[d[1][2]])
        one = np.zeros_like(sub); cv2.drawContours(one, [c.reshape(-1, 1, 2)], -1, 255, -1)
        cv2.line(one, p1, p2, 0, 5)
        out += split_concave(one, min_area, depth + 1)
    return out


def rects_from_mask(m, min_frac=0.02):
    return split_concave(m, min_frac * m.shape[0] * m.shape[1])


def crop(img, rect, scale, inset=15):
    """Redresse le rectangle par ses 4 coins (indépendant de la convention
    d'angle d'OpenCV) ; le haut de la photo reste le haut du scan."""
    pts = cv2.boxPoints(rect) * scale
    s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
    tl, br = pts[np.argmin(s)], pts[np.argmax(s)]
    tr, bl = pts[np.argmin(d)], pts[np.argmax(d)]
    w = int(round((np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2)) - 2 * inset
    h = int(round((np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2)) - 2 * inset
    src = np.float32([tl, tr, br, bl])
    dst = np.float32([[-inset, -inset], [w + inset, -inset],
                      [w + inset, h + inset], [-inset, h + inset]])
    M = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, M, (w, h), flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))


def split_photos(img):
    """Image BGR d'une planche -> liste des photos détourées (haut->bas, gauche->droite)."""
    scale = img.shape[0] / WORK
    small = cv2.resize(img, (round(img.shape[1] / scale), WORK), interpolation=cv2.INTER_AREA)
    rects = rects_from_mask(photo_mask(small))
    rects.sort(key=lambda r: (round(r[0][1] / 150), r[0][0]))
    return [crop(img, r, scale) for r in rects]
